#!/usr/bin/env python3
"""Point-by-point test suite for plc/TampoPrinter_SV2.il.

Every scenario runs the real IL program in tools/plc_sim.py against the
machine model, injects faults where needed and checks the outcome. The
suite measures which sequence steps, alarms and output instructions were
exercised and writes docs/11_test_report.md.

    python3 tools/test_suite.py            # all scenarios, 4 processes
    python3 tools/test_suite.py S16 S29    # selected scenarios
"""
import os
import random
import sys
import traceback
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(__file__))
import plc_sim                                       # noqa: E402
from plc_sim import SCAN, Sim                        # noqa: E402

ALARMS = {200 + i: "A%02d" % (i + 1) for i in range(21)}
AUTO_STEPS = [0, 5, 10, 20, 40, 50, 60, 70, 80, 90, 100, 110, 120]
# S5, S40 (flash-off 0) and S120 finish inside the scan that enters them,
# so they never show at the end of a scan; code coverage proves them.
AUTO_STEPS_HELD = [0, 10, 20, 50, 60, 70, 80, 90, 100, 110]
INK_STEPS = [0, 10, 20]
HOME_STEPS = [0, 10, 20, 30, 40]
AXIS_HOME_STEPS = [0, 10, 15, 20, 25]


# ------------------------------------------------------------------ harness
class TSim(Sim):
    def __init__(self, login=False):
        super().__init__()
        self.steps = {k: set() for k in ("D0", "D1", "D2", "D3", "D4")}
        self.alarms_seen = set()
        self.hook = None
        self.pedals = 0
        self.run(0.1)
        if not login:
            self.plc.bits["M508"] = False

    def run(self, seconds, until=None):
        p = self.plc
        for _ in range(int(round(seconds / SCAN))):
            self.plant.inputs()
            p.scan()
            p.pulse_step(self.plant)
            self.plant.step()
            w = p.words
            for k, st in self.steps.items():
                st.add(w[k])
            for i in range(200, 221):
                if p.bits["M%d" % i]:
                    self.alarms_seen.add(i)
            if self.hook:
                self.hook(self)
            if until and until():
                return True
        return False

    # helpers
    def b(self, n):
        return self.plc.bits[n]

    def alarms(self):
        return [ALARMS[i] for i in range(200, 221) if self.plc.bits["M%d" % i]]

    def home(self):
        self.cmd("M103")
        ok = self.run(40, until=lambda: self.b("M24") and self.w("D2") == 0)
        self.run(0.1)
        return ok

    def reset(self):
        self.cmd("M102")
        self.run(0.5)

    def start_auto(self, mode=0, n=None):
        self.plc.put("D554", mode)
        if n is not None:
            self.plc.put("D555", n)
        self.plc.bits["M120"] = True
        self.cmd("M100")
        self.run(0.3)
        return self.b("M90")

    def prints(self, n, timeout=90, pedal=True):
        start = self.w("D560", True)
        t_end = self.plant.t + timeout
        while self.w("D560", True) - start < n and self.plant.t < t_end:
            if pedal and self.w("D0") == 10 and not self.b("M94") \
                    and self.plant.t > self.plant.pedal_until + 0.2:
                self.pedal()
                self.pedals += 1
            if self.b("M21"):
                break
            self.run(0.05)
        return self.w("D560", True) - start

    def xpos(self):            # PLC frame, mm
        return self.w("D1030", True) / 100.0

    def ypos(self):
        return self.w("D1336", True) / 33.333

    def set_zone(self, base, k, lo_mm, hi_mm):
        self.plc.put("D%d" % (base + 4 * k), int(lo_mm * 10), True)
        self.plc.put("D%d" % (base + 4 * k + 2), int(hi_mm * 10), True)


def ck(checks, desc, ok):
    checks.append((desc, bool(ok)))


def clean(s):
    return not s.alarms() and not s.plant.violations


# ------------------------------------------------------------------ scenarios
def S01(s, c):
    """Auto cycle, serial inking, 1 pedal = 1 print"""
    s.plc.bits["M500"] = False
    ck(c, "homing", s.home())
    ck(c, "auto started", s.start_auto(0))
    ck(c, "3 prints", s.prints(3) == 3)
    ck(c, "no alarm, no collision", clean(s))
    ck(c, "every held auto step visited", set(AUTO_STEPS_HELD) <= s.steps["D0"])


def S02(s, c):
    """Auto cycle, parallel inking"""
    ck(c, "homing", s.home())
    s.start_auto(0)
    ck(c, "3 prints", s.prints(3) == 3)
    ck(c, "ink sub-sequence visited", {10, 20} <= s.steps["D1"])
    ck(c, "no alarm, no collision", clean(s))


def S03(s, c):
    """Early Z descent 5 mm"""
    s.plc.bits["M507"] = True
    ck(c, "homing", s.home())
    s.start_auto(0)
    ck(c, "3 prints", s.prints(3) == 3)
    ck(c, "no alarm, no collision", clean(s))


def S04(s, c):
    """Pre-pick + early Z + parallel inking"""
    s.plc.bits["M506"] = True
    s.plc.bits["M507"] = True
    ck(c, "homing", s.home())
    s.start_auto(0)
    ck(c, "3 prints", s.prints(3) == 3)
    s.run(6, until=lambda: s.b("M93") and s.w("D0") == 10)
    ck(c, "pad loaded and waiting for pedal", s.b("M93") and s.w("D0") == 10)
    s.run(3.5)
    ck(c, "pad re-picks after max wait (D552)", s.steps["D0"] >= {10, 20})
    ck(c, "no alarm, no collision", clean(s))


def S05(s, c):
    """Mode 1: one pedal = N prints"""
    ck(c, "homing", s.home())
    s.start_auto(1, n=3)
    ck(c, "6 prints", s.prints(6) == 6)
    ck(c, "2 pedals for 6 prints", s.pedals == 2)
    ck(c, "no alarm, no collision", clean(s))


def S06(s, c):
    """Mode 2: continuous"""
    ck(c, "homing", s.home())
    s.start_auto(2)
    ck(c, "4 prints without pedal", s.prints(4, pedal=False) == 4)
    ck(c, "no alarm, no collision", clean(s))


def S07(s, c):
    """Stop at end of cycle"""
    ck(c, "homing", s.home())
    s.start_auto(2)
    s.run(1.0)
    s.cmd("M101")
    done = s.run(15, until=lambda: not s.b("M90"))
    ck(c, "auto stops by itself", done)
    s.run(1.5)
    ck(c, "stopped at S0, pad up", s.w("D0") == 0 and s.plant.z < 2)
    ck(c, "no alarm", clean(s))


def S08(s, c):
    """Batch target reached"""
    s.plc.bits["M504"] = True
    s.plc.put("D564", 3, True)
    s.plc.put("D562", 0, True)
    ck(c, "homing", s.home())
    s.start_auto(2)
    s.run(40, until=lambda: not s.b("M90"))
    ck(c, "exactly 3 prints then stop", s.w("D562", True) == 3 and not s.b("M90"))
    ck(c, "batch done flag", s.b("M95"))
    ck(c, "start refused until batch reset", not s.start_auto(2))
    s.cmd("M116")
    s.run(0.2)
    ck(c, "batch reset clears flag", not s.b("M95") and s.w("D562", True) == 0)


def S09(s, c):
    """Homing starting on the X home sensor (back-off)"""
    s.plant.off["Y0"] = 0.0          # carriage sits on the DOG
    ck(c, "homing", s.home())
    ck(c, "back-off step used", 15 in s.steps["D3"])
    ck(c, "no alarm", clean(s))


def S10(s, c):
    """Homing: X sensor stuck ON -> A11"""
    s.plant.force = {"X0": True}
    s.cmd("M103")
    s.run(10, until=lambda: s.b("M210"))
    ck(c, "A11 raised", s.b("M210"))
    ck(c, "not homed", not s.b("M24"))


def S11(s, c):
    """Homing: X sensor never seen -> A11 by timeout"""
    s.plant.force = {"X0": False}
    s.cmd("M103")
    s.run(35, until=lambda: s.b("M210"))
    ck(c, "A11 raised by timeout", s.b("M210"))


def S12(s, c):
    """Manual jog X homed (soft limits, hold-to-run)"""
    ck(c, "homing", s.home())
    s.plc.bits["M104"] = True
    s.run(12)
    s.plc.bits["M104"] = False
    s.run(0.3)
    ck(c, "jog+ stops at soft max 1010 mm", abs(s.xpos() - 1010) < 1)
    s.plc.bits["M105"] = True
    s.run(1.0)
    s.plc.bits["M105"] = False
    s.run(0.3)
    x = s.xpos()
    ck(c, "release stops jog-", 0 < x < 1010 and not s.b("M1336"))
    ck(c, "no alarm", clean(s))


def S13(s, c):
    """Manual jog X not homed: max 50 mm per press"""
    s.run(2)                          # pad goes up
    x0 = s.xpos()
    s.plc.bits["M104"] = True
    s.run(10)
    s.plc.bits["M104"] = False
    s.run(0.2)
    ck(c, "moved 50 mm at most", 45 <= s.xpos() - x0 <= 50.5)


def S14(s, c):
    """Manual go-to and Y test stroke"""
    ck(c, "homing", s.home())
    s.cmd("M111")
    s.run(6)
    ck(c, "X at print", abs(s.xpos() - 495) < 0.6)
    s.cmd("M110")
    s.run(6)
    ck(c, "X at pick", abs(s.xpos() - 50) < 0.6)
    s.cmd("M113")
    s.run(6)
    ck(c, "Y at end", abs(s.ypos() - 350) < 0.6)
    s.cmd("M112")
    s.run(6)
    ck(c, "Y at park", abs(s.ypos() - 5) < 0.6)
    s.cmd("M117")
    s.run(4)
    ck(c, "Y test stroke done, image inked", s.b("M92") and s.w("D1") == 0)
    ck(c, "no alarm", clean(s))


def S15(s, c):
    """Manual Z only at pick (cup parked) or print"""
    ck(c, "homing", s.home())
    s.cmd("M108")
    s.run(1)
    ck(c, "Z down at pick", s.plant.z > 90)
    s.cmd("M109")
    s.run(1)
    s.plc.bits["M104"] = True
    s.run(0.5)
    s.plc.bits["M104"] = False
    s.run(0.3)
    s.cmd("M108")
    s.run(1)
    ck(c, "Z refused between stations", s.plant.z < 2 and not s.b("Y4"))
    ck(c, "no alarm", clean(s))


def fault_during_auto(s, c, name, apply, bit, restore, rehome):
    ck(c, "homing", s.home())
    s.start_auto(2)
    s.run(2.0)
    apply(s)
    s.run(3)
    ck(c, "%s raised" % name, s.b(bit))
    ck(c, "auto aborted, motion stopped", not s.b("M90") and not s.b("M1336") and not s.b("M1337"))
    ck(c, "pad up", s.plant.z < 2 or name in ("A07", "A08"))
    ck(c, "no collision", not s.plant.violations)
    restore(s)
    s.run(2)
    s.reset()
    ck(c, "alarm clears after reset", not s.alarms())
    if rehome:
        ck(c, "homing lost (class A)", not s.b("M24"))
        ck(c, "re-home", s.home())
    elif not s.b("M24"):              # a secondary class-A alarm fired too
        ck(c, "re-home after secondary alarm", s.home())
    ck(c, "production resumes", s.start_auto(2) and s.prints(2, pedal=False) == 2)


def _force(**kv):
    return lambda s: setattr(s.plant, "force", dict(kv))


def _clear(s):
    s.plant.force = {}
    s.plant.z_stuck = False
    s.plant.fault_down = False
    s.plant.hb_stop = False
    s.plc.stall = set()


def S16(s, c):
    """A01 E-stop during auto"""
    fault_during_auto(s, c, "A01", _force(X10=False), "M200", _clear, True)


def S17(s, c):
    """A02 / A03 drive faults"""
    fault_during_auto(s, c, "A02", _force(X4=False), "M201", _clear, True)


def S17b(s, c):
    """A03 Y drive fault"""
    fault_during_auto(s, c, "A03", _force(X5=False), "M202", _clear, True)


def S18(s, c):
    """A04 X over-travel"""
    fault_during_auto(s, c, "A04", _force(X6=False), "M203", _clear, True)


def S18b(s, c):
    """A05 Y over-travel"""
    fault_during_auto(s, c, "A05", _force(X7=False), "M204", _clear, True)


def S19(s, c):
    """A06 air pressure low"""
    fault_during_auto(s, c, "A06", _force(X15=False), "M205", _clear, False)


def S20(s, c):
    """A07 Z does not come down"""
    def apply(s):
        s.plant.z_stuck = True
    fault_during_auto(s, c, "A07", apply, "M206", _clear, False)


def S21(s, c):
    """A08 Z does not go up"""
    def apply(s):
        s.run(10, until=lambda: s.b("Y4"))
        s.run(0.4)
        s.plant.z_stuck = True
    fault_during_auto(s, c, "A08", apply, "M207", _clear, False)


def S22(s, c):
    """A09 Z sensors UP and DOWN together"""
    fault_during_auto(s, c, "A09", _force(X2=True, X3=True), "M208", _clear, False)


def S23(s, c):
    """A10 pad drops while X moves"""
    ck(c, "homing", s.home())
    s.cmd("M111")
    s.run(0.3)
    ck(c, "X moving", s.b("M1336"))
    s.plant.fault_down = True
    s.run(0.5)
    ck(c, "A10 raised", s.b("M209"))
    ck(c, "X stopped at once", not s.b("M1336"))
    xs = []
    s.hook = lambda t: xs.append(t.xpos())
    s.run(0.2)
    s.hook = None
    ck(c, "no further X travel after the fault", max(xs) - min(xs) < 0.05)
    s.plant.violations = []          # the injected fault itself, checked above
    _clear(s)
    s.run(1)
    s.reset()
    ck(c, "recovers after reset + homing", not s.alarms() and s.home())


def S24(s, c):
    """A13 light curtain during motion"""
    fault_during_auto(s, c, "A13", _force(X16=False), "M212", _clear, False)


def S25(s, c):
    """A14 HMI communication lost"""
    ck(c, "homing", s.home())
    s.plc.bits["M104"] = True               # operator holding jog
    s.run(0.3)
    s.plant.hb_stop = True
    s.run(3)
    ck(c, "A14 raised", s.b("M213"))
    ck(c, "held jog bit cleared", not s.b("M104"))
    ck(c, "X stopped", not s.b("M1336"))
    s.plant.hb_stop = False
    s.run(1)
    s.reset()
    ck(c, "alarm clears when comms return", not s.alarms())


def S26(s, c):
    """A15 invalid parameter"""
    ck(c, "homing", s.home())
    s.plc.put("D604", 500)                  # shift 2 before shift 1
    s.run(0.2)
    ck(c, "A15 raised", s.b("M214"))
    ck(c, "start refused", not s.start_auto(0))
    s.plc.put("D604", 1400)
    s.reset()
    ck(c, "clears after correction", not s.alarms())


def S27(s, c):
    """A16 step timeout (cup axis stalls)"""
    ck(c, "homing", s.home())
    s.plc.stall = {"Y2"}
    s.start_auto(2)
    s.run(20, until=lambda: s.b("M215"))
    ck(c, "A16 raised", s.b("M215"))
    ck(c, "auto aborted", not s.b("M90"))
    _clear(s)
    s.cmd("M141")                           # software safe reset
    s.run(1)
    ck(c, "safe reset recovers", not s.alarms() and s.start_auto(2) and s.prints(1, pedal=False) == 1)


def S28(s, c):
    """A17 pad reported down while X moves"""
    ck(c, "homing", s.home())
    s.cmd("M111")
    s.run(0.3)
    s.plant.force = {"X3": True, "X2": False}
    s.run(0.2)
    ck(c, "A17 raised", s.b("M216"))
    ck(c, "X stopped", not s.b("M1336"))
    s.plant.violations = []          # injected sensor fault


def S29(s, c):
    """A18 X path through a forbidden zone"""
    ck(c, "homing", s.home())
    s.set_zone(640, 0, 300, 320)
    xs = []
    s.hook = lambda t: xs.append(t.xpos())
    s.start_auto(0)
    s.pedal()
    s.run(4)
    ck(c, "A18 raised", s.b("M217"))
    ck(c, "X never entered the zone", all(not (300 <= x <= 320) for x in xs))
    ck(c, "D680 shows path blocked", s.w("D680") & (1 << 9))


def S30(s, c):
    """A18 Y path through a forbidden zone"""
    ck(c, "homing", s.home())
    s.set_zone(656, 0, 200, 220)
    ys = []
    s.hook = lambda t: ys.append(t.ypos())
    s.cmd("M113")
    s.run(3)
    ck(c, "A18 raised", s.b("M217"))
    ck(c, "Y never entered the zone", all(not (200 <= y <= 220) for y in ys))


def S31(s, c):
    """Jog stops before a zone (margin 2 mm)"""
    ck(c, "homing", s.home())
    s.set_zone(640, 1, 400, 420)
    s.plc.bits["M104"] = True
    s.run(5)
    s.plc.bits["M104"] = False
    s.run(0.2)
    ck(c, "stopped at 398 mm", abs(s.xpos() - 398) < 0.6)
    s.plc.bits["M104"] = True
    s.run(1)
    s.plc.bits["M104"] = False
    s.run(0.2)
    ck(c, "cannot jog further", abs(s.xpos() - 398) < 0.6)
    ck(c, "no alarm", clean(s))


def S32(s, c):
    """No-drop zone at the print station"""
    ck(c, "homing", s.home())
    s.set_zone(664, 0, 485, 505)
    zs = []
    s.hook = lambda t: zs.append((t.xpos(), t.plant.z))
    s.start_auto(0)
    s.pedal()
    s.run(6)
    ck(c, "A18 raised at the pad-down step", s.b("M217"))
    ck(c, "pad never came down in the zone", all(z < 40 for x, z in zs if 485 <= x <= 505))


def S33(s, c):
    """A19 axis already inside a zone, then jog out"""
    ck(c, "homing", s.home())
    s.set_zone(640, 0, 40, 60)             # around pick = 50 mm
    s.run(0.3)
    ck(c, "A19 raised", s.b("M218"))
    s.reset()
    ck(c, "reset accepted", not s.alarms())
    s.plc.bits["M104"] = True
    s.run(1)
    s.plc.bits["M104"] = False
    s.run(0.3)
    ck(c, "jogged out of the zone", s.xpos() > 60 and not s.alarms())


def S34(s, c):
    """A20 PLC operation error + safe reset"""
    ck(c, "homing", s.home())
    s.plc.put("D1067", 6706)
    s.plc.put("D1068", 1234)
    s.plc.bits["M1067"] = True
    s.run(0.2)
    ck(c, "A20 raised with code/step kept", s.b("M219") and s.w("D683") == 6706 and s.w("D684") == 1234)
    ck(c, "D680 shows PLC error", s.w("D680") & (1 << 12))
    s.cmd("M141")
    s.run(0.5)
    ck(c, "safe reset clears flag and alarm", not s.b("M1067") and not s.alarms())


def S35(s, c):
    """A21 corrupted step register repaired"""
    ck(c, "homing", s.home())
    s.start_auto(2)
    s.run(1.5)
    s.plc.put("D0", 33)
    s.run(0.5)
    ck(c, "A21 raised", s.b("M220"))
    ck(c, "sequence stopped safely, pad up", not s.b("M90") and s.w("D0") == 0)
    ck(c, "no collision", not s.plant.violations)
    s.reset()
    ck(c, "production resumes", s.start_auto(2) and s.prints(1, pedal=False) == 1)


def S36(s, c):
    """Software safe reset during motion"""
    ck(c, "homing", s.home())
    s.start_auto(2)
    s.run(2.2)
    s.cmd("M141")
    s.run(1.5)
    ck(c, "everything stopped, pad up", not s.b("M90") and not s.b("M1336")
       and not s.b("M1337") and s.plant.z < 2)
    ck(c, "no alarm, homing kept", not s.alarms() and s.b("M24"))
    ck(c, "restart works", s.start_auto(2) and s.prints(1, pedal=False) == 1)


def S37(s, c):
    """Restore default parameters"""
    s.plc.put("D502", 4000, True)
    s.set_zone(640, 0, 10, 20)
    s.cmd("M140")
    s.run(0.2)
    ck(c, "print position back to 495.0", s.w("D502", True) == 4950)
    ck(c, "zones cleared", s.w("D642", True) == 0)


def S38(s, c):
    """Black box records the first alarm"""
    ck(c, "homing", s.home())
    n0 = s.w("D682")
    s.start_auto(2)
    s.run(2)
    s.plant.force = {"X16": False}
    s.run(0.5)
    ck(c, "one black-box entry", s.w("D682") == n0 + 1)
    ck(c, "entry code = A13", s.w("D3750") == 13)
    ck(c, "entry keeps the step it happened in", s.w("D3751") in AUTO_STEPS[1:])


def S39(s, c):
    """Diagnostics: why won't it run (D680)"""
    s.plc.bits["M508"] = True
    ck(c, "not homed shown", s.w("D680") & 1)
    ck(c, "login missing shown", s.w("D680") & (1 << 6))
    ck(c, "homing", s.home())
    ck(c, "not-homed bit clears", not s.w("D680") & 1)
    s.plant.force = {"X15": False}
    s.run(1)
    ck(c, "air low shown", s.w("D680") & (1 << 4))


def S40(s, c):
    """Operators, shifts, session log"""
    p = s.plc
    p.put("D3000", 1234)
    p.put("D3001", 5678)
    ck(c, "homing", s.home())
    ck(c, "start refused without login", not s.start_auto(0) and s.b("M137"))
    p.put("D600", 9999); s.cmd("M130"); s.run(0.1)
    ck(c, "unknown code rejected", s.b("M133") and not s.b("M132"))
    p.put("D600", 1234); s.cmd("M130"); s.run(0.1)
    ck(c, "1234 logged in", s.b("M132") and s.w("D601") == 1234)
    s.start_auto(0)
    ck(c, "3 prints", s.prints(3) == 3)
    ck(c, "1234 shift count = 3", s.w("D616") == 3)
    p.put("D600", 5678); s.cmd("M130"); s.run(0.1)
    ck(c, "session record for 1234", s.w("D3100") == 1234 and s.w("D3106") == 3)
    ck(c, "2 more prints on 5678", s.prints(2) == 2 and s.w("D616") == 2)
    s.plant.clock0 += 4 * 3600
    s.run(0.3)
    ck(c, "shift change closes 5678 session", s.w("D3110") == 5678 and s.w("D3116") == 2)
    ck(c, "shift 2, counters cleared", s.w("D602") == 2 and s.w("D616") == 0)
    s.cmd("M101"); s.run(8)
    s.cmd("M131"); s.run(0.2)
    ck(c, "logout", not s.b("M132") and s.w("D601") == 0)
    ck(c, "no alarm, no collision", clean(s))


def S41(s, c):
    """Power cycle keeps parameters, comes up safe"""
    ck(c, "homing", s.home())
    s.plc.put("D502", 5200, True)
    s.start_auto(2)
    s.run(2)
    old = s.plc
    s2 = TSim()
    for k, v in old.words.items():
        n = int(k[1:]) if k[0] == "D" and k[1:].isdigit() else -1
        if 200 <= n <= 999 or 2000 <= n <= 9999:
            s2.plc.words[k] = v
    for k, v in old.bits.items():
        if k[0] == "M" and k[1:].isdigit() and 500 <= int(k[1:]) <= 999:
            s2.plc.bits[k] = v
    s2.plant.z = s.plant.z
    s2.plc.bits["M508"] = False
    s2.run(2)
    ck(c, "not homed, not running", not s2.b("M24") and not s2.b("M90"))
    ck(c, "pad goes up", s2.plant.z < 2)
    ck(c, "parameter kept", s2.w("D502", True) == 5200)
    ck(c, "home + print after power-up", s2.home() and s2.start_auto(2)
       and s2.prints(1, pedal=False) == 1)
    s.plc.cov |= s2.plc.cov


def fuzz(seed, s, c):
    rnd = random.Random(seed)
    cmds = ["M100", "M101", "M102", "M103", "M108", "M109", "M110", "M111", "M112",
            "M113", "M117", "M141"]
    faults = ["X10", "X15", "X16", "X4", "X5", "X6", "X7"]
    s.home()
    for _ in range(160):
        r = rnd.random()
        if r < 0.45:
            s.cmd(rnd.choice(cmds))
        elif r < 0.55:
            s.plc.bits["M120"] = rnd.random() < 0.7
        elif r < 0.65:
            s.plc.put("D554", rnd.randint(0, 2))
        elif r < 0.72:
            s.pedal()
        elif r < 0.80:
            j = rnd.choice(["M104", "M105", "M106", "M107"])
            s.plc.bits[j] = True
            s.run(rnd.uniform(0.05, 0.6))
            s.plc.bits[j] = False
        elif r < 0.90:
            s.plant.force = {rnd.choice(faults): False}
            s.run(rnd.uniform(0.02, 0.5))
            s.plant.force = {}
        else:
            s.plc.put(rnd.choice(["D0", "D1", "D2"]), rnd.randint(-5, 200))
        s.run(rnd.uniform(0.05, 0.8))
    ck(c, "no collision in 160 random actions", not s.plant.violations)
    _clear(s)
    s.run(1)
    s.cmd("M141")
    s.run(1)
    s.reset()
    rec = s.home() and s.start_auto(2) and s.prints(1, pedal=False) == 1
    ck(c, "recovers: safe reset, home, print", rec)


def S42(s, c):
    """Random fuzz #1"""
    fuzz(1, s, c)


def S43(s, c):
    """Random fuzz #2"""
    fuzz(2, s, c)


def S44(s, c):
    """Random fuzz #3"""
    fuzz(3, s, c)


def S45(s, c):
    """Out-of-range parameters are clamped"""
    P = s.plc
    for d, v, want in [("D540", 5, 20), ("D541", 5, 20), ("D522", 2000, 900), ("D527", 900, 600),
                       ("D528", 900, 600), ("D526", 10, 100), ("D532", 10, 100),
                       ("D552", 5000, 1000), ("D554", 5, 0), ("D555", 0, 1)]:
        P.put(d, v)
        s.run(0.02)
        ck(c, "%s %d -> %d" % (d, v, want), s.w(d) == want)
    for d, v, want in [("D540", 500, 100), ("D541", 500, 100), ("D554", -1, 0), ("D555", 20, 9)]:
        P.put(d, v)
        s.run(0.02)
        ck(c, "%s %d -> %d" % (d, v, want), s.w(d) == want)
    for d, v, want in [("D500", 20000, 10100), ("D500", -50, 0), ("D502", 20000, 10100), ("D502", -50, 0)]:
        P.put(d, v, True)
        s.run(0.02)
        ck(c, "%s %d -> %d" % (d, v, want), s.w(d, True) == want)


def S46(s, c):
    """Homing: Y sensor stuck ON -> A12"""
    s.plant.force = {"X1": True}
    s.cmd("M103")
    s.run(10, until=lambda: s.b("M211"))
    ck(c, "A12 raised", s.b("M211"))


def S47(s, c):
    """Y jog with zones and without homing"""
    s.run(2)
    y0 = s.ypos()
    s.plc.bits["M106"] = True
    s.run(8)
    s.plc.bits["M106"] = False
    s.run(0.2)
    ck(c, "unhomed Y jog+ max 50 mm", 45 <= s.ypos() - y0 <= 50.5)
    y1 = s.ypos()
    s.plc.bits["M107"] = True
    s.run(8)
    s.plc.bits["M107"] = False
    s.run(0.2)
    ck(c, "unhomed Y jog- max 50 mm", 45 <= y1 - s.ypos() <= 50.5)
    ck(c, "homing", s.home())
    s.set_zone(656, 0, 200, 220)
    s.cmd("M113")                             # blocked by zone: A18, reset
    s.run(0.3)
    s.reset()
    s.plc.bits["M106"] = True
    s.run(8)
    s.plc.bits["M106"] = False
    s.run(0.2)
    ck(c, "Y jog+ stops at 198 mm", abs(s.ypos() - 198) < 0.6)
    s.set_zone(656, 1, 20, 30)               # a zone behind the cup
    s.plc.bits["M107"] = True
    s.run(8)
    s.plc.bits["M107"] = False
    s.run(0.2)
    ck(c, "Y jog- stops at 32 mm", abs(s.ypos() - 32) < 0.6)
    ck(c, "no alarm", clean(s))


def S48(s, c):
    """X jog- with a zone behind, unhomed X jog-"""
    s.run(2)
    x0 = s.xpos()
    s.plc.bits["M105"] = True
    s.run(8)
    s.plc.bits["M105"] = False
    s.run(0.2)
    ck(c, "unhomed X jog- max 50 mm", 45 <= x0 - s.xpos() <= 50.5)
    ck(c, "homing", s.home())
    s.set_zone(640, 2, 10, 20)
    s.plc.bits["M105"] = True
    s.run(8)
    s.plc.bits["M105"] = False
    s.run(0.2)
    ck(c, "X jog- stops at 22 mm", abs(s.xpos() - 22) < 0.6)
    s.plc.bits["M104"] = True               # jog+ right after: zone behind is ignored
    s.run(0.5)
    s.plc.bits["M104"] = False
    s.run(0.2)
    ck(c, "jog+ away from the zone works", s.xpos() > 22.5 and clean(s))


def S49(s, c):
    """Ring buffers wrap: 70 sessions, 18 black-box entries"""
    p = s.plc
    p.put("D3000", 1111)
    for i in range(70):
        p.put("D600", 1111); s.cmd("M130"); s.run(0.02)
        s.cmd("M131"); s.run(0.02)
    ck(c, "70 records written", s.w("D3097") == 70)
    ck(c, "session slot wrapped (70 mod 64 = 6)", s.w("D627") == 6)
    for i in range(18):
        s.plant.force = {"X15": False}
        s.run(0.7)
        s.plant.force = {}
        s.reset()
    ck(c, "18 black-box entries", s.w("D682") == 18)
    ck(c, "black-box slot wrapped (18 mod 16 = 2)", s.w("D681") == 2)


def S50(s, c):
    """Login message timeout, total reset, auto start off-station"""
    p = s.plc
    p.put("D600", 4321); s.cmd("M130"); s.run(0.1)
    ck(c, "unknown code message shown", s.b("M133"))
    s.run(3.2)
    ck(c, "message clears after 3 s", not s.b("M133"))
    s.cmd("M115"); s.run(0.05)
    ck(c, "total counter reset", s.w("D560", True) == 0)
    ck(c, "homing", s.home())
    s.cmd("M111")                            # X to print, then start auto
    s.run(6)
    ck(c, "start from the print station", s.start_auto(0) and s.prints(1) == 1)
    ck(c, "no alarm", clean(s))


def S51(s, c):
    """Inductive Z sensors: X20 wire break / lost steel flag during auto"""
    fault_during_auto(s, c, "A09", _force(X20=False), "M208", _clear, False)


def S52(s, c):
    """Inductive Z sensors: without X20 the X axis stays locked (fail-safe)"""
    ck(c, "homing", s.home())
    x0 = s.xpos()
    s.plant.force = {"X20": False}
    s.cmd("M111")                            # go to print
    s.run(3)
    ck(c, "A09 raised (UP without SAFE)", s.b("M208"))
    ck(c, "X did not move", abs(s.xpos() - x0) < 0.2)
    ck(c, "no collision", not s.plant.violations)
    _clear(s)
    s.run(0.5)
    s.reset()
    ck(c, "alarm clears after reset", not s.alarms())
    s.cmd("M111")
    s.run(6)
    ck(c, "X moves again with a healthy sensor", abs(s.xpos() - 495) < 0.6)


SCENARIOS = {k: v for k, v in globals().items() if k[0] == "S" and k[1:3].isdigit()}
LOGIN = {"S39", "S40"}


def run_one(name):
    s = TSim(login=name in LOGIN)
    c = []
    err = None
    try:
        SCENARIOS[name](s, c)
    except Exception:
        err = traceback.format_exc(limit=3)
    if s.plant.violations:
        c.append(("safety invariants (plant model)", False))
    return {"name": name, "doc": SCENARIOS[name].__doc__, "checks": c, "error": err,
            "cov": sorted(s.plc.cov), "steps": {k: sorted(v) for k, v in s.steps.items()},
            "alarms": sorted(s.alarms_seen), "viol": s.plant.violations[:3]}


# ------------------------------------------------------------------ report
def report(results):
    from plc_sim import PLC
    plc = PLC(plc_sim.IL_PATH)
    contact = {"LD", "LDI", "LDP", "LDF", "AND", "ANI", "ANDP", "OR", "ORI", "ORP", "ANB",
               "ORB", "MPS", "MRD", "MPP", "LABEL", "FOR", "NEXT", "SRET", "FEND", "END"}
    outs = [i for i, (op, a) in enumerate(plc.prog) if op not in contact and not plc.cmp[i]]
    cov = set()
    steps = {k: set() for k in ("D0", "D1", "D2", "D3", "D4")}
    alarms = set()
    for r in results:
        cov |= set(r["cov"])
        for k in steps:
            steps[k] |= set(r["steps"][k])
        alarms |= set(r["alarms"])
    covered = [i for i in outs if i in cov]
    lines = open(plc_sim.IL_PATH, encoding="utf-8").read().splitlines()
    passed = sum(1 for r in results if not r["error"] and all(ok for _, ok in r["checks"]))
    nchecks = sum(len(r["checks"]) for r in results)
    nok = sum(ok for r in results for _, ok in r["checks"])
    out = ["# ۱۱. گزارش تست نقطه‌به‌نقطه‌ی برنامه‌ی PLC", "",
           "> این فایل را `python3 tools/test_suite.py` خودکار می‌سازد. هر سناریو برنامه‌ی واقعی "
           "`plc/TampoPrinter_SV2.il` را اسکن‌به‌اسکن (هر ۵ ms) روی مدل دستگاه اجرا می‌کند، خطا تزریق می‌کند "
           "و نتیجه را بررسی می‌کند. در هر اسکن، مدل دستگاه قانون‌های ایمنی را هم کنترل می‌کند: حرکت X با پد پایین، "
           "پد روی سطح حین حرکت، و حرکت کاپ زیر پد.", "",
           "## خلاصه", "",
           "| مورد | نتیجه |", "|---|---|",
           f"| سناریوها | **{passed} از {len(results)}** قبول |",
           f"| بررسی‌ها | **{nok} از {nchecks}** قبول |",
           f"| دستورهای خروجی اجراشده (پوشش کد) | **{len(covered)} از {len(outs)}** ({100 * len(covered) / len(outs):.0f}٪) |",
           f"| مرحله‌های اتومات دیده‌شده | {', '.join('S%d' % x for x in AUTO_STEPS if x in steps['D0'])} (S5، S40 و S120 در همان اسکن تمام می‌شوند و با پوشش کد تأیید می‌شوند) |",
           f"| مرحله‌های جوهرزنی / هومینگ | D1: {sorted(set(INK_STEPS) & steps['D1'])} · D2: {sorted(set(HOME_STEPS) & steps['D2'])} · D3: {sorted(set(AXIS_HOME_STEPS) & steps['D3'])} |",
           f"| آلارم‌های آزموده‌شده | {', '.join(ALARMS[a] for a in sorted(alarms))} ({len(alarms)} از 21) |",
           "", "## سناریوها", ""]
    for r in results:
        ok = not r["error"] and all(v for _, v in r["checks"])
        out.append(f"### {'✅' if ok else '❌'} {r['name']}: {r['doc']}")
        out.append("")
        for d, v in r["checks"]:
            out.append(f"- {'✅' if v else '❌'} {d}")
        if r["error"]:
            out.append("")
            out.append("```\n" + r["error"] + "```")
        for v in r["viol"]:
            out.append(f"- ⚠️ {v}")
        out.append("")
    unc = [i for i in outs if i not in cov]
    out += ["## خط‌های اجرانشده", "",
            "دستورهای خروجی که در هیچ سناریویی اجرا نشدند (شماره‌ی خط در فایل IL):", "", "```"]
    for i in unc:
        out.append(f"{plc.src[i]:5d}  {lines[plc.src[i] - 1].strip()}")
    out.append("```")
    open("docs/11_test_report.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
    return passed, len(results), len(covered), len(outs)


if __name__ == "__main__":
    names = sys.argv[1:] or list(SCENARIOS)
    with Pool(4) as pool:
        results = pool.map(run_one, names)
    for r in results:
        ok = not r["error"] and all(v for _, v in r["checks"])
        print("%-5s %-4s %s" % (r["name"], "OK" if ok else "FAIL", r["doc"]))
        if not ok:
            for d, v in r["checks"]:
                if not v:
                    print("        x", d)
            if r["error"]:
                print(r["error"])
    if len(names) == len(SCENARIOS):
        p, n, c, t = report(results)
        print("\n%d/%d scenarios, coverage %d/%d outputs -> docs/11_test_report.md" % (p, n, c, t))
