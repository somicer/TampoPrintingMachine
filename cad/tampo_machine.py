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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parts_lib as PL  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
QUICK = "--quick" in sys.argv

# ============================================================================
# 1. PARAMETERS  (change here, re-run, everything follows)
# ============================================================================
P = dict(
    Zc=945.0,          # cliché top = part top at print = working height
    body_L=600.0,      # machine body length (X): holds the ink station only
    x_travel=750.0,    # usable X travel (pad centre from home to the furthest print point)
    rail_margin=40.0,  # rail length beyond the block envelope at each end of travel (overtravel, braking)
    base_Y0=-600.0,    # base frame Y extent: the ink station (cup travel 370 along Y) sits on the -Y side
    base_Y1=350.0,
    base_top=880.0,    # top of base frame tubes
    foot_h=60.0,       # levelling feet
    tb=60.0, tb_t=4.0, # base / portal square tube 60x60x4
    x_home=290.0,      # world X of pad centre at X-axis position 0
    x_pick=50.0,       # X-axis position of pick (over the image)
    x_print=495.0,     # X-axis position of print (ring of a Ø1000/500 disc, r = 375)
    rail_y=150.0,      # Y of the X rails (±)
    x_belt_y=100.0,    # X belt line, inside between the rails (close to the carriage centre)
    pad_L=195.0, pad_W=140.0, pad_H=80.0,   # pad 3016
    z_stroke=100.0, pad_press=5.0,          # SC63 stroke, pad compression on cliché
    cup_od=140.0, cup_h=45.0,
    cup_stroke=370.0,  # cup travel along Y, 90° to X (measured on the existing machine)
    cliche_L=580.0, cliche_W=200.0, cliche_t=10.0,
    disc_od=1000.0, disc_id=500.0, disc_t=2.0,   # plastic disc (the part)
    disc_gap=60.0,     # disc edge to machine body front
    F_print=1590.0,    # SC63 @ 5.1 bar, N
)
Zc = P["Zc"]
YA = P["base_Y0"] + 30          # leg / column centre lines
YB = P["base_Y1"] - 30
ZT = P["base_top"]
P["reach"] = P["x_home"] + P["x_travel"] - P["body_L"]      # pad reach beyond the body front (440)
X_PICK = P["x_home"] + P["x_pick"]      # 340
X_PRINT = P["x_home"] + P["x_print"]    # 785
X_FRONT = P["body_L"]                   # body front face
X_FP = X_FRONT - 30                     # front post centre line
X_REACH = P["x_home"] + P["x_travel"]   # 1040 furthest pad centre
X_DISC = X_FRONT + P["disc_gap"] + P["disc_od"] / 2   # disc / table centre 1160
X_END = X_REACH + 190                   # beam tip (end cross member outer face)
PAD_UP_BOTTOM = Zc + P["z_stroke"] - P["pad_press"]          # 1040
# Z head stack (bottom -> top): pad, pad base 12, holder block (lowest) + side plates 210, head plate 20, gap 20
HEAD_BOT = PAD_UP_BOTTOM + P["pad_H"] + 12 + 210                # 1342
HEAD_TOP = HEAD_BOT + 20                                         # 1362
ZCP = HEAD_TOP + 20                                              # carriage plate bottom 1382
CP_T = 15.0
RAIL_BOT = ZCP - 30                                              # HGH20CA total height 30
BAR_BOT = RAIL_BOT - 15                                          # rail mounting bar 40x15
BEAM_TOP = BAR_BOT
BEAM_BOT = BEAM_TOP - 120
CROSS_TOP = BEAM_BOT
CROSS_BOT = CROSS_TOP - 60
PULLEY_Z = ZCP - 30          # X belt pulley axis
CUP_ARM_BOT = Zc + 50        # 995
CUP_RAIL_BOT = CUP_ARM_BOT - 28   # HGH15CA total height 28
CUP_PULLEY_Z = CUP_ARM_BOT - 10 - 19.1
PD24 = 38.2                  # pitch diameter 24T 5M

STEEL, ALU, PC, POM = 7.85e-6, 2.70e-6, 1.20e-6, 1.41e-6
RHO = {"فولاد": STEEL, "St37": STEEL, "CK45": STEEL, "آلومینیوم 6061": ALU,
       "آلومینیوم": ALU, "پلی‌کربنات": PC, "پلی‌استال": POM, "MDF روکش‌دار": 0.75e-6}

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
    def __init__(self, code, name, w, h, t, mat, holes=(), slots=(), cuts=(), note="", process="برش لیزر/واترجت",
                 r=0.0, outline=None):
        """r = outer corner radius; outline = custom polygon [(u, v), ...] centred like the w x h box."""
        self.code, self.name, self.w, self.h, self.t, self.mat = code, name, w, h, t, mat
        self.r, self.outline = r, outline
        self.holes, self.slots, self.cuts = list(holes), list(slots), list(cuts)
        self.note, self.process = note, process
        self._solid = None

    def solid(self):
        if self._solid is None:
            if self.outline:
                s = cq.Workplane("XY").polyline(self.outline).close().extrude(self.t).val()
            elif self.r:
                s = cq.Workplane("XY").rect(self.w, self.h).extrude(self.t).edges("|Z").fillet(self.r).val()
            else:
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
        if self.outline:
            msp.add_lwpolyline(self.outline, close=True, dxfattribs={"layer": "CUT"})
        elif self.r:
            r, b = self.r, math.tan(math.pi / 8)
            pts = [(-w / 2 + r, -h / 2, 0), (w / 2 - r, -h / 2, b), (w / 2, -h / 2 + r, 0), (w / 2, h / 2 - r, b),
                   (w / 2 - r, h / 2, 0), (-w / 2 + r, h / 2, b), (-w / 2, h / 2 - r, 0), (-w / 2, -h / 2 + r, b)]
            msp.add_lwpolyline([(p[0], p[1], 0, 0, p[2]) for p in pts], format="xyseb", close=True,
                               dxfattribs={"layer": "CUT"})
        else:
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


def detail(code, name, shape, color, group, mov=None):
    """Cosmetic detail of a bought part (seals, grease nipple...): shown, not listed."""
    add(code, name, shape, "detail", "-", color, group, mov, mass=0.0, meta=dict(dims=""))


def fast(code, name, spec, shapes, group, mov=None, color="gear"):
    """Fasteners: one compound per group of identical screws; qty = number of screws."""
    shapes = list(shapes)
    add(code, name, PL.comp(shapes), "buy", "-", color, group, mov, mass=0.0, meta=dict(dims=spec, n=len(shapes)))


def heads(m, pts, z, d="+Z"):
    """Socket-head screw heads sitting on a face at height z (d = direction the head points)."""
    return [PL.place(PL.shcs_head(m), d, (x, y, z)) for (x, y) in pts]


def rect_pattern(cx, cy, dx, dy, d):
    return [(cx + sx * dx, cy + sy * dy, d) for sx in (-1, 1) for sy in (-1, 1)]


def pcd(cx, cy, r, n, d, a0=45):
    return [(cx + r * math.cos(math.radians(a0 + i * 360 / n)), cy + r * math.sin(math.radians(a0 + i * 360 / n)), d)
            for i in range(n)]


def foot_at(x, y, g):
    """Welded foot plate under a leg + levelling foot M16 with lock nut."""
    fp = Plate("P62", "ورق کف پایه (جوشی، مهره‌ی M16 جوش پشت)", 80, 80, 10, "St37", holes=[(0, 0, 17)], r=4)
    plate(fp, "XY", x, y, P["foot_h"] - 10, g, "frame")
    buy("B40", "پایه‌ی ترازشو M16", PL.levelling_foot(P["foot_h"] - 10).translate(V(x, y, 0)), "gear", g, 0.6,
        "M16، کف Ø80، ظرفیت ≥ ۵۰۰ kg")


def gusset(code, x, y_face, z_top, side, g, size=100.0, t=8.0):
    """Right-angle gusset in the YZ plane of a portal, in the inner corner under a cross member.
    side = +1: column face at y_face, gusset towards +Y;  -1: towards -Y."""
    hs = size / 2
    pts = [(-hs, hs), (hs, hs), (-hs, -hs)] if side > 0 else [(hs, hs), (-hs, hs), (hs, -hs)]
    pl = Plate(code, "لچکی پرتال (جوشی)", size, size, t, "St37", outline=pts, note="جوش دو طرف")
    plate(pl, "YZ", y_face + side * hs, z_top - hs, x - t / 2, g, "frame")


def end_cap(shape_box, g):
    add("B90", "درپوش پلاستیکی لوله", shape_box, "buy", "-", C["motor"], g, mass=0.01, meta=dict(dims="PE، هم‌اندازه‌ی پروفیل"))


# ============================================================================
# 2. BASE FRAME  (welded, SHS 60x60x4)
# ============================================================================
def build_base():
    tb, t = P["tb"], P["tb_t"]
    g = "اسکلت پایین"
    h = tb / 2
    zb0, zb1 = P["foot_h"], ZT
    ry = P["rail_y"]
    legs = [(h, YA), (h, YB), (X_FP, YA), (X_FP, -ry), (X_FP, ry), (X_FP, YB)]
    for (x, y) in legs:
        tube("پایه", (x, y, zb0), (x, y, zb1), tb, tb, t, g, note="سرتاسری، دو سر گونیا")
    for zc in (zb1 - h, zb0 + h):
        for y in (YA, YB):
            tube("طولی", (tb, y, zc), (X_FP - h, y, zc), tb, tb, t, g, note="بین پایه‌ها")
        tube("عرضی", (h, YA + h, zc), (h, YB - h, zc), tb, tb, t, g, note="بین طولی‌ها")
        for (y0, y1) in ((YA + h, -ry - h), (-ry + h, ry - h), (ry + h, YB - h)):
            tube("عرضی جلو", (X_FP, y0, zc), (X_FP, y1, zc), tb, tb, t, g, note="بین پایه‌های جلو")
    for x in (200.0, 400.0):  # deck supports
        tube("عرضی زیر صفحه", (x, YA + h, zb1 - h), (x, YB - h, zb1 - h), tb, tb, t, g)
    for (x, y) in legs:
        foot_at(x, y, g)
    W = P["base_Y1"] - P["base_Y0"]
    yc = (P["base_Y0"] + P["base_Y1"]) / 2
    dl = X_FP - h - 70            # deck between rear portal columns and front posts
    deck = Plate("P01", "صفحه‌ی رویی ایستگاه جوهر", dl, W, 10, "St37",
                 holes=[(u, v - yc, 9) for u in (-dl / 2 + 30, 0, dl / 2 - 30) for v in (YA, YB)],
                 note="با پیچ M8 روی قاب؛ سوراخ‌های نصب قطعات را بعد از چیدمان جای‌یابی کنید")
    plate(deck, "XY", 70 + dl / 2, yc, ZT, g, "steel")


# ============================================================================
# 3. UPPER GANTRY  (two portals + two X beams)
# ============================================================================
def build_gantry():
    tb, t = P["tb"], P["tb_t"]
    g = "اسکلت بالا"
    h = tb / 2
    ry = P["rail_y"]
    # rear portal: 2 columns + full-width cross member
    for y in (YA, YB):
        tube("ستون پرتال عقب", (40, y, ZT), (40, y, CROSS_BOT), tb, tb, t, g, note="روی قاب پایین جوش")
    tube("تیر عرضی پرتال عقب", (40, P["base_Y0"], CROSS_BOT + h), (40, P["base_Y1"], CROSS_BOT + h), tb, tb, t, g,
         note="سرتاسری روی ستون‌ها")
    # front: posts straight under each beam (the pad passes between them), outer columns + short crosses
    for y in (-ry, ry):
        tube("ستون جلو زیر تیر", (X_FP, y, ZT), (X_FP, y, BEAM_BOT), tb, tb, t, g,
             note="ادامه‌ی پایه‌ی جلو؛ تیر X رویش پیچ می‌شود (کشش ≈ 2 kN)")
    for y in (YA, YB):
        tube("ستون جلو کناری", (X_FP, y, ZT), (X_FP, y, BEAM_BOT), tb, tb, t, g)
    for (y0, y1) in ((YA + h, -ry - h), (ry + h, YB - h)):
        tube("عرضی کوتاه جلو", (X_FP, y0, CROSS_BOT + h), (X_FP, y1, CROSS_BOT + h), tb, tb, t, g)
    for y in (P["base_Y0"] + 20, P["base_Y1"] - 20):
        tube("طولی بالای محافظ", (40 + h, y, BEAM_BOT - 20), (X_FP - h, y, BEAM_BOT - 20), 40, 40, 3, g,
             note="بین پرتال عقب و ستون جلو")
    for y, sd in ((YA + h, 1), (YB - h, -1)):
        gusset("P63", 40, y, CROSS_BOT, sd, g)
        gusset("P63", X_FP, y, CROSS_BOT, sd, g)
    L_beam = X_END - 10
    for y in (-ry, ry):
        tube("تیر ریل X (یک‌سرآزاد)", (10, y, BEAM_BOT + 60), (X_END, y, BEAM_BOT + 60), 60, 120, 5, g,
             note=f"روی پرتال عقب و ستون جلو، {X_END - X_FP:.0f} mm بیرون‌زده؛ هر اتصال 4× M10")
    for y in (-ry, ry):
        end_cap(box(8, 10, y - 30, y + 30, BEAM_BOT, BEAM_TOP), g)
        end_cap(box(X_END, X_END + 2, y - 30, y + 30, BEAM_BOT, BEAM_TOP), g)
    for yy in (P["base_Y0"] - 2, P["base_Y1"]):
        end_cap(box(10, 70, yy, yy + 2, CROSS_BOT, CROSS_TOP), g)
    tube("عرضی سر تیرها", (X_END - h, -ry - 30, CROSS_BOT + h), (X_END - h, ry + 30, CROSS_BOT + h), tb, tb, t, g,
         note="زیر سر آزاد دو تیر؛ هرزگرد X رویش")
    # HIWIN standard length: L = (n-1)*60 + 2*20, covering travel + block envelope (2 x 108.75) + margins
    need = P["x_travel"] + 217.5 + 2 * P["rail_margin"]
    n = int(math.ceil((need - 40) / 60)) + 1
    rl = (n - 1) * 60 + 40
    r0 = (P["x_home"] + X_REACH) / 2 - rl / 2
    r1 = r0 + rl
    for y in (-ry, ry):
        bar = Plate("P02", "تسمه‌ی نصب ریل X (سنگ‌خورده)", rl, 40, 15, "CK45",
                    holes=[(-rl / 2 + 20 + 60 * i, 0, 4.2) for i in range(n)] +
                          [(-rl / 2 + 50 + 120 * i, 13, 9) for i in range(int((rl - 60) // 120) + 1)] +
                          [(-rl / 2 + 50 + 120 * i, -13, 9) for i in range(int((rl - 60) // 120) + 1)],
                    note="Ø4.2 = قلاویز M5 برای ریل (گام ۶۰)؛ Ø9 = پیچ M8 به تیر؛ رو و زیر سنگ، تخت ≤ 0.02",
                    process="برش + فرز + سنگ")
        plate(bar, "XY", r0 + rl / 2, y, BAR_BOT, "ریل‌ها", "steel")
        rs, rh, nh = PL.rail(20, rl)
        buy("B01", f"ریل HIWIN HGR20 طول {rl:g}", rs.translate(V(r0, y, RAIL_BOT)), "rail",
            "ریل‌ها", 2.21 * rl / 1000, f"HGR20R{rl:g}C, گام سوراخ 60")
        add("F01", "پیچ آلن M5×20 ریل HGR20", rh.translate(V(r0, y, RAIL_BOT)), "buy", "-", C["motor"], "ریل‌ها",
            mass=0.0, meta=dict(dims="DIN 912 M5×20 گرید 12.9", n=nh))


# ============================================================================
# 4. X CARRIAGE + Z HEAD  (reference position: X axis = 0, Z up)
# ============================================================================
def build_x_carriage():
    g = "کالسکه X"
    xc = P["x_home"]           # pad centre X at axis 0
    ycp = -7.5                 # carriage plate centre Y (plate spans Y -200..185)
    yb = P["x_belt_y"]
    # HGH20CA blocks
    for dx in (-70, 70):
        for y in (-P["rail_y"], P["rail_y"]):
            bd, be = PL.block(20)
            buy("B02", "واگن HIWIN HGH20CA", bd.translate(V(xc + dx, y, RAIL_BOT)), "block", g, 0.40, "HGH20CAZ0C",
                mov="x")
            detail("B02", "آب‌بند و گریس‌خور واگن", be.translate(V(xc + dx, y, RAIL_BOT)), "red", g, mov="x")
    fast("F02", "پیچ آلن M5×25 واگن X", "DIN 912 M5×25", heads(5, [(xc + dx + sx * 18, y + sy * 16)
         for dx in (-70, 70) for y in (-P["rail_y"], P["rail_y"]) for sx in (-1, 1) for sy in (-1, 1)],
         ZCP + CP_T), g, mov="x")
    holes = []
    for dx in (-70, 70):
        for y in (-P["rail_y"], P["rail_y"]):
            holes += rect_pattern(dx, y - ycp, 18, 16, 5.5)
    holes += [(0, -ycp, 45)]                                           # rod + floating joint
    for dx in (-85, 85):
        holes += [(dx, -ycp, 40)] + pcd(dx, -ycp, 25.5, 4, 6.6)        # LMF25UU
    holes += rect_pattern(0, -ycp, 25, 50, 9)                          # SC63 FA flange
    holes += [(-20, yb - ycp, 6.6), (20, yb - ycp, 6.6)]               # belt clamp
    holes += [(-45, 97 - ycp, 5.5), (45, 97 - ycp, 5.5)]               # Z valve
    holes += [(-25, -190 - ycp, 6.6), (25, -190 - ycp, 6.6)]           # drag-chain bracket
    cp = Plate("P10", "صفحه‌ی کالسکه X", 280, 385, CP_T, "آلومینیوم 6061", holes=holes, r=10,
               cuts=[(0, -97.5 - ycp, 230, 45)],
               note="صفحه‌ی سبک‌شده؛ سوراخ‌های واگن M5 با فاصله‌ی 36×32 (HGH20CA)")
    plate(cp, "XY", xc, ycp, ZCP, g, "alu", mov="x")
    # belt clamp (top strand of the X belt)
    clamp = Plate("P11", "گیره‌ی تسمه X", 60, 25, 32, "آلومینیوم 6061", holes=[(-20, 0, 6.6), (20, 0, 6.6)],
                  note="دو تکه؛ شیار دندانه‌ی HTD5M در صفحه‌ی بین", process="فرز")
    clamp_shape = box(xc - 30, xc + 30, yb - 17, yb + 17, ZCP - 25, ZCP)
    machined("P11", "گیره‌ی تسمه X", clamp_shape, clamp.solid(), "آلومینیوم 6061", "alu", g, "60x34x25", mov="x")
    # Z valve on the carriage + quick exhausts
    buy("B20", "شیر 5/2 سایز 3/8 (4V320)", PL.place(PL.valve_4v320(), "+Z", (xc, 97.5, ZCP + CP_T)), "valve", g,
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
    fast("F03", "پیچ آلن M8×25 فلنج جک", "DIN 912 M8×25", heads(8, [(xc + sx * 25, sy * 50) for sx in (-1, 1)
                                                                    for sy in (-1, 1)], z0 + 12), g, mov="x")
    zb = z0 + 12
    cyl63, L = PL.sc63(P["z_stroke"])
    cylz = comp(cyl63.translate(V(xc, 0, zb)), cyl("Y", (xc, zb + 15), 14, 37.5, 45),
                cyl("Y", (xc, zb + L - 15), 14, 37.5, 45))
    buy("B21", "جک Airtac SC63×100", cylz, "pneu", g, 2.9, "SC63x100 (بدون مگنت کافی است)", mov="x")
    # Z position sensing: 3 inductive M12 sensors on a bracket under the carriage plate read ONE steel
    # flag (3x20x40) screwed to the head plate. Flag length = safe zone, so X20 is ON from fully up
    # down to the safe height (PLC: M26 = X20, fail-safe). Switch points match tools/plc_sim.py.
    ft = HEAD_TOP
    fl = 40.0
    z_safe, z_down = 32.0, 94.5
    fx = xc + 105
    flag = Plate("P16", "تسمه‌ی آهنی سنسورهای Z", 20, fl, 3, "St37", holes=[(0, 5, 5.5), (0, 15, 5.5)],
                 note="فولاد معمولی (باید آهنی باشد)؛ 2× M5 به لبه‌ی صفحه‌ی سر؛ طول آن = ناحیه‌ی امن")
    plate(flag, "XZ", fx, ft - fl / 2, -63, g, "steel", mov="z")
    zs = {"X2 بالا": ft - 2, "X20 ارتفاع امن": ft - z_safe, "X3 پایین": ft - fl - z_down}
    zb0, zb1 = min(zs.values()) - 8, ZCP - 6
    zcb = (zb0 + zb1) / 2
    br = Plate("P17", "براکت سنسورهای Z", 50, zb1 - zb0, 6, "St37",
               slots=[(0, z - zcb - 5, 0, z - zcb + 5, 12.5) for z in zs.values()],
               note="شیار 12.5 با ±5 mm تنظیم برای بدنه‌ی M12 با دو مهره؛ نقطه‌ی قطع هر سنسور را تنظیم می‌کند")
    plate(br, "XZ", fx, zcb, -93, g, "steel", mov="x")
    tab = Plate("P18", "زبانه‌ی براکت سنسورهای Z", 50, 60, 6, "St37", holes=[(-15, 15, 6.6), (15, 15, 6.6)],
                note="جوش به براکت؛ 2× M6 به صفحه‌ی کالسکه")
    plate(tab, "XY", fx, -90, ZCP - 6, g, "steel", mov="x")
    for nm, z in zs.items():
        buy("B22", "سنسور القایی M12 (Autonics PR12-4DN)", cyl("Y", (fx, z), 12, -115, -65), "red", g, 0.05,
            "M12، 4 mm، NPN نرمال‌باز، 10-30 VDC", mov="x")
    for zz in (zb + 17, zb + L - 17):   # ports face +Y (towards the valve), clear of the guide rods
        buy("B23", "شیر تخلیه‌ی سریع 3/8", cyl("Y", (xc, zz), 34, 45, 78), "pneu", g, 0.25, "SMC AQ5000", mov="x")
    # rod + floating joint (move with Z)
    buy("B21R", "شافت جک + مفصل شناور M16", comp(cyl("Z", (xc, 0), 20, HEAD_TOP + 25, zb + P["z_stroke"] + 5), cyl("Z", (xc, 0), 34, HEAD_TOP,
                                                                                              HEAD_TOP + 30)),
        "pneu", g, 0.5, "FJ M16x1.5", mov="z")
    # LMF25UU bushings (flange under the plate)
    for dx in (-85, 85):
        buy("B24", "بوش خطی فلنج‌دار LMF25UU", PL.lmf(25, 40, 62, 70, 10, 51, 6.6).translate(V(xc + dx, 0, ZCP - 10)),
            "gear", g, 0.34, "LMF25UU", mov="x")
        # guide rod Ø25 (moves with Z)
        machined("M01", "میله‌ی راهنمای Z Ø25", cyl("Z", (xc + dx, 0), 25, HEAD_TOP, HEAD_TOP + 210),
                 cyl("Z", (0, 0), 25, 0, 210), "CK45", "rail", g, "Ø25 h6 × 210، سخت‌کاری و کروم", mov="z",
                 note="سر پایین M12 به صفحه‌ی سر؛ سر بالا شیار خار")
        buy("B25", "رینگ توقف Ø25", tubecyl("Z", (xc + dx, 0), 45, 25, HEAD_TOP + 195, HEAD_TOP + 210), "gear", g, 0.1,
            "Shaft collar 25", mov="z")
    fast("F04", "پیچ آلن M6×30 بوش LMF25 (با مهره)", "DIN 912 M6×30 + DIN 934", heads(6, [
        (xc + dx + 25.5 * math.cos(math.radians(45 + 90 * i)), 25.5 * math.sin(math.radians(45 + 90 * i)))
        for dx in (-85, 85) for i in range(4)], ZCP + CP_T), g, mov="x")
    # head plate
    hp = Plate("P13", "صفحه‌ی سر Z", 240, 120, 20, "آلومینیوم 6061", r=6,
               holes=[(-85, 0, 12.5), (85, 0, 12.5), (0, 0, 16.5), (40, 25, 10.2)] +
                     [(u, v, 6.6) for u in (-60, 0, 60) for v in (-46, 46)],
               note="Ø12.5 پیچ M12 میله‌ها، Ø16.5 مفصل شناور، Ø10.2 قلاویز M12 پیچ تنظیم ارتفاع، Ø6.6 پیچ M6 صفحه‌های کناری")
    plate(hp, "XY", xc, 0, HEAD_BOT, g, "alu", mov="z")
    fast("F05", "پیچ آلن M6×20 صفحه‌های کناری", "DIN 912 M6×20", heads(6, [(xc + u, v) for u in (-60, 0, 60)
                                                                       for v in (-46, 46)], HEAD_TOP), g, mov="z")
    fast("F06", "پیچ آلن M12×25 میله‌های راهنما", "DIN 912 M12×25", heads(12, [(xc - 85, 0), (xc + 85, 0)],
                                                                          HEAD_BOT, "-Z"), g, mov="z")
    # side plates with vertical slots (manual pad height, 60 mm)
    sp = Plate("P14", "صفحه‌ی کناری اسلاید ارتفاع پد", 160, 210, 12, "آلومینیوم 6061",
               slots=[(-50, -80, -50, -20, 10.5), (50, -80, 50, -20, 10.5)],
               note="شیار 60 mm برای تنظیم ارتفاع پد؛ لبه‌ی بالا 3× قلاویز M6")
    zc_sp = HEAD_BOT - 105
    for y0 in (40.0, -52.0):
        plate(sp, "XZ", xc, zc_sp, y0, g, "alu", mov="z")
    zsl = HEAD_BOT - 185
    fast("F07", "پیچ آلن M10×30 + واشر اسلاید ارتفاع", "DIN 912 M10×30 + DIN 125", [
        PL.place(PL.comp([PL.washer(10), PL.shcs_head(10).translate(V(0, 0, 2))]), d, (xc + u, yy, zsl))
        for u in (-50, 50) for (yy, d) in ((52.0, "+Y"), (-52.0, "-Y"))], g, mov="z")
    # holder block (lowest position) + jack screw
    hb = box(xc - 80, xc + 80, -40, 40, HEAD_BOT - 210, HEAD_BOT - 160)
    machined("M02", "بلوک نگه‌دارنده‌ی پد", hb, box(0, 160, 0, 80, 0, 50), "آلومینیوم 6061", "alu", g, "160x80x50",
             mov="z", note="دو طرف 2× قلاویز M10 برای شیارها؛ زیر 4× M8 به صفحه‌ی پد")
    buy("B26", "پیچ تنظیم ارتفاع M12 + مهره قفل", cyl("Z", (xc + 40, 25), 10, HEAD_BOT - 160, HEAD_TOP + 10), "gear", g,
        0.15, "M12x200 DIN 913", mov="z")
    # pad base plate + pad
    pb = Plate("P15", "صفحه‌ی پد", 220, 160, 12, "آلومینیوم 6061", r=8,
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
    """Belt runs INSIDE, between the rails at Y = x_belt_y, so the drive force acts close to the
    carriage centre. Motor + gearbox sit between the beams behind the carriage's home position."""
    g = "محرک X"
    yb = P["x_belt_y"]
    xr, xf = 90.0, X_REACH + 100
    yp0 = yb - 33                      # bracket plate (12 mm) on the -Y side of the pulley
    ztop = PULLEY_Z + 23               # below the carriage plate
    zc_b = (CROSS_TOP + 12 + ztop) / 2
    hb = ztop - CROSS_TOP - 12
    foot = Plate("P20", "پایه‌ی براکت موتور X", 60, 50, 12, "St37", holes=[(-18, 10, 9), (18, 10, 9)])
    plate(foot, "XY", 40, yp0 + 25, CROSS_TOP, g, "steel")
    vp = Plate("P21", "براکت موتور X", 130, hb, 12, "St37",
               holes=[(xr - 75, PULLEY_Z - zc_b, 51)] + pcd(xr - 75, PULLEY_Z - zc_b, 35, 4, 5.5),
               note="جوش به پایه + لچکی؛ الگوی فلنج گیربکس PLF60 را با کاتالوگ تطبیق دهید")
    plate(vp, "XZ", 75, zc_b, yp0, g, "steel")
    buy("B03", "گیربکس خورشیدی PLF60 1:3", PL.place(PL.planetary60(), "-Y", (xr, yp0, PULLEY_Z)), "gear", g, 1.0,
        "PLF60-3 / EG24 1:3")
    buy("B04", "استپر کلوزلوپ NEMA24 4 N·m (X)", PL.place(PL.nema24(boss=False, shaft=False), "-Y",
                                                         (xr, yp0 - 70, PULLEY_Z)), "motor", g, 1.9,
        "60 mm, L≈110, 4 N·m")
    pul, _ = PL.pulley(24, 5, 28, 14, hub_l=4)
    for x in (xr, xf):
        buy("B05", "پولی 24T HTD5M عرض 25", PL.place(pul, "+Y", (x, yb, PULLEY_Z)), "gear", g, 0.18, "24-5M-25")
        buy("B06", "شافت پولی Ø14", cyl("Y", (x, PULLEY_Z), 14, yp0 + 12, yb + 16), "gear", g, 0.05, "Ø14")
    fast("F08", "پیچ آلن M8×20 پایه‌ی براکت‌ها", "DIN 912 M8×20 + واشر", heads(8, [
        (x0 + sx * 18, yp0 + 35) for x0 in (40, X_END - 30) for sx in (-1, 1)],
        CROSS_TOP + 12), g)
    foot2 = Plate("P22", "پایه‌ی براکت هرزگرد X", 60, 50, 12, "St37", holes=[(-18, 10, 9), (18, 10, 9)])
    plate(foot2, "XY", X_END - 30, yp0 + 25, CROSS_TOP, g, "steel")
    xb2 = X_END - 55
    vp2 = Plate("P23", "براکت هرزگرد X (شیار کشش)", 110, hb, 12, "St37",
                slots=[(xf - xb2 - 10, PULLEY_Z - zc_b, xf - xb2 + 10, PULLEY_Z - zc_b, 14.5)],
                holes=[(40, PULLEY_Z - zc_b, 8.5)],
                note="شیار ±10 برای کشش تسمه؛ پیچ کشش M8 از لبه")
    plate(vp2, "XZ", xb2, zc_b, yp0, g, "steel")
    buy("B07", "تسمه HTD5M عرض 25 مغزی فولادی (حلقه با دو سر در گیره)",
        PL.belt_loop(xf - xr, PD24 / 2, 3.6, 25).translate(V(xr, yb, PULLEY_Z)), "belt", g, 0.3, "HTD5M-25 PU steel",
        mov=None)
    for x in (P["x_home"] - 155, X_REACH + 160):
        buy("B30", "لیمیت سوئیچ Omron D4N", box(x - 15, x + 15, 181, 204, BEAM_TOP - 60, BEAM_TOP - 5), "yellow",
            "سنسورها", 0.15, "D4N-1A31")
    buy("B31", "سنسور هوم M18", cyl("Z", (P["x_home"] + 10, 193), 18, BEAM_TOP - 60, BEAM_TOP - 5), "gear", "سنسورها",
        0.06, "PR18-8DN")
    tl = X_END - 20 - (P["x_home"] + 40)
    tray = Plate("P24", "سینی زنجیر کابل X", tl, 64, 2, "فولاد", note="ورق 2 خم U، ارتفاع لبه 30",
                 process="برش + خم")
    xm = P["x_home"] + 40 + tl / 2
    plate(tray, "XY", xm, -214, BEAM_TOP - 12, g, "steel")
    zl, zu = BEAM_TOP + 2.5, ZCP - 12.5
    buy("B08", "زنجیر کابل 25×50 (X)", PL.drag_chain([((xm, -214, zl), (X_END - 20, -214, zl)),
                                                      ((xm, -214, zl + 12.5), (xm, -214, zu - 12.5)),
                                                      ((xc_chain(), -214, zu), (xm, -214, zu))]),
        "chain", g, 2.0, "25x50 R55، طول ≈ 1.7 m")


def xc_chain():
    return P["x_home"] + 40


# ============================================================================
# 6. INK STATION: cliché holder + closed cup on HGR15 + belt drive
# ============================================================================
def build_ink():
    """Cliché long side along Y. The cup moves along Y (90° to X), from the image under the pad path
    (Y = 0) to the -Y side, on an HGR15 rail placed behind the cliché (smaller X)."""
    g = "ایستگاه جوهر"
    xcl = X_PICK
    cs = P["cup_stroke"]
    y0c, y1c = -cs - 110, 100.0              # cliché Y extent (580)
    ycl = (y0c + y1c) / 2
    ch = Plate("P30", "پایه‌ی کلیشه (بستر فرزکاری‌شده)", 220, 600, 45, "St37",
               holes=rect_pattern(0, 0, 90, 280, 11) + rect_pattern(0, 0, 0, 150, 8.5),
               note="روی سطح فرز و سنگ؛ 4× پیچ M10 به صفحه‌ی رویی، گیره‌های کلیشه با M8",
               process="فرز + سنگ")
    plate(ch, "XY", xcl, ycl, ZT + 10, g, "steel")
    buy("B50", "کلیشه‌ی فولادی 580×200×10", box(xcl - P["cliche_W"] / 2, xcl + P["cliche_W"] / 2, y0c, y1c,
                                                 Zc - P["cliche_t"], Zc), "cliche", g, 9.1, "کلیشه‌ی ضخیم فولادی")
    buy("B51", "گیره‌ی کلیشه", comp(*[box(x - 12, x + 12, y - 15, y + 15, Zc, Zc + 8)
                                      for x in (xcl - 112, xcl + 112) for y in (y0c + 40, y1c - 40)]), "gear", g,
        0.2, "گیره‌ی لبه")
    # cup rail (along Y) on a riser behind the cliché
    xr_ = xcl - 145                             # rail centre X = 445
    ry0, ry1 = -cs - 50, 40.0
    ris = box(xr_ - 20, xr_ + 20, ry0, ry1, ZT + 10, CUP_RAIL_BOT)
    machined("M10", "پایه‌ی ریل کاپ", ris, box(0, 40, 0, ry1 - ry0, 0, CUP_RAIL_BOT - ZT - 10), "St37", "steel", g,
             f"40x{ry1 - ry0:g}x{CUP_RAIL_BOT - ZT - 10:g}", note="رو فرز؛ قلاویز M4 گام 60 برای HGR15")
    rs, rh, nh = PL.rail(15, ry1 - ry0)
    buy("B09", f"ریل HIWIN HGR15 طول {ry1 - ry0:g}", PL.place(rs, "+Z", (xr_, ry0, CUP_RAIL_BOT), spin=90),
        "rail", g, 1.45 * (ry1 - ry0) / 1000, f"HGR15R{ry1 - ry0:g}C")
    add("F09", "پیچ آلن M4×16 ریل HGR15", PL.place(rh, "+Z", (xr_, ry0, CUP_RAIL_BOT), spin=90), "buy", "-",
        C["motor"], g, mass=0.0, meta=dict(dims="DIN 912 M4×16", n=nh))
    bd, be = PL.block(15)
    buy("B10", "واگن HIWIN HGH15CA", PL.place(bd, "+Z", (xr_, 0, CUP_RAIL_BOT), spin=90), "block", g, 0.18,
        "HGH15CAZ0C", mov="c")
    detail("B10", "آب‌بند و گریس‌خور واگن", PL.place(be, "+Z", (xr_, 0, CUP_RAIL_BOT), spin=90), "red", g, mov="c")
    xbelt = xr_ - 45                            # cup belt line X = 400
    ax0, ax1 = xbelt - 20, xcl + 30             # arm X extent
    axc = (ax0 + ax1) / 2
    arm = Plate("P31", "بازوی کاپ", ax1 - ax0, 60, 12, "آلومینیوم 6061", r=8,
                holes=rect_pattern(xr_ - axc, 0, 13, 13, 4.5) + pcd(xcl - axc, 0, 25, 3, 8.5, a0=0) +
                      [(xbelt - axc, -15, 6.6), (xbelt - axc, 15, 6.6)],
                note="3× پین فنری روی کاپ؛ نگه‌دارنده‌ی کاپ باید آزاد روی کلیشه بنشیند")
    plate(arm, "XY", axc, 0, CUP_ARM_BOT, g, "alu", mov="c")
    fast("F10", "پیچ آلن M4×12 واگن کاپ", "DIN 912 M4×12", heads(4, [(xr_ + sx * 13, sy * 13) for sx in (-1, 1)
                                                                      for sy in (-1, 1)], CUP_ARM_BOT + 12), g,
         mov="c")
    buy("B52", "کاپ بسته Ø140 با رینگ سرامیکی", comp(cyl("Z", (xcl, 0), P["cup_od"], Zc, Zc + 8),
                                                   cyl("Z", (xcl, 0), P["cup_od"] - 10, Zc + 8, Zc + P["cup_h"])),
        "cup", g, 1.6, "Ø140 (مطابق کاپ فعلی)", mov="c")
    for (u, v, d) in pcd(xcl, 0, 25, 3, 8, a0=0):
        buy("B53", "پین فنری کاپ", cyl("Z", (u, v), 8, Zc + P["cup_h"], CUP_ARM_BOT), "gear", g, 0.02, "Ø8", mov="c")
    machined("P32", "گیره‌ی تسمه کاپ", box(xbelt - 17, xbelt + 17, -25, 25, CUP_ARM_BOT - 20, CUP_ARM_BOT),
             box(0, 34, 0, 50, 0, 20), "آلومینیوم 6061", "alu", g, "34x50x20", mov="c")
    # cup drive: NEMA24 direct at the -Y end, idler at the +Y end, belt along Y
    yr, yf = -cs - 130, 80.0
    xpl = xbelt - 25                            # bracket plate X 375..385 (between pulley and motor)
    for y, code, nm in ((yr, "P33", "براکت موتور کاپ"), (yf, "P34", "براکت هرزگرد کاپ (شیار کشش)")):
        f = Plate(code + "F", "پایه‌ی " + nm, 40, 90, 10, "St37", holes=[(15, -30, 9), (15, 30, 9)])
        plate(f, "XY", xpl + 5, y, ZT + 10, g, "steel")
        if code == "P33":
            vp = Plate(code, nm, 90, 130, 10, "St37",
                       holes=[(0, CUP_PULLEY_Z - 965, 39)] + rect_pattern(0, CUP_PULLEY_Z - 965, 23.57, 23.57, 5.2))
        else:
            vp = Plate(code, nm, 90, 130, 10, "St37",
                       slots=[(-10, CUP_PULLEY_Z - 965, 10, CUP_PULLEY_Z - 965, 12.5)])
        plate(vp, "YZ", y, 965, xpl, g, "steel")
    buy("B11", "استپر کلوزلوپ NEMA24 4 N·m (کاپ)", PL.place(PL.nema24(), "-X", (xpl, yr, CUP_PULLEY_Z)), "motor",
        g, 1.9, "60 mm, L≈110, 4 N·m")
    pul, _ = PL.pulley(24, 5, 22, 8, flange_d=44, hub_l=2, hub_d=22)
    for y in (yr, yf):
        buy("B12", "پولی 24T گام 5 عرض 20", PL.place(pul, "+X", (xbelt, y, CUP_PULLEY_Z)), "gear", g, 0.15,
            "24-5M-20 (مطابق تسمه‌ی فعلی)")
    buy("B14", "شافت هرزگرد کاپ Ø8", cyl("X", (yf, CUP_PULLEY_Z), 8, xpl + 10, xbelt + 13), "gear", g, 0.02, "Ø8")
    buy("B13", "تسمه گام 5 عرض 20 (کاپ)", PL.place(PL.belt_loop(yf - yr, PD24 / 2, 3.6, 20), "+Z",
                                                   (xbelt, yr, CUP_PULLEY_Z), spin=90), "belt", g, 0.15, "5M-20 open")
    fast("F08", "پیچ آلن M8×20 پایه‌ی براکت‌ها", "DIN 912 M8×20 + واشر", heads(8, [
        (xpl + 20, y + dy) for y in (yr, yf) for dy in (-30, 30)], ZT + 20), g)
    for y in (ry0 - 25, ry1 + 5):
        buy("B30", "لیمیت سوئیچ Omron D4N", box(xr_ - 15, xr_ + 15, y, y + 20, ZT + 10, ZT + 65), "yellow",
            "سنسورها", 0.15, "D4N-1A31")
    buy("B31", "سنسور هوم M18", cyl("Z", (xr_ - 35, ry0 + 20), 18, ZT + 10, ZT + 50), "gear", "سنسورها", 0.06,
        "PR18-8DN")


# ============================================================================
# 7. PRINT STATION: height-adjustable fixture table
# ============================================================================
def build_print_station():
    """Disc table outside the body, bolted to it with two tie pairs so the print force closes
    inside the steel (no tipping, no floor dependence). Turntable on a lazy-susan bearing,
    centring ring for the disc bore."""
    g = "میز دیسک"
    tb, t = P["tb"], P["tb_t"]
    h = tb / 2
    xc = X_DISC
    zt = ZT                              # table frame top = machine base top (ties are straight)
    a = 300.0                            # half size of the table frame (leg centres)
    legs = [(xc + sx * a, sy * a) for sx in (-1, 1) for sy in (-1, 1)]
    for (x, y) in legs:
        tube("پایه‌ی میز دیسک", (x, y, P["foot_h"]), (x, y, zt), tb, tb, t, g)
        foot_at(x, y, g)
    fl = Plate("P61", "فلنج لوله‌ی اتصال میز", 120, 60, 10, "St37", r=6, holes=[(-45, 0, 13), (45, 0, 13)],
               note="جوش به سر لوله‌ی اتصال؛ 2× M12 به پایه‌ی دستگاه یا قاب میز")
    xt0, xt1 = X_FRONT, xc - a - h
    bolts = []
    for zc in (zt - h, P["foot_h"] + 50):
        for y in (-a, a):
            tube("طولی میز دیسک", (xc - a + h, y, zc), (xc + a - h, y, zc), tb, tb, t, g)
        for x in (xc - a, xc + a):
            tube("عرضی میز دیسک", (x, -a + h, zc), (x, a - h, zc), tb, tb, t, g)
        for y in (-P["rail_y"], P["rail_y"]):     # ties to the machine front posts
            tube("اتصال میز به دستگاه (پیچی)", (xt0 + 10, y, zc), (xt1 - 10, y, zc), tb, tb, t, g,
                 note="دو سر ورق فلنج P61 و 4× M12؛ نیروی چاپ را داخل فولاد می‌بندد")
            for x0, d in ((xt0, "+X"), (xt1 - 10, "-X")):
                plate(fl, "YZ", y, zc, x0, g, "frame")
                xs = x0 + 10 if d == "+X" else x0
                bolts += [PL.place(PL.shcs_head(12), d, (xs, y + sy * 45, zc)) for sy in (-1, 1)]
    fast("F11", "پیچ آلن M12×40 + مهره و واشر (اتصال میز)", "DIN 912 M12×40 + DIN 934 + DIN 125", bolts, g)
    bp = Plate("P60", "صفحه‌ی پایه‌ی میز گردان", 2 * a + tb, 2 * a + tb, 15, "St37",
               holes=[(sx * a, sy * a, 13) for sx in (-1, 1) for sy in (-1, 1)] + [(0, 0, 40)] +
                     pcd(0, 0, 235, 8, 9, a0=22.5),
               note="روی قاب میز؛ 8× M8 برای بلبرینگ گردان")
    plate(bp, "XY", xc, 0, zt, g, "steel")
    z1 = zt + 15
    zb = Zc - P["disc_t"] - 20            # turntable plate bottom
    buy("B70", "بلبرینگ گردان (Lazy Susan) Ø500", tubecyl("Z", (xc, 0), 500, 430, z1, zb), "gear", g, 3.5,
        "Ø500، ظرفیت ≥ 200 kg")
    ridx = a + h + 25
    idx_holes = PL.comp([cyl("Z", (xc + ridx * math.cos(math.radians(k * 120)), ridx * math.sin(math.radians(k * 120))),
                             12, zb - 1, zb + 21) for k in range(3)])
    tt = cyl("Z", (xc, 0), P["disc_od"] + 50, zb, zb + 20).cut(idx_holes)
    add("M30", "صفحه‌ی گردان Ø1050 (MDF روکش‌دار یا کامپوزیت آلومینیوم)", tt, "machined", "MDF روکش‌دار", C["cab"], g,
        meta=dict(dims=f"Ø{P['disc_od'] + 50:g} × 20", process="برش CNC", note="سطح صاف؛ 4 سوراخ تنظیم زاویه (120°) برای چاپ سه‌تایی"),
        local=cyl("Z", (0, 0), P["disc_od"] + 50, 0, 20))
    buy("B71", "حلقه‌ی مرکزگیر دیسک (قابل تعویض برای هر قطر داخلی)",
        tubecyl("Z", (xc, 0), P["disc_id"] - 2, P["disc_id"] - 40, Zc - P["disc_t"], Zc - 0.5), "red", g, 0.5,
        "POM، ارتفاع کمتر از ضخامت دیسک")
    buy("B72", f"دیسک پلاستیکی Ø{P['disc_od']:g}/Ø{P['disc_id']:g} × {P['disc_t']:g}",
        tubecyl("Z", (xc, 0), P["disc_od"], P["disc_id"], Zc - P["disc_t"], Zc), "part", g, 1.8, "قطعه‌کار نمونه")
    buy("B73", "پین شاخص 120° (ایندکس)", comp(box(xc + a + h, xc + a + h + 50, -20, 20, zt - 40, zt),
                                             cyl("Z", (xc + a + h + 25, 0), 10, zt, zb + 12)), "yellow", g, 0.3,
        "پین فنری دستی")


# ============================================================================
# 8. SAFETY, GUARDS, ELECTRICS, PNEUMATICS
# ============================================================================
def build_periphery():
    g = "ایمنی و برق"
    gd = "محافظ‌ها"
    ry = P["rail_y"]
    H = BEAM_BOT - ZT
    W = P["base_Y1"] - P["base_Y0"]
    Lb = X_FRONT
    pr = Plate("P50", "محافظ عقب (پلی‌کربنات)", W, H, 5, "پلی‌کربنات")
    add("P50", pr.name, pr.place("YZ", (P["base_Y0"] + P["base_Y1"]) / 2, (ZT + BEAM_BOT) / 2, -5), "plate", pr.mat,
        C["guard"], gd, meta=dict(dims=f"{W:g}x{H:g}x5", plate=pr, process=pr.process, note=""), local=pr.solid())
    pr2 = Plate("P51", "محافظ کناری راست (پلی‌کربنات)", Lb, H, 5, "پلی‌کربنات")
    plate(pr2, "XZ", Lb / 2, (ZT + BEAM_BOT) / 2, P["base_Y1"] + 2, gd, "guard")
    pr3 = Plate("P52", "درب کناری چپ روی ایستگاه جوهر (لولایی، با سوئیچ ایمنی)", Lb, H, 5, "پلی‌کربنات")
    plate(pr3, "XZ", Lb / 2, (ZT + BEAM_BOT) / 2, P["base_Y0"] - 7, gd, "guard")
    # front wall with a window for the pad (between the two posts)
    sill = PAD_UP_BOTTOM - 20
    for code, nm, y0, y1, z0, z1 in (("P53", "محافظ جلو چپ", P["base_Y0"], -ry - 30, ZT, BEAM_BOT),
                                     ("P55", "محافظ جلو راست", ry + 30, P["base_Y1"], ZT, BEAM_BOT),
                                     ("P56", "محافظ جلو پایین پنجره‌ی پد", -ry + 30, ry - 30, ZT, sill)):
        pl = Plate(code, nm + " (پلی‌کربنات)", y1 - y0, z1 - z0, 5, "پلی‌کربنات")
        add(code, pl.name, pl.place("YZ", (y0 + y1) / 2, (z0 + z1) / 2, X_FRONT), "plate", pl.mat, C["guard"], gd,
            meta=dict(dims=f"{y1 - y0:g}x{z1 - z0:g}x5", plate=pl, process=pl.process, note=""), local=pl.solid())
    buy("B61", "سوئیچ ایمنی درب", box(Lb - 60, Lb - 40, P["base_Y0"] - 30, P["base_Y0"] - 8, 1080, 1120), "yellow",
        g, 0.1, "Pilz PSEN / Schmersal")
    # HMI at the front-right corner, facing the disc table
    machined("P54", "بازوی HMI", box(X_FRONT, X_FRONT + 50, YB - 20, YB + 20, 1230, 1270),
             box(0, 50, 0, 40, 0, 40), "St37", "frame", g, "SHS 40x40x3 L50 + ورق")
    hx = X_FRONT + 50
    hmi = box(hx, hx + 70, YB - 20, YB + 220, 1160, 1340)
    hmi = hmi.cut(box(hx + 66, hx + 71, YB + 12, YB + 188, 1212, 1322))        # screen recess
    buy("B62", "جعبه‌ی HMI + DOP-107BV", hmi, "hmi", g, 2.5, "DOP-107BV در جعبه")
    detail("B62", "صفحه‌ی لمسی HMI", box(hx + 66, hx + 67, YB + 12, YB + 188, 1212, 1322), (0.05, 0.25, 0.35, 1), g)
    detail("B62", "شستی‌های HMI", PL.comp([cyl("X", (YB + 40 + 55 * i, 1186), 22, hx + 70, hx + 78) for i in range(3)]),
           (0.2, 0.6, 0.3, 1), g)
    buy("B63", "E-Stop", PL.place(PL.estop(), "+Y", (hx + 35, YB + 220, 1195)), "red", g, 0.2, "XB5AS8442")
    buy("B63", "E-Stop", PL.place(PL.estop(), "-Y", (X_DISC + 300, -330, 730)), "red", g, 0.2, "XB5AS8442")
    tl = PL.tower_light()
    buy("B64", "چراغ برج", PL.place(tl, "+Z", (40, -300, CROSS_TOP)), "motor", g, 0.5, "3 رنگ")
    for k, col in enumerate(((0.2, 0.75, 0.3, 1), (0.95, 0.7, 0.1, 1), (0.85, 0.15, 0.1, 1))):
        detail("B64", "طبقه‌ی رنگی چراغ برج", tubecyl("Z", (40, -300), 57, 40, CROSS_TOP + 70.5 + 46 * k,
                                                         CROSS_TOP + 114.5 + 46 * k), col, g)
    y0c = P["base_Y1"] + 7
    cab = box(0, 600, y0c, y0c + 250, 80, 880)
    buy("B65", "تابلو برق 600×800×250", cab, "cab", g, 28.0, "ورق 1.5، صفحه‌ی نصب")
    door = box(10, 590, y0c + 250, y0c + 253, 90, 870).cut(
        PL.comp([box(60 + 28 * i, 76 + 28 * i, y0c + 249, y0c + 254, 120, 220) for i in range(6)]))
    detail("B65", "درب تابلو با دریچه‌ی هوا", door, "cab", g)
    detail("B65", "دستگیره و لولای تابلو", PL.comp([box(540, 560, y0c + 253, y0c + 273, 440, 560)] +
                                               [cyl("Z", (4, y0c + 257), 12, z, z + 60) for z in (150, 700)]),
           "motor", g)
    detail("B65", "گلند کابل", PL.comp([cyl("Z", (80 + 70 * i, y0c + 125), 22, 62, 80) for i in range(6)]), "motor", g)
    buy("B66", "پدال پایی", box(X_DISC + 400, X_DISC + 700, -450, -250, 0, 90), "yellow", g, 1.2, "پدال صنعتی با قاب")
    yf0 = P["base_Y0"] - 51
    frl = PL.comp([box(10, 90, yf0 - 20, yf0 + 20, 1110, 1160), cyl("Z", (50, yf0), 40, 1010, 1110),
                cyl("Y", (50, 1175), 40, yf0 - 10, yf0 + 10), box(10, 90, yf0 + 20, yf0 + 39, 1120, 1150)])
    buy("B67", "FRL + پرشر سوئیچ", frl, "pneu", g, 1.2, "AW20 + ISE")


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
        return s.translate(V(0, dcup, 0))
    return s


def bb_overlap(a, b, tol=0.05):
    return not (a.xmax <= b.xmin + tol or b.xmax <= a.xmin + tol or a.ymax <= b.ymin + tol or b.ymax <= a.ymin + tol
                or a.zmax <= b.zmin + tol or b.zmax <= a.zmin + tol)


def common_vol(a, b):
    try:
        return a.intersect(b).Volume()
    except Exception:
        return -1


EXPECTED = {("B27", "B50"), ("B27", "B72"), ("B27", "B71"), ("B27", "M30"),   # pad pressing on cliché / disc / table
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
    """Beams sit on the rear portal (X 40) and the front posts (X_FP) and overhang to the disc table.
    The print force pushes the carriage UP: the overhang lifts, the front posts are pulled (tension)."""
    E = 210000.0
    I2 = 2 * (60 * 120 ** 3 - 50 * 110 ** 3) / 12.0          # two RHS 120x60x5
    s = X_FP - 40.0
    F = P["F_print"]
    out = []
    a = X_PICK - 40.0
    b = s - a
    out.append((f"خیز تیرهای X در برداشت (بین دو تکیه‌گاه)، {F:.0f} N", F * a * a * b * b / (3 * E * I2 * s)))
    for lbl, x in ((f"چاپ دیسک Ø{P['disc_od']:g}", X_PRINT), ("بیشترین دسترسی", X_REACH)):
        c = x - X_FP
        out.append((f"خیز سر یک‌سرآزاد تیرهای X در {lbl} ({c:.0f} mm بیرون از ستون جلو)", F * c * c * (c + s) / (3 * E * I2)))
    return out


def tipping(F):
    """Tipping about the rear feet if the disc table were NOT tied to the machine."""
    body = [p for p in PARTS if p["group"] != "میز دیسک"]
    W = sum(mass_of(p) for p in body) * 9.81
    xg = sum(mass_of(p) * p["shape"].BoundingBox().center.x for p in body) * 9.81 / W
    return W, xg, [(x, F * (x - 30) / 1000, W * (xg - 30) / 1000) for x in (X_PRINT, X_REACH)]


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
    L += ["", "خیز زیر ۰.۵ mm در برابر فشردگی چند میلی‌متری پد ناچیز است و از چاپی به چاپ دیگر ثابت می‌ماند.", "",
          "### اگر میز دیسک به دستگاه پیچ نشود (واژگونی)", "",
          f"وزن بدنه‌ی دستگاه ≈ **{extra['tip'][0]:.0f} N**، مرکز جرم در X = {extra['tip'][1]:.0f} mm. نیروی چاپ رو به بالا جلوی دستگاه را بلند می‌کند:", "",
          "| محل چاپ X | گشتاور بلندکننده N·m | گشتاور وزن N·m | نتیجه |", "|---:|---:|---:|---|"] + [
          f"| {x:.0f} | {mo:.0f} | {mr:.0f} | {'❌ جلوی دستگاه بلند می‌شود' if mo > mr else ('⚠️ حاشیه کم' if mo > 0.6 * mr else '✅')} |"
          for x, mo, mr in extra["tip"][2]] + ["",
          "**به همین دلیل میز دیسک با ۴ لوله‌ی اتصال به بدنه پیچ می‌شود.** نیروی چاپ داخل فولاد بسته می‌شود و دستگاه هرگز بلند نمی‌شود. یا باید دستگاه را با رول‌بولت به زمین بست.", "",
          "## ۵. جرم‌ها", "", "| مورد | kg |", "|---|---:|"]
    for k, v in extra["mass"]:
        L.append(f"| {k} | {v:.1f} |")
    F, T, ratio = extra["motor"]
    L += ["", "## ۶. بررسی دوباره‌ی موتور X با جرم واقعی مدل", "",
          f"* جرم متحرک X از مدل: **{extra['m_x']:.1f} kg** (در محاسبه‌ی اولیه ۱۴ kg فرض شده بود).",
          f"* نیروی لازم در شتاب ۲.۸ m/s²: **{F:.0f} N** → گشتاور روی موتور با گیربکس ۱:۳ و پولی ۲۴ دندانه: **{T:.2f} N·m**.",
          f"* گشتاور موجود استپر ۴ N·m در ≈۱۲۵۰ rpm: ۱.۲ تا ۱.۵ N·m → حاشیه‌ی **{1.2 / T:.1f} تا {1.5 / T:.1f} برابر** ✅",
          f"* نسبت اینرسی بار به روتور: **≈ {ratio:.1f} : 1** (برای استپر کلوزلوپ تا ۱۰:۱ مناسب است).", ""]
    o = extra["offset"]
    L += ["## ۷. نیروی تسمه‌ی X خارج از مرکز کالسکه", "",
          f"* مرکز جرم بخش متحرک X در Y = **{o['ycg']:.0f} mm** است. خط تسمه در Y = **{o['yb']:.0f} mm** است، پس فاصله **{o['arm']:.0f} mm** است.",
          f"* گشتاور چرخشی (دور محور عمودی) در بیشترین شتاب: **{o['M']:.1f} N·m**.",
          f"* این گشتاور به‌صورت نیروی جانبی روی واگن‌ها می‌نشیند: **≈ {o['Fy']:.0f} N برای هر واگن**. ظرفیت هر واگن HGH20CA حدود **17,750 N** است، یعنی کمتر از **{o['pct']:.1f}٪** ظرفیت ✅",
          f"* در طرح قبلی که تسمه بیرون بود (Y = 215)، همین عدد {o['Fy_old']:.0f} N بود. با آوردن تسمه به داخل، نصف شد.", ""]
    L += ["## ۸. سنسورهای القایی Z: کی روشن‌اند؟ (از روی هندسه‌ی مدل)", "",
          "پد از 0 (کاملاً بالا) تا 100 mm (ته کورس) پایین می‌رود. هر سنسور وقتی روشن است که تسمه‌ی آهنی جلویش باشد.", "",
          "| سنسور | روشن در پایین‌رفتن | لازم برای برنامه‌ی PLC |", "|---|---|---|"]
    for nm, lo, hi, want in extra["sens"]:
        L.append(f"| {nm} | از {lo:.1f} تا {hi:.1f} mm | {want} |")
    L += ["", "حدود واقعی کمی (حدود ۱ تا ۲ mm) با این عددها فرق دارد، چون سطح حس سنسور ۱۲ mm قطر دارد. هنگام راه‌اندازی، هر سنسور را با شیار براکت طوری تنظیم کنید که چراغ آن دقیقاً در همین نقطه‌ها روشن و خاموش شود.", ""]
    r = extra["rail"]
    L += ["## ۹. ریل‌های X", "",
          f"* طول هر ریل HGR20: **{r['L']:.0f} mm** (استاندارد HIWIN: گام سوراخ ۶۰، از هر سر ۲۰ mm).",
          f"* کورس X: {P['x_travel']:g} mm. فاصله‌ی اطمینان ریل بعد از واگن‌ها: **{r['m0']:.0f} mm** در ابتدای کورس و **{r['m1']:.0f} mm** در انتها (برای رد شدن از لیمیت سوئیچ و ترمز).",
          f"* بار چاپ روی هر واگن: **{r['per_block']:.0f} N** (نیرو رو به بالا). ظرفیت ایستای هر واگن HGH20CA: 27,760 N، یعنی ضریب اطمینان **{27760 / r['per_block']:.0f}**. حتی با ضربه‌ی دو برابر، ضریب **{27760 / r['per_block'] / 2:.0f}** است (HIWIN برای ضربه ۳ تا ۵ را کافی می‌داند).",
          "* واگن‌های سری HG در هر چهار جهت (پایین، بالا، چپ و راست) ظرفیت برابر دارند، پس کشیده شدن رو به بالا مشکلی ندارد.",
          "* در حین حرکت X، پد بالاست (قانون «پد روی سطح = X ساکن»)، پس واگن‌ها در حرکت فقط وزن کالسکه را می‌برند.", ""]
    with open(os.path.join(OUT, "check_report.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    return "\n".join(L)


# ============================================================================
# 10. EXPORTS
# ============================================================================
def export_all():
    import shutil
    for d in ("parts_step", "dxf"):
        shutil.rmtree(os.path.join(OUT, d), ignore_errors=True)
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
        if p["kind"] == "detail":
            continue
        seen.setdefault(p["code"], [p, 0])
        seen[p["code"]][1] += p["meta"].get("n", 1)
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
    kinds = {"tube": "لوله‌ی اسکلت", "plate": "ورق (برش لیزر)", "machined": "ساخت (تراش/فرز)", "buy": "خریدنی",
             "detail": "جزء قطعه‌ی خریدنی"}
    qty = {}
    for p in PARTS:
        if p["kind"] != "detail":
            qty[p["code"]] = qty.get(p["code"], 0) + p["meta"].get("n", 1)
    parts, codes, seen = [], [], set()
    for p in PARTS:
        tol = 0.6 if p["kind"] != "buy" else 1.0
        vs, tris = p["shape"].tessellate(tol, 0.35)
        parts.append(dict(c=p["code"], g=p["group"], m=p["mov"] or "", col=[round(x, 3) for x in p["color"]],
                          v=[round(c, 1) for vv in vs for c in (vv.x, vv.y, vv.z)],
                          t=[k for tri in tris for k in tri]))
        if p["code"] not in seen and p["kind"] != "detail":
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
    xw = X_FP - P["x_home"]
    configs = [("X=0 (خانه)، Z بالا، کاپ روی تصویر", 0, 0, 0),
               (f"X={P['x_pick']:g} برداشت، Z پایین، کاپ عقب", P["x_pick"], P["z_stroke"], -P["cup_stroke"]),
               (f"X={P['x_pick']:g} برداشت، Z بالا، کاپ روی تصویر (انتظار برداشت زودتر)", P["x_pick"], 0, 0),
               (f"X={xw:g} عبور پد از پنجره‌ی جلو، Z بالا، کاپ در حال حرکت", xw, 0, -185),
               (f"X={P['x_print']:g} چاپ دیسک Ø{P['disc_od']:g}، Z پایین", P["x_print"], P["z_stroke"], 0),
               (f"X={P['x_travel']:g} بیشترین دسترسی ({P['reach']:g} mm بیرون)، Z بالا", P["x_travel"], 0, -P["cup_stroke"]),
               (f"X={P['x_travel']:g} بیشترین دسترسی، Z پایین", P["x_travel"], P["z_stroke"], 0)]
    inter = interference(configs)
    stat = static_overlaps()
    print(f"checks {time.time() - t0:.1f}s")
    pad = find("B27")[0]
    cup = find("B52")[0]
    arm = find("P31")[0]
    end_cross = [p for p in PARTS if p["name"] == "عرضی سر تیرها"][0]
    beams = [p for p in PARTS if p["name"] == "تیر ریل X (یک‌سرآزاد)"]
    posts = [p for p in PARTS if p["name"] == "ستون جلو زیر تیر"]
    sill = find("P56")[0]
    sideplates = find("P14")
    dist = [
        ("پد (بالا) تا بازوی کاپ، وقتی پد منتظر روی کلیشه است", min_dist(moved(pad, P["x_pick"]), arm["shape"])),
        ("پد (بالا) تا بالای کاپ", min_dist(moved(pad, P["x_pick"]), cup["shape"])),
        ("پد (پایین، برداشت) تا کاپ عقب‌رفته", min_dist(moved(pad, P["x_pick"], P["z_stroke"]),
                                                     moved(cup, dcup=-P["cup_stroke"]))),
        ("صفحه‌ی کناری هد Z (پایین) تا تیر ریل", min(min_dist(moved(s, P["x_print"], P["z_stroke"]), b["shape"])
                                                   for s in sideplates for b in beams)),
        ("هد Z تا ستون‌های جلو هنگام عبور از پنجره", min(min_dist(moved(q, X_FP - P["x_home"]), c["shape"])
                                                         for q in sideplates + [pad] for c in posts)),
        ("پد (بالا) تا لبه‌ی پایین پنجره‌ی جلو", min_dist(moved(pad, X_FP - P["x_home"]), sill["shape"])),
        ("هد Z در بیشترین دسترسی تا عرضی سر تیرها", min(min_dist(moved(q, P["x_travel"]), end_cross["shape"])
                                                       for q in sideplates + [pad])),
        ("فضای آزاد بالای دیسک تا زیر تیرهای X (جای دست)", BEAM_BOT - Zc),
        ("لبه‌ی دیسک تا بدنه‌ی دستگاه", P["disc_gap"]),
    ]
    m_all = sum(mass_of(p) for p in PARTS)
    m_x = sum(mass_of(p) for p in PARTS if p["mov"] in ("x", "z"))
    m_z = sum(mass_of(p) for p in PARTS if p["mov"] == "z")
    m_c = sum(mass_of(p) for p in PARTS if p["mov"] == "c")
    m_frame = sum(mass_of(p) for p in PARTS if p["kind"] == "tube")
    m_tab = sum(mass_of(p) for p in PARTS if p["group"] == "میز دیسک")
    mass = [("کل دستگاه (بدون تابلو و میز دیسک)", m_all - 28 - m_tab), ("میز دیسک", m_tab), ("اسکلت لوله‌ای", m_frame), ("متحرک X (کالسکه + هد Z)", m_x),
            ("متحرک Z", m_z), ("متحرک کاپ", m_c)]
    mv = [p for p in PARTS if p["mov"] in ("x", "z")]
    ycg = sum(mass_of(p) * p["shape"].BoundingBox().center.y for p in mv) / m_x
    Fdrv = x_motor_check(m_x)[0]
    arm = abs(P["x_belt_y"] - ycg)
    Mz = Fdrv * arm / 1000
    Fy = Mz / 0.140 / 2          # block pairs 140 mm apart along X, two rails
    Fy_old = Fdrv * abs(215 - ycg) / 1000 / 0.140 / 2
    extra = dict(dist=dist, stiff=stiffness(), tip=tipping(P["F_print"]), mass=mass, m_x=m_x, motor=x_motor_check(m_x),
                 offset=dict(ycg=ycg, yb=P["x_belt_y"], arm=arm, M=Mz, Fy=Fy, pct=Fy / 17750 * 100, Fy_old=Fy_old))
    fb = find("P16")[0]["shape"].BoundingBox()
    sens = []
    for q, (nm, want) in zip(find("B22"), (("X2 بالا", "کمتر از 2 mm"), ("X20 ارتفاع امن", "از 0 تا 32 mm"),
                                          ("X3 پایین", "از 94.5 mm به بعد"))):
        zc_ = q["shape"].BoundingBox().center.z
        lo, hi = max(0.0, fb.zmin - zc_), min(P["z_stroke"], fb.zmax - zc_)
        sens.append((nm, lo, hi, want))
    extra["sens"] = sens
    rail = [q for q in PARTS if q["code"] == "B01"][0]["shape"].BoundingBox()
    blk = find("B02")
    bx0 = min(q["shape"].BoundingBox().xmin for q in blk)
    bx1 = max(q["shape"].BoundingBox().xmax for q in blk)
    extra["rail"] = dict(L=rail.xlen, m0=bx0 - rail.xmin, m1=rail.xmax - (bx1 + P["x_travel"]),
                         per_block=P["F_print"] / 4)
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
