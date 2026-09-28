#!/usr/bin/env python3
"""
Parametric 3D model of the single-colour closed-cup pad printer (Tampo).

Run:   python3 cad/tampo_machine.py            (all outputs, ~1-3 min)
       python3 cad/tampo_machine.py --quick    (model + checks only)

Outputs (cad/out/):
  tampo_assembly.step      whole machine, one solid per part, coloured  -> AutoCAD: IMPORT
  parts_step/<code>.step   every manufactured part in its own coordinates
  dxf/<code>.dxf           flat pattern of every plate (laser / waterjet), 1:1 mm
  tampo_GA.dxf             general arrangement: 3 hidden-line views + main dimensions
  cut_list.csv             steel tube cut list (profile, length, qty)
  parts_list.csv           full part list with material, mass, qty, process
  check_report.md          interference / clearance / stiffness / mass checks
  viewer_data.json         tessellated meshes for the 3D web viewer

World axes (mm):  X = pad travel (+X towards the operator / print station)
                  Y = across the machine,  Z = up,  floor = Z 0,  Y 0 = machine centre.
The ink-cup axis ("Y" in the PLC program) runs parallel to world X, beside the cliché.
"""
import csv, json, math, os, sys, time
import cadquery as cq
import ezdxf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
QUICK = "--quick" in sys.argv

# ============================================================================
# 1. PARAMETERS  (change here, re-run, everything follows)
# ============================================================================
P = dict(
    Zc=945.0,          # cliché top = part top at print = working height
    base_L=1300.0,     # base frame length (X)
    base_W=700.0,      # base frame width (Y)
    base_top=880.0,    # top of base frame tubes
    foot_h=60.0,       # levelling feet
    tb=60.0, tb_t=4.0, # base / portal square tube 60x60x4
    x_home=490.0,      # world X of pad centre at X-axis position 0
    x_pick=100.0,      # X-axis position of pick (over the image)
    x_print=600.0,     # X-axis position of print
    x_travel=650.0,    # usable X travel (limit switch to limit switch)
    rail_y=150.0,      # Y of the X rails (±)
    pad_L=195.0, pad_W=140.0, pad_H=80.0,   # pad 3016
    z_stroke=100.0, pad_press=5.0,          # SC63 stroke, pad compression on cliché
    cup_od=140.0, cup_h=45.0,
    cup_home=590.0,    # world X of cup centre when it covers the image (= pick)
    cup_stroke=370.0,  # cup travel (measured on the existing machine)
    cliche_L=580.0, cliche_W=200.0, cliche_t=10.0,
    part_h=60.0,       # sample part height at the print station
    F_print=1590.0,    # SC63 @ 5.1 bar, N
)
Zc = P["Zc"]
ZT = P["base_top"]
X_PICK = P["x_home"] + P["x_pick"]      # 590
X_PRINT = P["x_home"] + P["x_print"]    # 1090
PAD_UP_BOTTOM = Zc + P["z_stroke"] - P["pad_press"]          # 1040
# Z head stack (bottom -> top): pad, pad base 12, holder block (lowest) + side plates 210, head plate 20, gap 20
HEAD_BOT = PAD_UP_BOTTOM + P["pad_H"] + 12 + 210                # 1342
HEAD_TOP = HEAD_BOT + 20                                         # 1362
ZCP = HEAD_TOP + 20                                              # carriage plate bottom 1382
CP_T = 15.0
RAIL_BOT = ZCP - 30                                              # HGH20CA total height 30
BAR_BOT = RAIL_BOT - 15                                          # rail mounting bar 40x15
BEAM_TOP = BAR_BOT
BEAM_BOT = BEAM_TOP - 100
CROSS_TOP = BEAM_BOT
CROSS_BOT = CROSS_TOP - 60
PULLEY_Z = ZCP - 30          # X belt pulley axis
CUP_ARM_BOT = Zc + 50        # 995
CUP_RAIL_BOT = CUP_ARM_BOT - 28   # HGH15CA total height 28
CUP_PULLEY_Z = CUP_ARM_BOT - 10 - 19.1
PD24 = 38.2                  # pitch diameter 24T 5M

STEEL, ALU, PC, POM = 7.85e-6, 2.70e-6, 1.20e-6, 1.41e-6
RHO = {"فولاد": STEEL, "St37": STEEL, "CK45": STEEL, "آلومینیوم 6061": ALU,
       "آلومینیوم": ALU, "پلی‌کربنات": PC, "پلی‌استال": POM}

C = {  # colours r,g,b,a
    "frame": (0.22, 0.25, 0.29, 1), "steel": (0.56, 0.58, 0.61, 1), "alu": (0.80, 0.82, 0.85, 1),
    "rail": (0.62, 0.64, 0.67, 1), "block": (0.18, 0.20, 0.23, 1), "motor": (0.10, 0.10, 0.11, 1),
    "gear": (0.40, 0.42, 0.45, 1), "pneu": (0.78, 0.80, 0.83, 1), "valve": (0.16, 0.33, 0.62, 1),
    "pad": (0.88, 0.47, 0.52, 1), "cup": (0.60, 0.62, 0.68, 1), "cliche": (0.72, 0.72, 0.74, 1),
    "guard": (0.65, 0.82, 0.95, 0.22), "yellow": (0.96, 0.78, 0.10, 1), "red": (0.85, 0.10, 0.10, 1),
    "cab": (0.86, 0.87, 0.89, 1), "hmi": (0.13, 0.13, 0.15, 1), "belt": (0.08, 0.08, 0.08, 1),
    "part": (0.20, 0.55, 0.45, 1), "chain": (0.12, 0.12, 0.12, 1), "green": (0.2, 0.7, 0.3, 1),
}

V = cq.Vector
PARTS = []


def add(code, name, shape, kind, mat, color, group, mov=None, mass=None, meta=None, local=None):
    """kind: tube | plate | machined | buy | sheet.  mov: None | 'x' | 'z' | 'c' (cup)."""
    PARTS.append(dict(code=code, name=name, shape=shape, kind=kind, mat=mat, color=C[color] if isinstance(color, str) else color,
                      group=group, mov=mov, mass=mass, meta=meta or {}, local=local))


def box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(axis, c, d, z0, z1):
    """cylinder along axis 'X'|'Y'|'Z'; c = the two other coords; runs z0..z1 along the axis."""
    dirs = {"X": V(1, 0, 0), "Y": V(0, 1, 0), "Z": V(0, 0, 1)}
    if axis == "X":
        p = V(z0, c[0], c[1])
    elif axis == "Y":
        p = V(c[0], z0, c[1])
    else:
        p = V(c[0], c[1], z0)
    return cq.Solid.makeCylinder(d / 2, z1 - z0, p, dirs[axis])


def tubecyl(axis, c, od, idd, z0, z1):
    return cyl(axis, c, od, z0, z1).cut(cyl(axis, c, idd, z0 - 1, z1 + 1))


def comp(*shapes):
    return cq.Compound.makeCompound([s for s in shapes])


# ---------------------------------------------------------------- tubes
def rhs(p0, p1, a, b, t):
    """axis-aligned rectangular hollow section between centreline points p0,p1.
    a = size along the first perpendicular axis, b = along the second (X:(Y,Z) Y:(X,Z) Z:(X,Y))."""
    ax = [i for i in range(3) if abs(p0[i] - p1[i]) > 1e-6]
    assert len(ax) == 1, (p0, p1)
    ax = ax[0]
    L = abs(p1[ax] - p0[ax])
    lo = min(p0[ax], p1[ax])
    perp = [i for i in range(3) if i != ax]
    size = [0, 0, 0]
    size[ax] = L
    size[perp[0]] = a
    size[perp[1]] = b
    mn = [0, 0, 0]
    mn[ax] = lo
    mn[perp[0]] = p0[perp[0]] - a / 2
    mn[perp[1]] = p0[perp[1]] - b / 2
    outer = cq.Solid.makeBox(*size, V(*mn))
    isz = list(size)
    imn = list(mn)
    isz[ax] += 2
    imn[ax] -= 1
    for i in perp:
        isz[i] -= 2 * t
        imn[i] += t
    shape = outer.cut(cq.Solid.makeBox(*isz, V(*imn)))
    local = cq.Solid.makeBox(L, a, b).cut(cq.Solid.makeBox(L + 2, a - 2 * t, b - 2 * t, V(-1, t, t)))
    return shape, L, local


def tube(name, p0, p1, a, b, t, group="اسکلت", color="frame", note=""):
    shape, L, local = rhs(p0, p1, a, b, t)
    big, small = max(a, b), min(a, b)
    prof = f"{'SHS' if a == b else 'RHS'} {big:g}x{small:g}x{t:g}"
    add(None, name, shape, "tube", "St37", color, group, meta=dict(profile=prof, L=round(L, 1), note=note), local=local)


# ---------------------------------------------------------------- plates
class Plate:
    def __init__(self, code, name, w, h, t, mat, holes=(), slots=(), cuts=(), note="", process="برش لیزر/واترجت"):
        self.code, self.name, self.w, self.h, self.t, self.mat = code, name, w, h, t, mat
        self.holes, self.slots, self.cuts = list(holes), list(slots), list(cuts)
        self.note, self.process = note, process
        self._solid = None

    def solid(self):
        if self._solid is None:
            s = cq.Solid.makeBox(self.w, self.h, self.t, V(-self.w / 2, -self.h / 2, 0))
            cutters = [cq.Solid.makeCylinder(d / 2, self.t + 2, V(u, v, -1)) for (u, v, d) in self.holes]
            for (u1, v1, u2, v2, wd) in self.slots:
                ln = math.hypot(u2 - u1, v2 - v1)
                ang = math.degrees(math.atan2(v2 - v1, u2 - u1))
                sl = (cq.Workplane("XY").workplane(offset=-1).center((u1 + u2) / 2, (v1 + v2) / 2)
                      .slot2D(ln + wd, wd, ang).extrude(self.t + 2).val())
                cutters.append(sl)
            for (u, v, cw, ch) in self.cuts:
                cutters.append(cq.Solid.makeBox(cw, ch, self.t + 2, V(u - cw / 2, v - ch / 2, -1)))
            if cutters:
                s = s.cut(*cutters)
            self._solid = s
        return self._solid

    def place(self, plane, cu, cv, n0):
        """plane XY: u->X v->Y, thickness n0..n0+t along Z.  XZ: u->X v->Z, thickness along Y.  YZ: u->Y v->Z, along X."""
        t = self.t
        if plane == "XY":
            pl = cq.Plane((cu, cv, n0), (1, 0, 0), (0, 0, 1))
        elif plane == "XZ":
            pl = cq.Plane((cu, n0 + t, cv), (1, 0, 0), (0, -1, 0))
        else:
            pl = cq.Plane((n0, cu, cv), (0, 1, 0), (1, 0, 0))
        return self.solid().moved(cq.Location(pl))

    def dxf(self, path, qty):
        doc = ezdxf.new("R2010", setup=True)
        doc.units = ezdxf.units.MM
        for ln, col in (("CUT", 7), ("HOLES", 1), ("TEXT", 3), ("DIM", 5)):
            doc.layers.add(ln, color=col)
        msp = doc.modelspace()
        w, h = self.w, self.h
        msp.add_lwpolyline([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)], close=True,
                           dxfattribs={"layer": "CUT"})
        for (u, v, d) in self.holes:
            msp.add_circle((u, v), d / 2, dxfattribs={"layer": "HOLES"})
        for (u1, v1, u2, v2, wd) in self.slots:
            ang = math.atan2(v2 - v1, u2 - u1)
            nx, ny = -math.sin(ang) * wd / 2, math.cos(ang) * wd / 2
            pts = [(u1 + nx, v1 + ny, 0), (u2 + nx, v2 + ny, 1), (u2 - nx, v2 - ny, 0), (u1 - nx, v1 - ny, 1)]
            msp.add_lwpolyline([(p[0], p[1], 0, 0, p[2]) for p in pts], format="xyseb", close=True,
                               dxfattribs={"layer": "HOLES"})
        for (u, v, cw, ch) in self.cuts:
            msp.add_lwpolyline([(u - cw / 2, v - ch / 2), (u + cw / 2, v - ch / 2), (u + cw / 2, v + ch / 2),
                                (u - cw / 2, v + ch / 2)], close=True, dxfattribs={"layer": "CUT"})
        ov = {"dimlfac": 1, "dimdec": 1, "dimtxt": 5, "dimasz": 3, "dimzin": 8}
        msp.add_linear_dim(base=(0, -h / 2 - 25), p1=(-w / 2, -h / 2), p2=(w / 2, -h / 2),
                           dxfattribs={"layer": "DIM"}, override=ov).render()
        msp.add_linear_dim(base=(-w / 2 - 25, 0), p1=(-w / 2, -h / 2), p2=(-w / 2, h / 2), angle=90,
                           dxfattribs={"layer": "DIM"}, override=ov).render()
        mat = {"آلومینیوم 6061": "AL 6061-T6", "پلی‌کربنات": "POLYCARBONATE", "فولاد": "STEEL"}.get(self.mat, self.mat)
        txt = f"{self.code}  {self.w:g} x {self.h:g} x {self.t:g}  {mat}  QTY {qty}  (mm)"
        msp.add_text(txt, height=6, dxfattribs={"layer": "TEXT"}).set_placement((-w / 2, -h / 2 - 55))
        doc.saveas(path)


def plate(pl, plane, cu, cv, n0, group, color, mov=None):
    add(pl.code, pl.name, pl.place(plane, cu, cv, n0), "plate", pl.mat, color, group, mov,
        meta=dict(dims=f"{pl.w:g}x{pl.h:g}x{pl.t:g}", plate=pl, process=pl.process, note=pl.note),
        local=pl.solid())


def machined(code, name, shape, local, mat, color, group, dims, mov=None, note=""):
    add(code, name, shape, "machined", mat, color, group, mov, meta=dict(dims=dims, note=note, process="تراش/فرز"),
        local=local)


def buy(code, name, shape, color, group, mass, spec, mov=None):
    add(code, name, shape, "buy", "-", color, group, mov, mass=mass, meta=dict(dims=spec))


def rect_pattern(cx, cy, dx, dy, d):
    return [(cx + sx * dx, cy + sy * dy, d) for sx in (-1, 1) for sy in (-1, 1)]


def pcd(cx, cy, r, n, d, a0=45):
    return [(cx + r * math.cos(math.radians(a0 + i * 360 / n)), cy + r * math.sin(math.radians(a0 + i * 360 / n)), d)
            for i in range(n)]


# ============================================================================
# 2. BASE FRAME  (welded, SHS 60x60x4)
# ============================================================================
def build_base():
    tb, t = P["tb"], P["tb_t"]
    g = "اسکلت پایین"
    h = tb / 2
    zb0, zb1 = P["foot_h"], ZT
    legX = (h, 900.0, P["base_L"] - h)
    yS = P["base_W"] / 2 - h            # 320
    for x in legX:
        for y in (-yS, yS):
            tube("پایه", (x, y, zb0), (x, y, zb1), tb, tb, t, g, note="سرتاسری، دو سر گونیا")
    for zc in (zb1 - h, zb0 + h):
        for y in (-yS, yS):
            tube("طولی", (tb, y, zc), (900 - h, y, zc), tb, tb, t, g, note="بین پایه‌ها")
            tube("طولی", (900 + h, y, zc), (P["base_L"] - tb, y, zc), tb, tb, t, g, note="بین پایه‌ها")
        for x in legX:
            tube("عرضی", (x, -yS + h, zc), (x, yS - h, zc), tb, tb, t, g, note="بین طولی‌ها")
    for x in (300.0, 600.0):  # deck supports
        tube("عرضی زیر صفحه", (x, -yS + h, zb1 - h), (x, yS - h, zb1 - h), tb, tb, t, g)
    # print-station sub-frame (well), top at Z 640
    zs = 640 - h
    for y in (-yS, yS):
        tube("طولی زیرقاب چاپ", (900 + h, y, zs), (P["base_L"] - tb, y, zs), tb, tb, t, g)
    for x in (960.0, 1210.0):
        tube("عرضی زیرقاب چاپ", (x, -yS + h, zs), (x, yS - h, zs), tb, tb, t, g)
    # levelling feet
    for x in legX:
        for y in (-yS, yS):
            buy("B40", "پایه‌ی ترازشو M16", comp(cyl("Z", (x, y), 80, 0, 12), cyl("Z", (x, y), 16, 12, P["foot_h"])),
                "gear", g, 0.6, "M16، کف Ø80، ظرفیت ≥ ۵۰۰ kg")
    # deck (top plate over the ink station)
    deck = Plate("P01", "صفحه‌ی رویی ایستگاه جوهر", 800, P["base_W"], 10, "St37",
                 holes=[(u, v, 9) for u in (-370, -120, 130, 370) for v in (-320, 320)] +
                       [(u, v, 9) for u in (-170, 130) for v in (-320, 320)],
                 note="با پیچ M8 روی قاب؛ سوراخ‌های نصب قطعات را بعد از چیدمان جای‌یابی کنید")
    plate(deck, "XY", 470, 0, ZT, g, "steel")


# ============================================================================
# 3. UPPER GANTRY  (two portals + two X beams)
# ============================================================================
def build_gantry():
    tb, t = P["tb"], P["tb_t"]
    g = "اسکلت بالا"
    h = tb / 2
    yS = P["base_W"] / 2 - h
    portX = (40.0, 1260.0)
    for x in portX:
        for y in (-yS, yS):
            tube("ستون پرتال", (x, y, ZT), (x, y, CROSS_BOT), tb, tb, t, g, note="روی قاب پایین جوش")
        tube("تیر عرضی پرتال", (x, -P["base_W"] / 2, CROSS_BOT + h), (x, P["base_W"] / 2, CROSS_BOT + h), tb, tb, t, g,
             note="سرتاسری روی ستون‌ها")
    for y in (-330.0, 330.0):
        tube("طولی بالای محافظ", (portX[0] + h, y, CROSS_TOP - 20), (portX[1] - h, y, CROSS_TOP - 20), 40, 40, 3, g,
             note="بین دو پرتال، رو با تیر عرضی")
    for y in (-P["rail_y"], P["rail_y"]):
        tube("تیر ریل X", (10, y, BEAM_BOT + 50), (1290, y, BEAM_BOT + 50), 50, 100, t, g,
             note="با ۴ پیچ M10 روی هر پرتال؛ رو با تسمه‌ی تخت ریل")
        # rail mounting bar (machined flat)
        bar = Plate("P02", "تسمه‌ی نصب ریل X (سنگ‌خورده)", 900, 40, 15, "CK45",
                    holes=[(-450 + 30 + 60 * i, 0, 4.2) for i in range(15)] +
                          [(-450 + 60 + 120 * i, 13, 9) for i in range(7)] +
                          [(-450 + 60 + 120 * i, -13, 9) for i in range(7)],
                    note="Ø4.2 = قلاویز M5 برای ریل (گام ۶۰)؛ Ø9 = پیچ M8 به تیر؛ رو و زیر سنگ، تخت ≤ 0.02",
                    process="برش + فرز + سنگ")
        plate(bar, "XY", 815, y, BAR_BOT, "ریل‌ها", "steel")
        buy("B01", "ریل HIWIN HGR20 طول 900", box(365, 1265, y - 10, y + 10, RAIL_BOT, RAIL_BOT + 17.5), "rail",
            "ریل‌ها", 2.21 * 0.9, "HGR20R900C, گام سوراخ 60")


# ============================================================================
# 4. X CARRIAGE + Z HEAD  (reference position: X axis = 0, Z up)
# ============================================================================
def build_x_carriage():
    g = "کالسکه X"
    xc = P["x_home"]           # pad centre X at axis 0
    ycp = 17.5                 # carriage plate centre Y (plate spans Y -200..235)
    # HGH20CA blocks
    for dx in (-70, 70):
        for y in (-P["rail_y"], P["rail_y"]):
            blk = box(xc + dx - 38.75, xc + dx + 38.75, y - 22, y + 22, RAIL_BOT + 4.6, ZCP).cut(
                box(xc + dx - 40, xc + dx + 40, y - 10.5, y + 10.5, RAIL_BOT, RAIL_BOT + 18))
            buy("B02", "واگن HIWIN HGH20CA", blk,
                "block", g, 0.40, "HGH20CAZ0C", mov="x")
    holes = []
    for dx in (-70, 70):
        for y in (-P["rail_y"], P["rail_y"]):
            holes += rect_pattern(dx, y - ycp, 18, 16, 5.5)
    holes += [(0, -ycp, 45)]                                           # rod + floating joint
    for dx in (-85, 85):
        holes += [(dx, -ycp, 40)] + pcd(dx, -ycp, 25.5, 4, 6.6)        # LMF25UU
    holes += rect_pattern(0, -ycp, 25, 50, 9)                          # SC63 FA flange
    holes += [(-20, 216 - ycp, 6.6), (20, 216 - ycp, 6.6)]             # belt clamp
    holes += [(-45, 97 - ycp, 5.5), (45, 97 - ycp, 5.5)]               # Z valve
    holes += [(-25, -190 - ycp, 6.6), (25, -190 - ycp, 6.6)]           # drag-chain bracket
    cp = Plate("P10", "صفحه‌ی کالسکه X", 280, 435, CP_T, "آلومینیوم 6061", holes=holes,
               cuts=[(0, -97.5 - ycp, 230, 45)],
               note="صفحه‌ی سبک‌شده؛ سوراخ‌های واگن M5 با فاصله‌ی 36×32 (HGH20CA)")
    plate(cp, "XY", xc, ycp, ZCP, g, "alu", mov="x")
    # belt clamp (top strand of the X belt)
    clamp = Plate("P11", "گیره‌ی تسمه X", 60, 25, 32, "آلومینیوم 6061", holes=[(-20, 0, 6.6), (20, 0, 6.6)],
                  note="دو تکه؛ شیار دندانه‌ی HTD5M در صفحه‌ی بین", process="فرز")
    clamp_shape = box(xc - 30, xc + 30, 200, 232, ZCP - 25, ZCP)
    machined("P11", "گیره‌ی تسمه X", clamp_shape, clamp.solid(), "آلومینیوم 6061", "alu", g, "60x32x25", mov="x")
    # Z valve on the carriage + quick exhausts
    buy("B20", "شیر 5/2 سایز 3/8 (4V320)", box(xc - 55, xc + 55, 80, 115, ZCP + CP_T, ZCP + CP_T + 60), "valve", g,
        0.55, "Airtac 4V320-10 24VDC", mov="x")
    # drag chain bracket
    machined("P12", "براکت زنجیر کابل X", box(xc - 40, xc + 40, -215, -200, ZCP - 25, ZCP + CP_T),
             box(0, 80, 0, 15, 0, 40), "St37", "steel", g, "80x40x15 نبشی", mov="x")


def build_z_head():
    g = "هد Z"
    xc = P["x_home"]
    # cylinder SC63x100 with FA flange on the carriage plate, rod down through the plate
    fa = Plate("B21F", "فلنج جلو SC63 (FA)", 75, 120, 12, "فولاد", holes=rect_pattern(0, 0, 25, 50, 9) + [(0, 0, 40)])
    z0 = ZCP + CP_T
    buy("B21F", "فلنج جلو FA جک Ø63", fa.place("XY", xc, 0, z0), "gear", g, 0.6, "ISO 15552 MF1 Ø63", mov="x")
    zb = z0 + 12
    L = 140 + P["z_stroke"]
    cylz = comp(box(xc - 37.5, xc + 37.5, -37.5, 37.5, zb, zb + 30), box(xc - 33, xc + 33, -33, 33, zb + 30, zb + L - 30),
                box(xc - 37.5, xc + 37.5, -37.5, 37.5, zb + L - 30, zb + L),
                cyl("Y", (xc, zb + 15), 14, 37.5, 45), cyl("Y", (xc, zb + L - 15), 14, 37.5, 45))
    buy("B21", "جک Airtac SC63×100-S", cylz, "pneu", g, 2.9, "SC63x100-S مگنت‌دار", mov="x")
    for i, zz in enumerate((zb + 40, zb + 90, zb + L - 40)):
        buy("B22", "سنسور مگنتی جک", box(xc - 44, xc - 37.5, -8, 8, zz, zz + 25), "red", g, 0.03, "CS1-J / D-M9N",
            mov="x")
    for zz in (zb + 17, zb + L - 17):   # ports face +Y (towards the valve), clear of the guide rods
        buy("B23", "شیر تخلیه‌ی سریع 3/8", cyl("Y", (xc, zz), 34, 45, 78), "pneu", g, 0.25, "SMC AQ5000", mov="x")
    # rod + floating joint (move with Z)
    buy("B21R", "شافت جک + مفصل شناور M16", comp(cyl("Z", (xc, 0), 20, HEAD_TOP + 25, zb + P["z_stroke"] + 5), cyl("Z", (xc, 0), 34, HEAD_TOP,
                                                                                              HEAD_TOP + 30)),
        "pneu", g, 0.5, "FJ M16x1.5", mov="z")
    # LMF25UU bushings (flange under the plate)
    for dx in (-85, 85):
        buy("B24", "بوش خطی فلنج‌دار LMF25UU", comp(tubecyl("Z", (xc + dx, 0), 62, 25, ZCP - 10, ZCP),
                                                   tubecyl("Z", (xc + dx, 0), 40, 25, ZCP, ZCP + 60)),
            "gear", g, 0.34, "LMF25UU", mov="x")
        # guide rod Ø25 (moves with Z)
        machined("M01", "میله‌ی راهنمای Z Ø25", cyl("Z", (xc + dx, 0), 25, HEAD_TOP, HEAD_TOP + 210),
                 cyl("Z", (0, 0), 25, 0, 210), "CK45", "rail", g, "Ø25 h6 × 210، سخت‌کاری و کروم", mov="z",
                 note="سر پایین M12 به صفحه‌ی سر؛ سر بالا شیار خار")
        buy("B25", "رینگ توقف Ø25", tubecyl("Z", (xc + dx, 0), 45, 25, HEAD_TOP + 195, HEAD_TOP + 210), "gear", g, 0.1,
            "Shaft collar 25", mov="z")
    # head plate
    hp = Plate("P13", "صفحه‌ی سر Z", 240, 120, 20, "آلومینیوم 6061",
               holes=[(-85, 0, 12.5), (85, 0, 12.5), (0, 0, 16.5), (40, 25, 10.2)] +
                     [(u, v, 6.6) for u in (-60, 0, 60) for v in (-46, 46)],
               note="Ø12.5 پیچ M12 میله‌ها، Ø16.5 مفصل شناور، Ø10.2 قلاویز M12 پیچ تنظیم ارتفاع، Ø6.6 پیچ M6 صفحه‌های کناری")
    plate(hp, "XY", xc, 0, HEAD_BOT, g, "alu", mov="z")
    # side plates with vertical slots (manual pad height, 60 mm)
    sp = Plate("P14", "صفحه‌ی کناری اسلاید ارتفاع پد", 160, 210, 12, "آلومینیوم 6061",
               slots=[(-50, -80, -50, -20, 10.5), (50, -80, 50, -20, 10.5)],
               note="شیار 60 mm برای تنظیم ارتفاع پد؛ لبه‌ی بالا 3× قلاویز M6")
    zc_sp = HEAD_BOT - 105
    for y0 in (40.0, -52.0):
        plate(sp, "XZ", xc, zc_sp, y0, g, "alu", mov="z")
    # holder block (lowest position) + jack screw
    hb = box(xc - 80, xc + 80, -40, 40, HEAD_BOT - 210, HEAD_BOT - 160)
    machined("M02", "بلوک نگه‌دارنده‌ی پد", hb, box(0, 160, 0, 80, 0, 50), "آلومینیوم 6061", "alu", g, "160x80x50",
             mov="z", note="دو طرف 2× قلاویز M10 برای شیارها؛ زیر 4× M8 به صفحه‌ی پد")
    buy("B26", "پیچ تنظیم ارتفاع M12 + مهره قفل", cyl("Z", (xc + 40, 25), 10, HEAD_BOT - 160, HEAD_TOP + 10), "gear", g,
        0.15, "M12x200 DIN 913", mov="z")
    # pad base plate + pad
    pb = Plate("P15", "صفحه‌ی پد", 220, 160, 12, "آلومینیوم 6061",
               holes=rect_pattern(0, 0, 60, 25, 8.5) + rect_pattern(0, 0, 95, 65, 6.6),
               note="4× M8 به بلوک؛ 4× M6 برای پایه‌ی چوبی/آلومینیومی پد")
    plate(pb, "XY", xc, 0, HEAD_BOT - 222, g, "alu", mov="z")
    zt = HEAD_BOT - 222
    zbot = zt - P["pad_H"]
    hw = P["pad_W"] / 2
    prof = (cq.Workplane("YZ", origin=(xc - P["pad_L"] / 2, 0, 0))
            .polyline([(-hw, zt), (hw, zt), (hw, zt - 25), (8, zbot), (-8, zbot), (-hw, zt - 25)]).close()
            .extrude(P["pad_L"]).edges("|X").fillet(6).val())
    buy("B27", "پد سیلیکونی 3016 (195×140×80)", prof, "pad", g, 1.8, "3016 شیروانی", mov="z")


# ============================================================================
# 5. X DRIVE  (NEMA24 + PLF60 1:3 + HTD5M 25 mm belt)
# ============================================================================
def build_x_drive():
    g = "محرک X"
    yb = 215.0
    xr, xf = 90.0, 1230.0
    # rear motor bracket (L: foot on portal cross + vertical plate)
    foot = Plate("P20", "پایه‌ی براکت موتور X", 60, 77, 12, "St37", holes=rect_pattern(0, 0, 18, 25, 9))
    plate(foot, "XY", 40, 177 + 38.5, CROSS_TOP, g, "steel")
    vp = Plate("P21", "براکت موتور X", 130, 151, 12, "St37",
               holes=[(xr - 75, PULLEY_Z - 1324.5, 51)] + pcd(xr - 75, PULLEY_Z - 1324.5, 35, 4, 5.5),
               note="جوش به پایه + لچکی؛ الگوی فلنج گیربکس PLF60 را با کاتالوگ تطبیق دهید")
    plate(vp, "XZ", 75, 1249 + 75.5, 242, g, "steel")
    buy("B03", "گیربکس خورشیدی PLF60 1:3", comp(box(xr - 30, xr + 30, 254, 264, PULLEY_Z - 30, PULLEY_Z + 30),
                                                 cyl("Y", (xr, PULLEY_Z), 58, 264, 324)), "gear", g, 1.0,
        "PLF60-3 / EG24 1:3")
    buy("B04", "استپر کلوزلوپ NEMA24 4 N·m (X)", comp(box(xr - 30, xr + 30, 324, 434, PULLEY_Z - 30, PULLEY_Z + 30),
                                                      box(xr - 20, xr + 20, 434, 454, PULLEY_Z - 12, PULLEY_Z + 12)),
        "motor", g, 1.9, "60 mm, L≈110, 4 N·m")
    for x in (xr, xf):
        buy("B05", "پولی 24T HTD5M عرض 25", comp(cyl("Y", (x, PULLEY_Z), PD24 - 1.1, yb - 14, yb + 14),
                                                 cyl("Y", (x, PULLEY_Z), 46, yb - 16, yb - 14),
                                                 cyl("Y", (x, PULLEY_Z), 46, yb + 14, yb + 16))
            .cut(cyl("Y", (x, PULLEY_Z), 14, yb - 20, yb + 20)), "gear", g, 0.18,
            "24-5M-25")
        buy("B06", "شافت پولی Ø14", cyl("Y", (x, PULLEY_Z), 14, yb - 16, 254), "gear", g, 0.05, "Ø14")
    # front idler bracket with tension slot
    foot2 = Plate("P22", "پایه‌ی براکت هرزگرد X", 60, 77, 12, "St37", holes=rect_pattern(0, 0, 18, 25, 9))
    plate(foot2, "XY", 1260, 177 + 38.5, CROSS_TOP, g, "steel")
    vp2 = Plate("P23", "براکت هرزگرد X (شیار کشش)", 110, 151, 12, "St37",
                slots=[(xf - 1235 - 10, PULLEY_Z - 1324.5, xf - 1235 + 10, PULLEY_Z - 1324.5, 14.5)],
                holes=[(40, PULLEY_Z - 1324.5, 8.5)],
                note="شیار ±10 برای کشش تسمه؛ پیچ کشش M8 از لبه")
    plate(vp2, "XZ", 1235, 1249 + 75.5, 242, g, "steel")
    # belt: top strand clamped to the carriage, bottom strand free
    r = PD24 / 2
    for z0_, z1_ in ((PULLEY_Z + r, PULLEY_Z + r + 3.6), (PULLEY_Z - r - 3.6, PULLEY_Z - r)):
        buy("B07", "تسمه HTD5M عرض 25 مغزی فولادی", box(xr, xf, yb - 12.5, yb + 12.5, z0_, z1_), "belt", g,
            0.1, "HTD5M-25 PU steel", mov=None)
    # limit switches + home sensor on the +Y beam
    for x in (330.0, 1275.0):
        buy("B30", "لیمیت سوئیچ Omron D4N", box(x - 15, x + 15, 176, 199, BEAM_TOP - 60, BEAM_TOP - 5), "yellow",
            "سنسورها", 0.15, "D4N-1A31")
    buy("B31", "سنسور هوم M18", cyl("Z", (395, 188), 18, BEAM_TOP - 60, BEAM_TOP - 5), "gear", "سنسورها", 0.06,
        "PR18-8DN")
    # drag chain tray on the -Y beam
    tray = Plate("P24", "سینی زنجیر کابل X", 860, 64, 2, "فولاد", note="ورق 2 خم U، ارتفاع لبه 30",
                 process="برش + خم")
    plate(tray, "XY", 825, -228, BEAM_TOP - 12, g, "steel")
    buy("B08", "زنجیر کابل 25×50 (X)", comp(box(830, 1240, -253, -203, BEAM_TOP - 10, BEAM_TOP + 15),
                                            box(xc_chain(), 830, -253, -203, ZCP - 25, ZCP)),
        "chain", g, 1.5, "25x50 R55، طول ≈ 1.2 m")


def xc_chain():
    return P["x_home"] + 40


# ============================================================================
# 6. INK STATION: cliché holder + closed cup on HGR15 + belt drive
# ============================================================================
def build_ink():
    g = "ایستگاه جوهر"
    x0c = 120.0
    xcl = x0c + P["cliche_L"] / 2
    ch = Plate("P30", "پایه‌ی کلیشه (بستر فرزکاری‌شده)", 600, 220, 45, "St37",
               holes=rect_pattern(0, 0, 280, 90, 11) + rect_pattern(0, 0, 150, 0, 8.5),
               note="روی سطح فرز و سنگ؛ 4× پیچ M10 به صفحه‌ی رویی، گیره‌های کلیشه با M8",
               process="فرز + سنگ")
    plate(ch, "XY", xcl, 0, ZT + 10, g, "steel")
    buy("B50", "کلیشه‌ی فولادی 580×200×10", box(x0c, x0c + P["cliche_L"], -P["cliche_W"] / 2, P["cliche_W"] / 2,
                                                 Zc - P["cliche_t"], Zc), "cliche", g, 9.1, "کلیشه‌ی ضخیم فولادی")
    buy("B51", "گیره‌ی کلیشه", comp(*[box(x - 15, x + 15, y - 12, y + 12, Zc, Zc + 8)
                                      for x in (x0c + 40, x0c + P["cliche_L"] - 40) for y in (-112, 112)]), "gear", g,
        0.2, "گیره‌ی لبه")
    # cup rail riser
    ris = box(180, 640, -195, -155, ZT + 10, CUP_RAIL_BOT)
    machined("M10", "پایه‌ی ریل کاپ", ris, box(0, 460, 0, 40, 0, CUP_RAIL_BOT - ZT - 10), "St37", "steel", g,
             f"460x40x{CUP_RAIL_BOT - ZT - 10:g}", note="رو فرز؛ قلاویز M4 گام 60 برای HGR15")
    buy("B09", "ریل HIWIN HGR15 طول 460", box(180, 640, -182.5, -167.5, CUP_RAIL_BOT, CUP_RAIL_BOT + 15), "rail", g,
        0.67, "HGR15R460C")
    xcup = P["cup_home"]
    blk = box(xcup - 30.7, xcup + 30.7, -192, -158, CUP_RAIL_BOT + 4.3, CUP_ARM_BOT).cut(
        box(xcup - 32, xcup + 32, -183, -167, CUP_RAIL_BOT, CUP_RAIL_BOT + 15.5))
    buy("B10", "واگن HIWIN HGH15CA", blk, "block",
        g, 0.18, "HGH15CAZ0C", mov="c")
    arm = Plate("P31", "بازوی کاپ", 60, 270, 12, "آلومینیوم 6061",
                holes=rect_pattern(0, -175 + 105, 13, 13, 4.5) + pcd(0, 105, 25, 3, 8.5, a0=90) +
                      [(-15, -215 + 105, 6.6), (15, -215 + 105, 6.6)],
                note="3× پین فنری روی کاپ؛ نگه‌دارنده‌ی کاپ باید آزاد روی کلیشه بنشیند")
    arm_shape = arm.place("XY", xcup, -105, CUP_ARM_BOT)
    add("P31", arm.name, arm_shape, "plate", arm.mat, C["alu"], g, "c",
        meta=dict(dims="60x270x12", plate=arm, process=arm.process, note=arm.note), local=arm.solid())
    # arm is 60 wide; cup sits below the arm end, hung on 3 spring pins
    buy("B52", "کاپ بسته Ø140 با رینگ سرامیکی", comp(cyl("Z", (xcup, 0), P["cup_od"], Zc, Zc + 8),
                                                   cyl("Z", (xcup, 0), P["cup_od"] - 10, Zc + 8, Zc + P["cup_h"])),
        "cup", g, 1.6, "Ø140 (مطابق کاپ فعلی)", mov="c")
    for (u, v, d) in pcd(xcup, 0, 25, 3, 8, a0=90):
        buy("B53", "پین فنری کاپ", cyl("Z", (u, v), 8, Zc + P["cup_h"], CUP_ARM_BOT), "gear", g, 0.02, "Ø8", mov="c")
    machined("P32", "گیره‌ی تسمه کاپ", box(xcup - 25, xcup + 25, -232, -198, CUP_ARM_BOT - 20, CUP_ARM_BOT),
             box(0, 50, 0, 34, 0, 20), "آلومینیوم 6061", "alu", g, "50x34x20", mov="c")
    # cup drive (NEMA24 direct, 24T pulley, 20 mm belt)
    yb = -215.0
    xr, xf = 120.0, 700.0
    for x, code, nm in ((xr, "P33", "براکت موتور کاپ"), (xf, "P34", "براکت هرزگرد کاپ (شیار کشش)")):
        f = Plate(code + "F", "پایه‌ی " + nm, 90, 40, 10, "St37", holes=[(-30, 0, 9), (30, 0, 9)])
        plate(f, "XY", x, -220, ZT + 10, g, "steel")
        if code == "P33":
            vp = Plate(code, nm, 90, 130, 10, "St37",
                       holes=[(0, CUP_PULLEY_Z - 965, 39)] + rect_pattern(0, CUP_PULLEY_Z - 965, 23.57, 23.57, 5.2))
        else:
            vp = Plate(code, nm, 90, 130, 10, "St37",
                       slots=[(-10, CUP_PULLEY_Z - 965, 10, CUP_PULLEY_Z - 965, 12.5)])
        plate(vp, "XZ", x, 965, -240, g, "steel")
    buy("B11", "استپر کلوزلوپ NEMA24 4 N·m (کاپ)",
        comp(box(xr - 30, xr + 30, -350, -240, CUP_PULLEY_Z - 30, CUP_PULLEY_Z + 30)), "motor", g, 1.9,
        "60 mm, L≈110, 4 N·m")
    for x in (xr, xf):
        buy("B12", "پولی 24T گام 5 عرض 20", comp(cyl("Y", (x, CUP_PULLEY_Z), PD24 - 1.1, yb - 11, yb + 11),
                                                 cyl("Y", (x, CUP_PULLEY_Z), 44, yb - 13, yb - 11),
                                                 cyl("Y", (x, CUP_PULLEY_Z), 44, yb + 11, yb + 13)), "gear", g, 0.15,
            "24-5M-20 (مطابق تسمه‌ی فعلی)")
    r = PD24 / 2
    for z0_, z1_ in ((CUP_PULLEY_Z + r, CUP_PULLEY_Z + r + 3.6), (CUP_PULLEY_Z - r - 3.6, CUP_PULLEY_Z - r)):
        buy("B13", "تسمه گام 5 عرض 20 (کاپ)", box(xr, xf, yb - 10, yb + 10, z0_, z1_), "belt", g, 0.08,
            "5M-20 open")
    for x in (170.0, 650.0):
        buy("B30", "لیمیت سوئیچ Omron D4N", box(x - 15, x + 15, -150, -128, ZT + 10, ZT + 65), "yellow", "سنسورها",
            0.15, "D4N-1A31")
    buy("B31", "سنسور هوم M18", cyl("Y", (200, ZT + 45), 18, -154, -120), "gear", "سنسورها", 0.06, "PR18-8DN")


# ============================================================================
# 7. PRINT STATION: height-adjustable fixture table
# ============================================================================
def build_print_station():
    g = "ایستگاه چاپ"
    xc = X_PRINT
    top = Zc - P["part_h"]
    bp = Plate("P40", "صفحه‌ی پایه‌ی میز چاپ", 300, 300, 15, "St37",
               holes=[(dx, dy, 32) for dx in (-75, 75) for dy in (-90, 90)] +
                     [p for dx in (-75, 75) for dy in (-90, 90) for p in pcd(dx, dy, 21.5, 4, 5.5)] +
                     [(0, 0, 36)] + [(dx, 0, 11) for dx in (-130, -120, 120, 130)],
               note="روی زیرقاب چاپ؛ Ø36 یاتاقان پیچ Tr20")
    plate(bp, "XY", xc, 0, 640, g, "steel")
    tp = Plate("P41", "صفحه‌ی بالای میز چاپ (فیکسچر)", 260, 260, 20, "آلومینیوم 6061",
               holes=[(dx, dy, 17.5) for dx in (-75, 75) for dy in (-90, 90)] + [(0, 0, 17.5)] +
                     [(u, v, 6.8) for u in (-100, -50, 50, 100) for v in (-100, -50, 0, 50, 100)],
               note="شبکه‌ی M8 گام 50 برای قالب قطعه؛ مهره‌ی Tr20 زیر صفحه")
    plate(tp, "XY", xc, 0, top - 20, g, "alu")
    for dx in (-75, 75):
        for dy in (-90, 90):
            buy("B41", "بوش خطی LMF20UU", comp(tubecyl("Z", (xc + dx, dy), 54, 20, 655, 663),
                                               tubecyl("Z", (xc + dx, dy), 32, 20, 663, 715)), "gear", g, 0.18,
                "LMF20UU")
            machined("M20", "میله‌ی راهنمای میز Ø20", cyl("Z", (xc + dx, dy), 20, top - 20 - 250, top - 20),
                     cyl("Z", (0, 0), 20, 0, 250), "CK45", "rail", g, "Ø20 h6 × 250")
    buy("B42", "پیچ ذوزنقه Tr20×4 + مهره", cyl("Z", (xc, 0), 20, 555, top - 20), "gear", g, 0.8, "Tr20x4 L≈330")
    buy("B43", "فلکه‌ی دستی Ø125", comp(tubecyl("Z", (xc, 0), 125, 105, 530, 545), cyl("Z", (xc, 0), 30, 530, 555)),
        "motor", g, 0.5, "DIN 950 Ø125")
    buy("B44", "قطعه‌ی نمونه Ø80×60", cyl("Z", (xc, 0), 80, top, top + P["part_h"]), "part", g, 0.3, "نمونه")


# ============================================================================
# 8. SAFETY, GUARDS, ELECTRICS, PNEUMATICS
# ============================================================================
def build_periphery():
    g = "ایمنی و برق"
    # light curtain on the front portal columns (field between the two sticks)
    for y in (-300.0, 300.0):
        buy("B60", "پرده‌ی نوری نوع ۴، 14 mm (فرستنده / گیرنده)", box(1292, 1327, y - 17.5, y + 17.5, ZT, ZT + 310), "yellow", g, 0.6,
            "ارتفاع حفاظت ≈ 300")
    # guards (polycarbonate 5 mm)
    gd = "محافظ‌ها"
    pr = Plate("P50", "محافظ عقب (پلی‌کربنات)", 700, CROSS_TOP - ZT, 5, "پلی‌کربنات")
    add("P50", pr.name, pr.place("YZ", 0, (ZT + CROSS_TOP) / 2, -5), "plate", pr.mat, C["guard"], gd,
        meta=dict(dims=f"700x{CROSS_TOP - ZT:g}x5", plate=pr, process=pr.process, note=""), local=pr.solid())
    pr2 = Plate("P51", "محافظ کناری راست (پلی‌کربنات)", 1160, CROSS_TOP - ZT, 5, "پلی‌کربنات")
    plate(pr2, "XZ", 650, (ZT + CROSS_TOP) / 2, 352, gd, "guard")
    pr3 = Plate("P52", "درب کناری چپ روی ایستگاه جوهر (لولایی، با سوئیچ ایمنی)", 800, CROSS_TOP - ZT, 5, "پلی‌کربنات")
    plate(pr3, "XZ", 470, (ZT + CROSS_TOP) / 2, -357, gd, "guard")
    pr4 = Plate("P53", "محافظ کناری چپ جلو (پلی‌کربنات)", 360, CROSS_TOP - ZT, 5, "پلی‌کربنات")
    plate(pr4, "XZ", 1050, (ZT + CROSS_TOP) / 2, -357, gd, "guard")
    buy("B61", "سوئیچ ایمنی درب", box(860, 880, -380, -358, 1120, 1160), "yellow", g, 0.1, "Pilz PSEN / Schmersal")
    # HMI on a bracket at the right front column
    machined("P54", "بازوی HMI", box(1290, 1340, 300, 340, 1330, 1370), box(0, 50, 0, 40, 0, 40), "St37", "frame", g,
             "SHS 40x40x3 L50 + ورق")
    buy("B62", "جعبه‌ی HMI + DOP-107BV", comp(box(1340, 1410, 300, 540, 1260, 1440),
                                            box(1410, 1412, 330, 510, 1290, 1420)), "hmi", g, 2.5, "DOP-107BV در جعبه")
    buy("B63", "E-Stop", comp(box(1350, 1400, 540, 585, 1270, 1320), cyl("Y", (1375, 1295), 40, 585, 610)),
        "red", g, 0.2, "XB5AS8442")
    buy("B63", "E-Stop", comp(box(1235, 1285, -420, -350, 1050, 1120), cyl("Y", (1260, 1085), 40, -445, -420)),
        "red", g, 0.2, "XB5AS8442")
    buy("B64", "چراغ برج", comp(cyl("Z", (40, -300), 60, CROSS_TOP, CROSS_TOP + 100),
                               cyl("Z", (40, -300), 60, CROSS_TOP + 100, CROSS_TOP + 150)), "green", g, 0.5, "3 رنگ")
    buy("B65", "تابلو برق 600×800×250", comp(box(150, 750, -600, -352, 80, 880), box(170, 730, -603, -600, 100, 860)),
        "cab", g, 28.0, "ورق 1.5، صفحه‌ی نصب")
    buy("B66", "پدال پایی", box(1450, 1750, -100, 100, 0, 90), "yellow", g, 1.2, "پدال صنعتی با قاب")
    buy("B67", "FRL + پرشر سوئیچ", comp(box(20, 100, -420, -357, 1000, 1160)), "pneu", g, 1.2, "AW20 + ISE")


def build_all():
    build_base()
    build_gantry()
    build_x_carriage()
    build_z_head()
    build_x_drive()
    build_ink()
    build_print_station()
    build_periphery()
    # auto codes for tubes: T01.. by profile then length
    keys = sorted({(p["meta"]["profile"], p["meta"]["L"]) for p in PARTS if p["kind"] == "tube"},
                  key=lambda k: (k[0], -k[1]))
    tcode = {k: f"T{i + 1:02d}" for i, k in enumerate(keys)}
    for p in PARTS:
        if p["kind"] == "tube":
            p["code"] = tcode[(p["meta"]["profile"], p["meta"]["L"])]


# ============================================================================
# 9. CHECKS
# ============================================================================
def moved(p, dx=0.0, dz=0.0, dcup=0.0):
    s = p["shape"]
    if p["mov"] == "x":
        return s.translate(V(dx, 0, 0))
    if p["mov"] == "z":
        return s.translate(V(dx, 0, -dz))
    if p["mov"] == "c":
        return s.translate(V(dcup, 0, 0))
    return s


def bb_overlap(a, b, tol=0.05):
    return not (a.xmax <= b.xmin + tol or b.xmax <= a.xmin + tol or a.ymax <= b.ymin + tol or b.ymax <= a.ymin + tol
                or a.zmax <= b.zmin + tol or b.zmax <= a.zmin + tol)


def common_vol(a, b):
    try:
        return a.intersect(b).Volume()
    except Exception:
        return -1


EXPECTED = {("B27", "B50"), ("B27", "B44"),   # pad pressing on cliché / part
            ("B07", "P11"), ("B13", "P32"),   # belt strand clamped in its clamp
            ("B21", "B21R")}                 # piston rod inside the cylinder
FLEX = {"B08"}                               # drag chain: flexible, not checked


def interference(configs):
    res = []
    for (label, dx, dz, dcup) in configs:
        shapes = [(p, moved(p, dx, dz, dcup)) for p in PARTS]
        bbs = [s.BoundingBox() for _, s in shapes]
        movers = [i for i, (p, _) in enumerate(shapes) if p["mov"]]
        hits = []
        for i in movers:
            for j in range(len(shapes)):
                if j == i or (shapes[j][0]["mov"] and j < i and j in movers):
                    continue
                pi, pj = shapes[i][0], shapes[j][0]
                if pi["code"] in FLEX or pj["code"] in FLEX:
                    continue
                same_body = (pi["mov"] in ("x", "z") and pj["mov"] in ("x", "z") and pi["mov"] == pj["mov"])
                if same_body:
                    continue   # parts bolted together on the same moving body are checked in the static pass
                if not bb_overlap(bbs[i], bbs[j]):
                    continue
                v = common_vol(shapes[i][1], shapes[j][1])
                if v > 1.0:
                    key = tuple(sorted((pi["code"], pj["code"])))
                    hits.append((pi["code"], pi["name"], pj["code"], pj["name"], round(v), key in EXPECTED))
        res.append((label, hits))
    return res


def static_overlaps():
    shapes = [(p, p["shape"]) for p in PARTS]
    bbs = [s.BoundingBox() for _, s in shapes]
    hits = []
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            if not bb_overlap(bbs[i], bbs[j]):
                continue
            v = common_vol(shapes[i][1], shapes[j][1])
            if v > 1.0:
                a, b = shapes[i][0], shapes[j][0]
                if tuple(sorted((a["code"], b["code"]))) not in EXPECTED:
                    hits.append((a["code"], a["name"], b["code"], b["name"], round(v)))
    return hits


def min_dist(a, b):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    return d.Value()


def find(code):
    return [p for p in PARTS if p["code"] == code]


def mass_of(p):
    if p["mass"] is not None:
        return p["mass"]
    rho = RHO.get(p["mat"], STEEL)
    return p["shape"].Volume() * rho


def stiffness():
    E = 210000.0
    I_beam = (50 * 100 ** 3 - 42 * 92 ** 3) / 12.0          # RHS 100x50x4, strong axis
    I_60 = (60 ** 4 - 52 ** 4) / 12.0
    L = 1260.0 - 40.0
    F = P["F_print"]
    out = []
    for lbl, x in (("چاپ", X_PRINT), ("برداشت", X_PICK)):
        a = x - 40.0
        b = L - a
        d = (F / 2) * a * a * b * b / (3 * E * I_beam * L)
        out.append((f"خیز تیر ریل X زیر نیروی {F:.0f} N در {lbl}", d))
    # portal cross beam: two point loads (one per rail) at 170 mm from the columns
    R = F * (X_PRINT - 40) / L / 2
    a = 320 - 150.0
    Lc = 640.0
    d = R * a * a * (3 * Lc - 4 * a) / (6 * E * I_60)
    out.append(("خیز تیر عرضی پرتال جلو در محل تیر ریل", d))
    # print sub-frame crosses: centre load F/2 each on 580 span
    d = (F / 2) * 580 ** 3 / (48 * E * I_60)
    out.append(("خیز عرضی زیرقاب چاپ", d))
    return out


def x_motor_check(m_x):
    a = 2.8            # m/s^2 (500 mm in 0.9 s, trapezoid)
    F = m_x * a + 0.02 * m_x * 9.81 + 15.0          # inertia + rolling + belt/seal drag
    r = PD24 / 2 / 1000
    T = F * r / 3 / 0.9
    J_load = m_x * r * r / 9
    J_rotor = 0.9e-4 + 0.15e-4                       # NEMA24 4 N.m rotor + pulley/gearbox reflected
    return F, T, J_load / J_rotor


def write_report(inter, stat, extra):
    L = ["# گزارش بررسی مدل سه‌بعدی (خودکار)", "",
         f"تاریخ ساخت: {time.strftime('%Y-%m-%d %H:%M')} — تعداد قطعات در مدل: **{len(PARTS)}**", ""]
    L += ["## ۱. تداخل قطعات ثابت (مدل‌سازی)", ""]
    if stat:
        L += ["| قطعه | با | حجم مشترک mm³ |", "|---|---|---:|"] + [f"| {a} {an} | {b} {bn} | {v} |" for a, an, b, bn, v in stat]
    else:
        L += ["✅ هیچ دو قطعه‌ی ثابتی در هم نرفته‌اند (فقط تماس سطحی، مثل جوش و پیچ)."]
    L += ["", "## ۲. تداخل قطعات متحرک در موقعیت‌های مختلف", "",
          "«تماس عمدی» یعنی تسمه داخل گیره‌اش، شافت داخل جک، یا پد در حال فشردن روی کلیشه یا قطعه.", "",
          "| حالت | نتیجه |", "|---|---|"]
    for label, hits in inter:
        bad = [h for h in hits if not h[5]]
        ok = [h for h in hits if h[5]]
        txt = "✅ بدون برخورد" if not bad else "❌ " + "؛ ".join(f"{h[0]} {h[1]} ↔ {h[2]} {h[3]} ({h[4]} mm³)" for h in bad)
        if ok:
            txt += f" (تماس‌های عمدی: {len(ok)})"
        L.append(f"| {label} | {txt} |")
    L += ["", "## ۳. فاصله‌های کلیدی", "", "| فاصله | mm |", "|---|---:|"]
    for k, v in extra["dist"]:
        L.append(f"| {k} | {v:.1f} |")
    L += ["", "## ۴. سفتی سازه (نیروی چاپ واکنش به بالا روی ریل‌ها)", "", "| مورد | خیز mm |", "|---|---:|"]
    for k, v in extra["stiff"]:
        L.append(f"| {k} | {v:.3f} |")
    L += ["", "خیز زیر ۰.۲ mm در برابر فشردگی چند میلی‌متری پد ناچیز است.", "",
          "## ۵. جرم‌ها", "", "| مورد | kg |", "|---|---:|"]
    for k, v in extra["mass"]:
        L.append(f"| {k} | {v:.1f} |")
    F, T, ratio = extra["motor"]
    L += ["", "## ۶. بررسی دوباره‌ی موتور X با جرم واقعی مدل", "",
          f"* جرم متحرک X از مدل: **{extra['m_x']:.1f} kg** (در محاسبه‌ی اولیه ۱۴ kg فرض شده بود).",
          f"* نیروی لازم در شتاب ۲.۸ m/s²: **{F:.0f} N** → گشتاور روی موتور با گیربکس ۱:۳ و پولی ۲۴ دندانه: **{T:.2f} N·m**.",
          f"* گشتاور موجود استپر ۴ N·m در ≈۱۲۵۰ rpm: ۱.۲ تا ۱.۵ N·m → حاشیه‌ی **{1.2 / T:.1f} تا {1.5 / T:.1f} برابر** ✅",
          f"* نسبت اینرسی بار به روتور: **≈ {ratio:.1f} : 1** (برای استپر کلوزلوپ تا ۱۰:۱ مناسب است).", ""]
    with open(os.path.join(OUT, "check_report.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    return "\n".join(L)


# ============================================================================
# 10. EXPORTS
# ============================================================================
def export_all():
    os.makedirs(os.path.join(OUT, "parts_step"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "dxf"), exist_ok=True)
    # --- assembly STEP
    assy = cq.Assembly(name="TAMPO")
    for i, p in enumerate(PARTS):
        assy.add(p["shape"], name=f"{p['code']}_{i:03d}", color=cq.Color(*p["color"]))
    assy.export(os.path.join(OUT, "tampo_assembly.step"))
    # --- per-part STEP (manufactured) + DXF (plates)
    seen = {}
    for p in PARTS:
        seen.setdefault(p["code"], [p, 0])
        seen[p["code"]][1] += 1
    for code, (p, q) in seen.items():
        if p["kind"] in ("tube", "plate", "machined") and p["local"] is not None:
            cq.exporters.export(cq.Workplane().add(p["local"]), os.path.join(OUT, "parts_step", f"{code}.step"))
        if p["kind"] == "plate" and "plate" in p["meta"]:
            p["meta"]["plate"].dxf(os.path.join(OUT, "dxf", f"{code}.dxf"), q)
    # --- lists
    rows = []
    for code, (p, q) in sorted(seen.items()):
        m = mass_of(p)
        dims = p["meta"].get("dims") or f"{p['meta'].get('profile', '')} L={p['meta'].get('L', 0):g}"
        proc = {"tube": "برش اره + جوش", "buy": "خرید"}.get(p["kind"], p["meta"].get("process", ""))
        rows.append([code, p["name"], p["group"], p["kind"], p["mat"], dims, q, round(m, 2), round(m * q, 2), proc,
                     p["meta"].get("note", "")])
    with open(os.path.join(OUT, "parts_list.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["code", "name", "group", "kind", "material", "dims", "qty", "kg_each", "kg_total", "process", "note"])
        w.writerows(rows)
    tubes = [(c, p, q) for c, (p, q) in sorted(seen.items()) if p["kind"] == "tube"]
    with open(os.path.join(OUT, "cut_list.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["code", "profile", "length_mm", "qty", "cut", "used_in", "note"])
        tot = {}
        for c, p, q in tubes:
            used = " / ".join(dict.fromkeys(x["name"] for x in PARTS if x["code"] == c))
            w.writerow([c, p["meta"]["profile"], f"{p['meta']['L']:g}", q, "90°", used, p["meta"]["note"]])
            tot[p["meta"]["profile"]] = tot.get(p["meta"]["profile"], 0) + p["meta"]["L"] * q
        w.writerow([])
        for prof, l in tot.items():
            w.writerow(["TOTAL", prof, round(l), f"≈ {math.ceil(l * 1.1 / 6000)} شاخه‌ی ۶ متری (با ۱۰٪ پرت)", "", "", ""])
    return seen, rows


def export_viewer(summary):
    """Tessellate every part and embed the meshes into cad/out/tampo_viewer.html (works offline)."""
    kinds = {"tube": "لوله‌ی اسکلت", "plate": "ورق (برش لیزر)", "machined": "ساخت (تراش/فرز)", "buy": "خریدنی"}
    qty = {}
    for p in PARTS:
        qty[p["code"]] = qty.get(p["code"], 0) + 1
    parts, codes, seen = [], [], set()
    for p in PARTS:
        tol = 0.6 if p["kind"] != "buy" else 1.0
        vs, tris = p["shape"].tessellate(tol, 0.35)
        parts.append(dict(c=p["code"], g=p["group"], m=p["mov"] or "", col=[round(x, 3) for x in p["color"]],
                          v=[round(c, 1) for vv in vs for c in (vv.x, vv.y, vv.z)],
                          t=[k for tri in tris for k in tri]))
        if p["code"] not in seen:
            seen.add(p["code"])
            dims = p["meta"].get("dims") or f"{p['meta'].get('profile', '')} × {p['meta'].get('L', 0):g}"
            f = []
            if p["kind"] in ("tube", "plate", "machined"):
                f.append(f"cad/out/parts_step/{p['code']}.step")
            if p["kind"] == "plate":
                f.append(f"cad/out/dxf/{p['code']}.dxf")
            codes.append(dict(c=p["code"], n=p["name"], g=p["group"], k=kinds[p["kind"]], mt=p["mat"], d=dims,
                              q=qty[p["code"]], kg=round(mass_of(p), 2), f=f, note=p["meta"].get("note", "")))
    codes.sort(key=lambda d: d["c"])
    data = dict(meta=dict(x_pick=P["x_pick"], x_print=P["x_print"], x_travel=P["x_travel"], z_stroke=P["z_stroke"],
                          cup_stroke=P["cup_stroke"], **summary), parts=parts, codes=codes)
    tpl = open(os.path.join(HERE, "viewer_template.html"), encoding="utf-8").read()
    js = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    with open(os.path.join(OUT, "tampo_viewer.html"), "w", encoding="utf-8") as f:
        vend = os.path.join(HERE, "vendor")   # three.js r128 (MIT) inlined so the viewer needs no CDN
        three = open(os.path.join(vend, "three.min.js"), encoding="utf-8").read().replace("</script", "<\\/script")
        orbit = open(os.path.join(vend, "OrbitControls.js"), encoding="utf-8").read().replace("</script", "<\\/script")
        f.write(tpl.replace("__DATA__", js).replace("/*__THREE__*/", three).replace("/*__ORBIT__*/", orbit))


def export_ga():
    """General arrangement DXF: hidden-line projections (side, front, top) + main dimensions."""
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection

    solids = [p["shape"] for p in PARTS if p["group"] not in ("محافظ‌ها",)]
    whole = cq.Compound.makeCompound(solids)
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("VISIBLE", color=7)
    doc.layers.add("HIDDEN", color=8, linetype="HIDDEN")
    doc.layers.add("DIM", color=5)
    doc.layers.add("TEXT", color=3)
    msp = doc.modelspace()

    def project(direction, xdir, ox, oy, title):
        algo = HLRBRep_Algo()
        algo.Add(whole.wrapped)
        algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*direction), gp_Dir(*xdir))))
        algo.Update()
        algo.Hide()
        h = HLRBRep_HLRToShape(algo)
        xs, ys = [], []
        for comp_, layer in ((h.VCompound(), "VISIBLE"), (h.OutLineVCompound(), "VISIBLE"), (h.HCompound(), "HIDDEN")):
            if comp_ is None or comp_.IsNull():
                continue
            ex = TopExp_Explorer(comp_, TopAbs_EDGE)
            while ex.More():
                e = TopoDS.Edge_s(ex.Current())
                c = BRepAdaptor_Curve(e)
                d = GCPnts_QuasiUniformDeflection(c, 0.3)
                if d.IsDone() and d.NbPoints() > 1:
                    pts = [(d.Value(k).X() + ox, d.Value(k).Y() + oy) for k in range(1, d.NbPoints() + 1)]
                    if layer == "VISIBLE":
                        xs += [p[0] for p in pts]
                        ys += [p[1] for p in pts]
                    msp.add_lwpolyline(pts, dxfattribs={"layer": layer})
                ex.Next()
        if xs:
            msp.add_text(title, height=25, dxfattribs={"layer": "TEXT"}).set_placement((min(xs), min(ys) - 120))
        return (min(xs), max(xs), min(ys), max(ys)) if xs else None

    # side view from -Y: X right, Z up.   front view from +X: Y right (seen by operator), Z up.   top: X right, Y up
    b1 = project((0, -1, 0), (1, 0, 0), 0, 0, "SIDE VIEW (from -Y)  /  nama-ye janebi")
    b2 = project((1, 0, 0), (0, 1, 0), 2400, 0, "FRONT VIEW (operator side, +X)")
    b3 = project((0, 0, 1), (1, 0, 0), 0, 2600, "TOP VIEW")

    def dim(p1, p2, base, angle=0):
        msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, dxfattribs={"layer": "DIM"},
                           override={"dimtxt": 18, "dimasz": 12, "dimlfac": 1, "dimdec": 0}).render()

    if b1:
        x0, x1, z0, z1 = b1
        dim((x0, z0), (x1, z0), (0, z0 - 70))
        dim((x0, 0), (x0, z1), (x0 - 90, 0), 90)
        dim((x0, 0), (x0, Zc), (x0 - 170, 0), 90)
        dim((X_PICK, Zc), (X_PRINT, Zc), (0, z1 + 60))
    if b2:
        y0, y1, z0, z1 = b2
        dim((y0, z0), (y1, z0), (0, z0 - 70))
    msp.add_text("TAMPO pad printer - general arrangement - units mm - generated by cad/tampo_machine.py",
                 height=20, dxfattribs={"layer": "TEXT"}).set_placement((0, -400))
    doc.saveas(os.path.join(OUT, "tampo_GA.dxf"))


# ============================================================================
def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    build_all()
    print(f"built {len(PARTS)} parts in {time.time() - t0:.1f}s")
    configs = [("X=0 (خانه)، Z بالا، کاپ روی تصویر", 0, 0, 0),
               (f"X={P['x_pick']:g} برداشت، Z پایین، کاپ عقب", P["x_pick"], P["z_stroke"], -P["cup_stroke"]),
               (f"X={P['x_pick']:g} برداشت، Z بالا، کاپ روی تصویر (انتظار برداشت زودتر)", P["x_pick"], 0, 0),
               ("X=350 وسط مسیر، Z بالا، کاپ در حال حرکت", 350, 0, -185),
               (f"X={P['x_print']:g} چاپ، Z پایین", P["x_print"], P["z_stroke"], 0),
               (f"X={P['x_travel']:g} انتهای کورس، Z بالا", P["x_travel"], 0, -P["cup_stroke"]),
               (f"X={P['x_travel']:g} انتهای کورس، Z پایین (خطای فرضی)", P["x_travel"], P["z_stroke"], 0)]
    inter = interference(configs)
    stat = static_overlaps()
    print(f"checks {time.time() - t0:.1f}s")
    pad = find("B27")[0]
    cup = find("B52")[0]
    arm = find("P31")[0]
    front_cross = [p for p in PARTS if p["kind"] == "tube" and p["name"] == "تیر عرضی پرتال"
                   and p["shape"].BoundingBox().xmin > 1000][0]
    beams = [p for p in PARTS if p["name"] == "تیر ریل X"]
    sideplates = find("P14")
    dist = [
        ("پد (بالا) تا بازوی کاپ، وقتی پد منتظر روی کلیشه است", min_dist(moved(pad, P["x_pick"]), arm["shape"])),
        ("پد (بالا) تا بالای کاپ", min_dist(moved(pad, P["x_pick"]), cup["shape"])),
        ("پد (پایین، برداشت) تا کاپ عقب‌رفته", min_dist(moved(pad, P["x_pick"], P["z_stroke"]),
                                                     moved(cup, dcup=-P["cup_stroke"]))),
        ("صفحه‌ی کناری هد Z (پایین) تا تیر ریل", min(min_dist(moved(s, P["x_print"], P["z_stroke"]), b["shape"])
                                                   for s in sideplates for b in beams)),
        ("پد در انتهای کورس تا تیر عرضی پرتال جلو", min_dist(moved(pad, P["x_travel"]), front_cross["shape"])),
        ("فضای آزاد بالای قطعه تا زیر تیر عرضی جلو (دسترسی دست)", CROSS_BOT - Zc),
        ("عرض دهانه‌ی جلو بین ستون‌ها", P["base_W"] - 2 * P["tb"]),
    ]
    m_all = sum(mass_of(p) for p in PARTS)
    m_x = sum(mass_of(p) for p in PARTS if p["mov"] in ("x", "z"))
    m_z = sum(mass_of(p) for p in PARTS if p["mov"] == "z")
    m_c = sum(mass_of(p) for p in PARTS if p["mov"] == "c")
    m_frame = sum(mass_of(p) for p in PARTS if p["kind"] == "tube")
    mass = [("کل دستگاه (بدون تابلو)", m_all - 28), ("اسکلت لوله‌ای", m_frame), ("متحرک X (کالسکه + هد Z)", m_x),
            ("متحرک Z", m_z), ("متحرک کاپ", m_c)]
    extra = dict(dist=dist, stiff=stiffness(), mass=mass, m_x=m_x, motor=x_motor_check(m_x))
    rep = write_report(inter, stat, extra)
    print(rep)
    if not QUICK:
        export_all()
        print(f"step/dxf/csv {time.time() - t0:.1f}s")
        bb = cq.Compound.makeCompound([p["shape"] for p in PARTS]).BoundingBox()
        export_viewer(dict(L=round(bb.xlen), W=round(bb.ylen), H=round(bb.zlen), Zc=Zc, m_all=round(m_all - 28),
                           m_x=round(m_x, 1), n_parts=len(PARTS), n_codes=len({p["code"] for p in PARTS}),
                           n_cfg=len(inter), n_ok=sum(1 for _, h in inter if not [x for x in h if not x[5]])))
        print(f"viewer {time.time() - t0:.1f}s")
        export_ga()
        print(f"GA {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
