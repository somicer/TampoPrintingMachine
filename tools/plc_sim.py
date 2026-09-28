#!/usr/bin/env python3
"""Minimal Delta DVP-SV2 IL interpreter + pad-printer plant model.

Runs plc/TampoPrinter_SV2.il against a simple physical model of the
machine (X/Y stepper axes, Z pneumatic cylinder, sensors) and checks the
safety invariants every scan.  It covers only the instruction subset the
program uses and simplifies pulse-output behaviour, so it verifies the
LOGIC (sequence, interlocks, alarms), not Delta firmware timing.

Usage:  python3 tools/plc_sim.py            (runs all scenarios)
"""
import math
import re
import sys
from collections import defaultdict

SCAN = 0.005                       # s per scan
IL_PATH = "plc/TampoPrinter_SV2.il"


# ---------------------------------------------------------------- PLC core
def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


class PLC:
    def __init__(self, path):
        self.prog = []
        self.labels = {}
        for raw in open(path, encoding="utf-8"):
            line = raw.split("//")[0].strip()
            if line:
                p = line.split()
                if re.fullmatch(r"P\d+", p[0]) and len(p) == 1:
                    self.labels[p[0]] = len(self.prog)
                    self.prog.append(("LABEL", []))
                    continue
                self.prog.append((p[0], p[1:]))
        self.bits = defaultdict(bool)      # X, Y, M, T(contact)
        self.words = defaultdict(int)      # D, T(value) - 16-bit signed
        self.tacc = defaultdict(float)     # timer accumulators (s)
        self.edge = {}                     # per-instruction previous value
        self.pulse = {}                    # pulse channel state
        self.first = True

    # --- operand access -------------------------------------------------
    def bit(self, name):
        return self.bits[name]

    def setbit(self, name, v):
        self.bits[name] = bool(v)

    def ix(self, op):
        m = re.fullmatch(r"([A-Z])(\d+)([EF]\d)?", op)
        if m and m.group(3):
            return "%s%d" % (m.group(1), int(m.group(2)) + s16(self.words[m.group(3)]))
        return op

    def val(self, op, dbl=False):
        op = self.ix(op)
        if op.startswith("K"):
            if op.startswith("K4M"):
                base = int(op[3:])
                return sum((1 << i) for i in range(16) if self.bits["M%d" % (base + i)])
            return int(op[1:])
        if op.startswith("T"):
            return int(self.tacc[op] / self.tbase(op))
        if op[0] in "EF":
            return s16(self.words[op])
        n = int(op[1:])
        if dbl:
            lo = self.words["D%d" % n] & 0xFFFF
            hi = self.words["D%d" % (n + 1)] & 0xFFFF
            return s32(lo | (hi << 16))
        return s16(self.words[op])

    def put(self, op, v, dbl=False):
        op = self.ix(op)
        if op[0] in "EF":
            self.words[op] = s16(v)
            return
        n = int(op[1:])
        if dbl:
            v &= 0xFFFFFFFF
            self.words["D%d" % n] = s16(v & 0xFFFF)
            self.words["D%d" % (n + 1)] = s16(v >> 16)
        else:
            self.words[op] = s16(v)

    def put64(self, op, v):
        n = int(op[1:])
        v &= (1 << 64) - 1
        for i in range(4):
            self.words["D%d" % (n + i)] = s16((v >> (16 * i)) & 0xFFFF)

    @staticmethod
    def tbase(t):
        n = int(t[1:])
        return 0.01 if 200 <= n <= 239 else 0.1

    # --- scan -------------------------------------------------------------
    CMP = {"=": lambda a, b: a == b, "<>": lambda a, b: a != b, ">": lambda a, b: a > b,
           "<": lambda a, b: a < b, ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b}

    def scan(self):
        self.bits["M1000"] = True
        self.bits["M1002"] = self.first
        acc = False
        stack = []          # block stack for ANB/ORB
        mps = []
        idx = -1
        calls = []
        loops = []
        while True:
            idx += 1
            if idx >= len(self.prog):
                break
            op, a = self.prog[idx]
            if op == "LABEL":
                continue
            if op == "FEND" and not calls:
                break
            if op == "SRET":
                idx = calls.pop()
                continue
            if op == "FOR":
                loops.append([idx, self.val(a[0])])
                continue
            if op == "NEXT":
                loops[-1][1] -= 1
                if loops[-1][1] > 0:
                    idx = loops[-1][0]
                else:
                    loops.pop()
                continue
            if op in ("CJ", "CALL"):
                if acc:
                    if op == "CALL":
                        calls.append(idx)
                    idx = self.labels[a[0]]
                continue
            m = re.match(r"^(D?)(LD|AND|OR)(=|<>|>=|<=|>|<)$", op)
            if m:
                dbl = m.group(1) == "D"
                r = self.CMP[m.group(3)](self.val(a[0], dbl), self.val(a[1], dbl))
                kind = m.group(2)
                if kind == "LD":
                    stack.append(acc); acc = r
                elif kind == "AND":
                    acc = acc and r
                else:
                    acc = acc or r
                continue
            if op in ("LD", "LDI", "LDP", "LDF", "AND", "ANI", "ANDP", "OR", "ORI", "ORP"):
                v = self.bit(a[0])
                if op in ("LDP", "ORP", "ANDP"):
                    prev = self.edge.get(idx, v if self.first else False)
                    self.edge[idx] = v
                    v = v and not prev
                elif op == "LDF":
                    prev = self.edge.get(idx, v)
                    self.edge[idx] = v
                    v = prev and not v
                if op in ("LDI", "ANI", "ORI"):
                    v = not v
                if op.startswith("LD"):
                    stack.append(acc); acc = v
                elif op.startswith("AN"):
                    acc = acc and v
                else:
                    acc = acc or v
                continue
            if op == "ANB":
                acc = stack.pop() and acc; continue
            if op == "ORB":
                acc = stack.pop() or acc; continue
            if op == "MPS":
                mps.append(acc); continue
            if op == "MRD":
                acc = mps[-1]; continue
            if op == "MPP":
                acc = mps.pop(); continue
            if op == "END":
                break
            # ---- outputs / applied instructions (use acc) ----------
            if op == "OUT":
                self.setbit(a[0], acc); continue
            if op == "TMR":
                t = a[0]
                preset = self.val(a[1])
                if acc:
                    self.tacc[t] += SCAN
                    if self.tacc[t] >= preset * self.tbase(t) - 1e-9:
                        self.bits[t] = True
                else:
                    self.tacc[t] = 0.0
                    self.bits[t] = False
                continue
            if op == "DDRVA" or op == "DZRN":
                self.pulse_instr(idx, op, a, acc)
                continue
            if not acc:
                continue
            if op == "SET":
                self.setbit(a[0], True)
            elif op == "RST":
                self.setbit(a[0], False)
            elif op == "ZRST":
                t = a[0][0]
                for n in range(int(a[0][1:]), int(a[1][1:]) + 1):
                    if t == "M":
                        self.bits["M%d" % n] = False
                    else:
                        self.words["D%d" % n] = 0
            elif op == "MOV":
                self.put(a[1], self.val(a[0]))
            elif op == "DMOV":
                self.put(a[1], self.val(a[0], True), True)
            elif op in ("DADD", "DSUB"):
                x, y = self.val(a[0], True), self.val(a[1], True)
                self.put(a[2], x + y if op == "DADD" else x - y, True)
            elif op == "DMUL":
                self.put64(a[2], self.val(a[0], True) * self.val(a[1], True))
            elif op == "DDIV":
                x, y = self.val(a[0], True), self.val(a[1], True)
                if y:
                    q = int(x / y)
                    self.put(a[2], q, True)
                    self.put("D%d" % (int(a[2][1:]) + 2), x - q * y, True)
            elif op == "DABS":
                self.put(a[0], abs(self.val(a[0], True)), True)
            elif op == "INC":
                self.put(a[0], self.val(a[0]) + 1)
            elif op == "ADD":
                self.put(a[2], self.val(a[0]) + self.val(a[1]))
            elif op == "MUL":
                self.put(a[2], self.val(a[0]) * self.val(a[1]), True)
            elif op == "DINC":
                self.put(a[0], self.val(a[0], True) + 1, True)
            elif op == "DZCP":
                lo, hi, s = (self.val(x, True) for x in a[:3])
                n = int(a[3][1:])
                self.bits["M%d" % n] = s < lo
                self.bits["M%d" % (n + 1)] = lo <= s <= hi
                self.bits["M%d" % (n + 2)] = s > hi
            else:
                raise NotImplementedError(op)
        self.first = False

    # --- pulse output model (per channel) ------------------------------
    CH = {"Y0": ("D1030", "M1029", "M1336", "M1078", "D1343"),
          "Y2": ("D1336", "M1030", "M1337", "M1104", "D1353")}

    def pulse_instr(self, idx, op, a, acc):
        out = a[2] if op == "DDRVA" else a[3]
        pos_d, done_m, busy_m, pause_m, acc_d = self.CH[out]
        prev = self.edge.get(idx, False)
        self.edge[idx] = acc
        ch = self.pulse.setdefault(out, {"active": None})
        if acc and not prev and ch["active"] is None:
            if op == "DDRVA":
                ch.update(active=idx, mode="abs", target=self.val(a[0], True),
                          f=self.val(a[1], True), v=0.0)
            else:
                ch.update(active=idx, mode="home", f=self.val(a[0], True),
                          creep=self.val(a[1], True), dog=a[2], stage=0, v=0.0)
            self.bits[busy_m] = True
        if not acc and ch["active"] == idx:
            ch["active"] = None
            self.bits[busy_m] = False

    def pulse_step(self, plant):
        for out, (pos_d, done_m, busy_m, pause_m, acc_d) in self.CH.items():
            ch = self.pulse.get(out)
            if not ch or ch["active"] is None or self.bits[pause_m]:
                if ch and ch["active"] is not None and self.bits[pause_m]:
                    ch["v"] = 0.0
                continue
            pos = self.val(pos_d, True)
            amax = ch["f"] / max(self.val(acc_d) / 1000.0, 0.05)   # pulses/s^2
            if ch["mode"] == "abs":
                dist = ch["target"] - pos
                if dist == 0:
                    ch["active"] = None
                    self.bits[busy_m] = False
                    self.bits[done_m] = True
                    continue
                vstop = math.sqrt(2 * amax * abs(dist))
                ch["v"] = min(ch["f"], ch["v"] + amax * SCAN, vstop)
                step = max(1, int(round(ch["v"] * SCAN)))
                step = min(step, abs(dist))
                self.put(pos_d, pos + (step if dist > 0 else -step), True)
            else:  # home: negative until DOG on, creep until DOG off
                dog = self.bits[ch["dog"]]
                if ch["stage"] == 0 and dog:
                    ch["stage"] = 1
                if ch["stage"] == 1 and not dog:
                    ch["active"] = None
                    self.bits[busy_m] = False
                    self.bits[done_m] = True
                    self.put(pos_d, 0, True)
                    plant.rehome(out)
                    continue
                f = ch["f"] if ch["stage"] == 0 else ch["creep"]
                step = max(1, int(round(f * SCAN)))
                self.put(pos_d, pos - step, True)


# ---------------------------------------------------------------- plant
class Plant:
    """X/Y: true position = offset + counts/scale.  Z: 0 = up, 100 = end."""
    PPMM = {"Y0": 100.0, "Y2": 33.333}
    Z_SPEED = 300.0          # mm/s
    Z_SAFE = (25.0, 32.0)    # sensor window mm
    Z_SURFACE = 90.0         # pad touches surface
    Z_DOWN = 95.0            # pad compressed -> DOWN sensor
    DOG = (-3.0, 2.0)        # home target window (mm, true position)

    def __init__(self, plc, x0=300.0, y0=200.0):
        self.plc = plc
        self.off = {"Y0": x0, "Y2": y0}   # true pos when counts = 0
        self.z = 60.0                      # pad half down at power-up
        self.valve_down = False
        self.t = 0.0
        self.violations = []
        self.prints = 0
        self.pedal_until = -1
        self.hb = 0.0
        self.clock0 = 10 * 3600 + 30 * 60     # 10:30 -> shift 1

    def rehome(self, out):
        # counts were zeroed when DOG turned off at true = DOG[0]
        self.off[out] = self.DOG[0]

    def true_pos(self, out):
        return self.off[out] + self.plc.val(Plc_pos(out), True) / self.PPMM[out]

    def inputs(self):
        b = self.plc.bits
        x, y = self.true_pos("Y0"), self.true_pos("Y2")
        b["X0"] = self.DOG[0] <= x <= self.DOG[1]
        b["X1"] = self.DOG[0] <= y <= self.DOG[1]
        b["X2"] = self.z <= 2.0
        b["X20"] = self.Z_SAFE[0] <= self.z <= self.Z_SAFE[1]
        b["X3"] = self.z >= self.Z_DOWN - 0.5
        for n in ("X4", "X5", "X6", "X7", "X10", "X13", "X15", "X16"):
            b[n] = True
        b["X11"] = self.t < self.pedal_until
        clk = self.clock0 + self.t * getattr(self, "clock_speed", 1.0)
        w = self.plc.words
        w["D1314"] = int(clk // 60) % 60
        w["D1315"] = int(clk // 3600) % 24
        w["D1316"], w["D1317"], w["D1319"] = 28, 9, 26

    def step(self):
        b = self.plc.bits
        if b["Y4"] and not b["Y5"]:
            self.valve_down = True
        if b["Y5"] and not b["Y4"]:
            self.valve_down = False
        if getattr(self, "fault_down", False):
            self.valve_down = True      # simulated valve / air fault
        tgt = self.Z_DOWN if self.valve_down else 0.0
        dz = self.Z_SPEED * SCAN
        self.z = min(tgt, self.z + dz) if tgt > self.z else max(tgt, self.z - dz)
        self.t += SCAN
        self.hb += SCAN
        if self.hb >= 0.5:
            self.hb = 0
            self.plc.words["D60"] = s16(self.plc.words["D60"] + 1)
        self.check()

    def check(self):
        b = self.plc.bits
        x_moving = b["M1336"]
        y_moving = b["M1337"]
        x = self.true_pos("Y0")
        in_zone = x <= 250.0 + 5
        if x_moving and self.z > self.Z_SAFE[1] + 0.5:
            self.violations.append((round(self.t, 3), "X moving with pad below safe height",
                                    round(self.z, 1)))
        if x_moving and self.z >= self.Z_SURFACE:
            self.violations.append((round(self.t, 3), "pad on surface while X moving"))
        if y_moving and in_zone and self.z > self.Z_SAFE[1] + 0.5:
            self.violations.append((round(self.t, 3), "cup moving under lowered pad"))


def Plc_pos(out):
    return "D1030" if out == "Y0" else "D1336"


# ---------------------------------------------------------------- runner
class Sim:
    def __init__(self):
        self.plc = PLC(IL_PATH)
        self.plant = Plant(self.plc)

    def run(self, seconds, until=None):
        n = int(seconds / SCAN)
        for _ in range(n):
            self.plant.inputs()
            self.plc.scan()
            self.plc.pulse_step(self.plant)
            self.plant.step()
            if until and until():
                return True
        return False

    def cmd(self, bit):
        self.plc.bits[bit] = True

    def pedal(self):
        self.plant.pedal_until = self.plant.t + 0.1

    def w(self, d, dbl=False):
        return self.plc.val(d, dbl)


def scenario(name, options, cycles=5, pedal=True, lead=None, mode=None, n=None):
    s = Sim()
    p = s.plc
    s.run(0.1)
    p.bits["M508"] = False              # these scenarios run without login
    for m, v in options.items():
        p.bits[m] = v
    if mode is not None:
        p.put("D554", mode)
    if n is not None:
        p.put("D555", n)
    if lead is not None:
        p.put("D550", int(lead * 10), True)
    ok = []
    # homing
    s.cmd("M103")
    homed = s.run(20, until=lambda: p.bits["M24"] and s.w("D2") == 0)
    ok.append(("homing", homed))
    # auto
    p.bits["M120"] = True
    s.cmd("M100")
    s.run(0.2)
    start_count = s.w("D560", True)
    t0 = s.plant.t
    done = 0
    for _ in range(cycles * 400):
        if pedal and s.w("D0") == 10 and not p.bits["M94"] and s.plant.t > s.plant.pedal_until + 0.2:
            s.pedal()
            s.pedals = getattr(s, "pedals", 0) + 1
        s.run(0.05)
        done = s.w("D560", True) - start_count
        if done >= cycles or p.bits["M21"]:
            break
    dt = s.plant.t - t0
    s.pedals = getattr(s, "pedals", 0)
    alarms = [i for i in range(200, 217) if p.bits["M%d" % i]]
    ok.append(("%d prints" % cycles, done >= cycles))
    ok.append(("no alarms", not alarms))
    ok.append(("no collisions", not s.plant.violations))
    interval = s.w("D566", True) * 0.01
    print("== %s ==" % name)
    for k, v in ok:
        print("   %-14s %s" % (k, "OK" if v else "FAIL"))
    print("   prints=%d pedals=%d in %.1fs, last print interval %.2fs, alarms=%s"
          % (done, s.pedals, dt, interval, ["A%02d" % (i - 199) for i in alarms]))
    for v in s.plant.violations[:5]:
        print("   VIOLATION", v)
    return all(v for _, v in ok), s


def interlock_test():
    """Force the pad down while X moves: A10 must stop X immediately."""
    s = Sim()
    p = s.plc
    s.run(0.1)
    p.bits["M508"] = False
    s.cmd("M103")
    s.run(20, until=lambda: p.bits["M24"] and s.w("D2") == 0)
    s.run(0.1)
    s.cmd("M111")                               # manual: X -> print
    s.run(0.3)
    moving = p.bits["M1336"]
    s.plant.fault_down = True                   # air/valve fault drops pad
    s.run(0.5)
    stopped = not p.bits["M1336"]
    a10 = p.bits["M209"]
    print("== interlock: pad drops while X moves ==")
    print("   X was moving %s, A10 raised %s, X stopped %s"
          % (moving, a10, stopped))
    return moving and a10 and stopped


def operators_test():
    """Login, per-operator counting, session log, shift change."""
    s = Sim()
    p = s.plc
    s.run(0.1)
    p.put("D3000", 1234); p.put("D3001", 5678)       # registry
    s.cmd("M103")
    s.run(20, until=lambda: p.bits["M24"] and s.w("D2") == 0)
    p.bits["M120"] = True
    checks = []
    s.cmd("M100"); s.run(0.3)
    checks.append(("start blocked without login", not p.bits["M90"] and p.bits["M137"]))
    p.put("D600", 9999); s.cmd("M130"); s.run(0.1)
    checks.append(("unknown code rejected", p.bits["M133"] and not p.bits["M132"]))
    p.put("D600", 1234); s.cmd("M130"); s.run(0.1)
    checks.append(("operator 1234 logged in", p.bits["M132"] and s.w("D601") == 1234))

    def prints(n):
        start = s.w("D560", True)
        s.cmd("M100"); s.run(0.2)
        t_end = s.plant.t + 60
        while s.w("D560", True) - start < n and s.plant.t < t_end:
            if s.w("D0") == 10 and not p.bits["M94"] and s.plant.t > s.plant.pedal_until + 0.2:
                s.pedal()
            s.run(0.05)
        s.cmd("M101"); s.run(3)
    prints(3)
    checks.append(("3 prints on 1234 this shift", s.w("D616") == 3))
    p.put("D600", 5678); s.cmd("M130"); s.run(0.1)
    rec0 = [s.w("D%d" % (3100 + i)) for i in range(8)]
    checks.append(("record written for 1234 (3 prints)", rec0[0] == 1234 and rec0[6] == 3 and rec0[1] == 1))
    prints(2)
    checks.append(("2 prints on 5678", s.w("D616") == 2))
    s.plant.clock0 += 4 * 3600           # jump to 14:30 -> shift 2
    s.run(0.2)
    rec1 = [s.w("D%d" % (3110 + i)) for i in range(9)]
    checks.append(("shift change closed 5678 session", rec1[0] == 5678 and rec1[6] == 2 and rec1[8] == 2))
    checks.append(("new shift 2, counters cleared", s.w("D602") == 2 and s.w("D616") == 0))
    checks.append(("live block operator/shift", s.w("D3081") == 5678 and s.w("D3082") == 2))
    s.cmd("M131"); s.run(0.1)
    checks.append(("logout", not p.bits["M132"] and s.w("D601") == 0 and s.w("D3093") == 3))
    alarms = [i for i in range(200, 217) if p.bits["M%d" % i]]
    checks.append(("no alarms / collisions", not alarms and not s.plant.violations))
    print("== operators, shifts, session log ==")
    for k, v in checks:
        print("   %-38s %s" % (k, "OK" if v else "FAIL"))
    return all(v for _, v in checks)


if __name__ == "__main__":
    results = []
    results.append(scenario("basic (serial, no overlap)", {"M500": False, "M506": False, "M507": False})[0])
    results.append(scenario("parallel inking", {"M500": True, "M506": False, "M507": False})[0])
    results.append(scenario("parallel inking + early Z (default lead 5 mm)", {"M500": True, "M506": False, "M507": True})[0])
    results.append(scenario("all options + pre-pick", {"M500": True, "M506": True, "M507": True})[0])
    ok, sm = scenario("mode 1: one pedal = 3 prints (multi-hit)", {"M500": True, "M506": False, "M507": False}, cycles=6, mode=1, n=3)
    ratio_ok = ok and sm.pedals == 2
    print("   expected 2 pedals for 6 prints: %s" % ratio_ok)
    results.append(ratio_ok)
    results.append(scenario("mode 2: continuous, no pedal", {"M500": True, "M506": False, "M507": False}, cycles=4, mode=2, pedal=False)[0])
    print("\n(next scenario is EXPECTED to stop with A10 - FAIL lines are normal)")
    ok30, s30 = scenario("early Z lead 30 mm (too long: must alarm, not crash)",
                         {"M500": True, "M506": False, "M507": True}, lead=30)
    a10 = s30.plc.bits["M209"] or s30.plc.bits["M216"]
    print("   expected A10/A17 raised: %s" % a10)
    results.append(a10)
    results.append(interlock_test())
    results.append(operators_test())
    print("\nALL PASS" if all(results) else "\nSOME FAILED")
    sys.exit(0 if all(results) else 1)
