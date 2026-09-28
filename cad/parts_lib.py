"""
Detailed geometry for purchased parts and fasteners (used by tampo_machine.py).

Every builder returns a cq.Shape in LOCAL coordinates; `place()` turns it into
world coordinates. Dimensions follow the catalogue values where they matter for
fit (mounting faces, bores, hole patterns); cosmetic details are simplified.
"""
import math
import cadquery as cq

V = cq.Vector
O = V(0, 0, 0)


def place(shape, d="+Z", at=(0, 0, 0), spin=0.0):
    """Local +Z is turned to direction d ('+X','-X','+Y','-Y','+Z','-Z'), after an optional
    spin (deg) about local Z; then the local origin is moved to `at`."""
    s = shape.rotate(O, V(0, 0, 1), spin) if spin else shape
    if d == "-Z":
        s = s.rotate(O, V(1, 0, 0), 180)
    elif d == "+X":
        s = s.rotate(O, V(0, 1, 0), 90)
    elif d == "-X":
        s = s.rotate(O, V(0, 1, 0), -90)
    elif d == "+Y":
        s = s.rotate(O, V(1, 0, 0), -90)
    elif d == "-Y":
        s = s.rotate(O, V(1, 0, 0), 90)
    return s.translate(V(*at))


def comp(shapes):
    return cq.Compound.makeCompound(list(shapes))


def cylz(d, z0, z1, x=0.0, y=0.0):
    return cq.Solid.makeCylinder(d / 2, z1 - z0, V(x, y, z0))


def boxc(w, h, z0, z1, x=0.0, y=0.0):
    return cq.Solid.makeBox(w, h, z1 - z0, V(x - w / 2, y - h / 2, z0))


def hexz(af, z0, z1, x=0.0, y=0.0):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).polygon(6, af / math.cos(math.pi / 6)) \
        .extrude(z1 - z0).val()


# --------------------------------------------------------------------------- fasteners
SHCS = {  # socket head cap screw: head Ø, head h, socket AF
    4: (7, 4, 3), 5: (8.5, 5, 4), 6: (10, 6, 5), 8: (13, 8, 6), 10: (16, 10, 8), 12: (18, 12, 10), 16: (24, 16, 14)}
NUT = {6: (10, 5), 8: (13, 6.5), 10: (16, 8), 12: (18, 10), 16: (24, 13)}


def shcs_head(m):
    dh, hh, af = SHCS[m]
    return cylz(dh, 0, hh).cut(hexz(af, hh - 0.6 * af, hh + 1))


def washer(m, t=None):
    dh = {4: 9, 5: 10, 6: 12, 8: 16, 10: 20, 12: 24, 16: 30}[m]
    t = t or {4: 0.8, 5: 1, 6: 1.6, 8: 1.6, 10: 2, 12: 2.5, 16: 3}[m]
    return cylz(dh, 0, t).cut(cylz(m + 0.5, -1, t + 1))


def nut(m):
    af, h = NUT[m]
    return hexz(af, 0, h).cut(cylz(m, -1, h + 1))


# --------------------------------------------------------------------------- linear guides
RAIL = {  # W, H, pitch, E, counterbore D, depth, hole d
    20: (20, 17.5, 60, 20, 9.5, 8.5, 6), 15: (15, 15, 60, 20, 7.5, 5.3, 4.5)}
BLOCK = {  # W, H(from rail bottom), H1(gap under block), L, L1(steel body), B, C, M
    20: (44, 30, 4.6, 77.5, 50.5, 32, 36, 5), 15: (34, 28, 4.3, 61.4, 39.4, 26, 26, 4)}


def rail(size, L):
    """HIWIN HGR rail, local: along +X from 0..L, centred on y=0, bottom at z=0; M screws in counterbores."""
    W, H, P, E, cbD, cbH, hd = RAIL[size]
    w = W / 2
    g = 1.5 if size == 20 else 1.2
    zg = H * 0.68
    prof = [(-w, 0), (w, 0), (w, zg - 2 * g), (w - g, zg - g), (w, zg), (w, H - 0.8), (w - 0.8, H),
            (-w + 0.8, H), (-w, H - 0.8), (-w, zg), (-w + g, zg - g), (-w, zg - 2 * g)]
    s = cq.Workplane("YZ").polyline(prof).close().extrude(L).val()
    n = int((L - 2 * E) // P) + 1
    cut = []
    heads = []
    for i in range(n):
        x = E + i * P
        cut += [cylz(cbD, H - cbH, H + 1, x, 0), cylz(hd, -1, H, x, 0)]
        heads.append(shcs_head(hd - 1 if size == 20 else 4).translate(V(x, 0, H - cbH)))
    return s.cut(*cut), comp(heads), n


def block(size):
    """HIWIN HG block, local: travel along X, centred at origin, rail bottom at z=0 (block rides above)."""
    W, H, H1, L, L1, B, C, M = BLOCK[size]
    rw, rh = RAIL[size][0], RAIL[size][1]
    body = boxc(L1, W, H1, H).cut(boxc(L1 + 2, rw + 1.2, H1 - 1, rh + 0.5))
    body = body.cut(*[cylz(M * 0.85, H - 8, H + 1, sx * C / 2, sy * B / 2) for sx in (-1, 1) for sy in (-1, 1)])
    ends = []
    le = (L - L1) / 2
    for sx in (-1, 1):
        x0 = sx * (L1 / 2 + le / 2)
        e = boxc(le, W - 2, H1 + 0.5, H - 1.5, x0, 0).cut(boxc(le + 2, rw + 1.4, H1 - 1, rh + 0.8, x0, 0))
        ends.append(e)
    nip = cylz(6, 0, 8).rotate(O, V(0, 1, 0), 90).translate(V(L / 2, 0, H - 5))
    return body, comp(ends + [nip])


# --------------------------------------------------------------------------- motors, gearbox
def nema24(L=110.0, boss=True, shaft=True, shaft_d=8.0, shaft_l=24.0):
    """NEMA24 closed-loop stepper, local: flange face at z=0, body towards +z, shaft towards -z."""
    a = 60.0
    c = 6.0
    sec = [(-a / 2 + c, -a / 2), (a / 2 - c, -a / 2), (a / 2, -a / 2 + c), (a / 2, a / 2 - c), (a / 2 - c, a / 2),
           (-a / 2 + c, a / 2), (-a / 2, a / 2 - c), (-a / 2, -a / 2 + c)]
    body = cq.Workplane("XY").polyline(sec).close().extrude(L - 30).val()
    fl = boxc(a, a, 0, 7).cut(*[cylz(5.2, -1, 8, sx * 23.57, sy * 23.57) for sx in (-1, 1) for sy in (-1, 1)])
    enc = cylz(52, L - 30, L) .fuse(boxc(20, 14, L - 22, L - 8, 0, -30))
    parts = [body.fuse(fl), enc]
    if boss:
        parts.append(cylz(38.1, -1.6, 0))
    if shaft:
        parts.append(cylz(shaft_d, -shaft_l, -1.6 if boss else 0))
    return comp(parts)


def planetary60(L=70.0):
    """PLF60-type gearbox, local: output flange face at z=0, body towards +z (motor side)."""
    fl = boxc(60, 60, 0, 10).cut(*[cylz(5.5, -1, 11, 35 * math.cos(math.radians(45 + 90 * i)),
                                          35 * math.sin(math.radians(45 + 90 * i))) for i in range(4)])
    return comp([fl, cylz(58, 10, L - 12), boxc(60, 60, L - 12, L), cylz(50, -3, 0)])


# --------------------------------------------------------------------------- belt drive
def pulley(teeth=24, pitch=5.0, width=28.0, bore=14.0, flange_d=46.0, flange_t=2.0, hub_l=10.0, hub_d=26.0):
    """HTD 5M pulley, local: axis z, belt-centre plane at z=0; hub on the -z side."""
    pd = teeth * pitch / math.pi
    od = pd - 1.14
    r = od / 2
    w = width / 2
    core = cylz(od, -w, w)
    grooves = [cylz(2.6, -w - 1, w + 1, (r + 0.35) * math.cos(2 * math.pi * i / teeth),
                    (r + 0.35) * math.sin(2 * math.pi * i / teeth)) for i in range(teeth)]
    core = core.cut(*grooves)
    fl = [cylz(flange_d, -w - flange_t, -w), cylz(flange_d, w, w + flange_t)]
    hub = cylz(hub_d, -w - flange_t - hub_l, -w - flange_t)
    s = comp([core] + fl + [hub])
    return s.cut(cylz(bore, -w - flange_t - hub_l - 1, w + flange_t + 1)), pd


def belt_loop(c2c, r, t=3.6, width=25.0):
    """Open-end belt clamped into a loop, local: stadium in the XZ plane (first pulley centre at origin,
    second at +x = c2c), width along y centred on 0. r = pitch radius (inside face)."""
    outer = cq.Workplane("XY").center(c2c / 2, 0).slot2D(c2c + 2 * (r + t), 2 * (r + t)).extrude(width).val()
    inner = cq.Workplane("XY").center(c2c / 2, 0).slot2D(c2c + 2 * r, 2 * r).extrude(width + 2) \
        .val().translate(V(0, 0, -1))
    band = outer.cut(inner).translate(V(0, 0, -width / 2))
    return band.rotate(O, V(1, 0, 0), 90)          # local y (stadium) -> z, extrusion -> -y (symmetric)


def drag_chain(path, w=50.0, h=25.0, pitch=25.0):
    """Cable chain as individual links along straight segments; path = [(p0, p1), ...] world points."""
    links = []
    for (a, b) in path:
        a, b = V(*a), V(*b)
        d = b - a
        L = d.Length
        n = max(1, int(L // pitch))
        u = d.normalized()
        for i in range(n):
            c = a + u * (pitch * (i + 0.5))
            if abs(u.x) > 0.5:
                sz = (pitch - 2, w, h)
            elif abs(u.y) > 0.5:
                sz = (w, pitch - 2, h)
            else:
                sz = (w, h, pitch - 2)
            links.append(cq.Solid.makeBox(*sz, V(c.x - sz[0] / 2, c.y - sz[1] / 2, c.z - sz[2] / 2)))
    return comp(links)


# --------------------------------------------------------------------------- pneumatics
def sc63(stroke=100.0):
    """Airtac SC63 tie-rod cylinder, local: front (rod-end) cover face at z=0, body towards +z."""
    L = 140.0 + stroke
    cov = 30.0
    parts = []
    for z0 in (0.0, L - cov):
        c = boxc(75, 75, z0, z0 + cov)
        parts.append(cq.Workplane().add(c).edges("|Z").chamfer(4).val())
    parts.append(cylz(70, cov, L - cov))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(cylz(10, 0, L + 9, sx * 28.25, sy * 28.25))
            parts.append(nut(10).translate(V(sx * 28.25, sy * 28.25, L)))
    for z in (15.0, L - 15.0):                      # cushion screws (-X face)
        parts.append(cylz(8, 0, 4).rotate(O, V(0, 1, 0), -90).translate(V(-37.5, 0, z)))
    return comp(parts), L


def valve_4v320():
    """5/2 double-solenoid valve, local: base on z=0, long side along x (centred)."""
    body = boxc(110, 35, 0, 40)
    coils = [boxc(32, 30, 5, 38, sx * 70, 0) for sx in (-1, 1)]
    plugs = [boxc(20, 28, 38, 55, sx * 72, 0) for sx in (-1, 1)]
    fit = [cylz(14, 40, 52, x, 0) for x in (-25, 0, 25)]
    return comp([body] + coils + plugs + fit)


# --------------------------------------------------------------------------- misc buyouts
def levelling_foot(h, pad_d=80.0):
    """Levelling foot, local: floor at z=0, top of stud at z=h (tube foot plate underside)."""
    return comp([cylz(pad_d, 0, 4), cylz(pad_d - 6, 4, 14), cylz(16, 14, h), nut(16).translate(V(0, 0, h - 13))])


def lmf(d, D, D1, L, t, pcd, hole, holes=4):
    """Flanged linear bushing LMF, local: flange at z=0..t, body up to z=L."""
    fl = cylz(D1, 0, t).cut(*[cylz(hole, -1, t + 1, pcd / 2 * math.cos(math.radians(45 + 90 * i)),
                                     pcd / 2 * math.sin(math.radians(45 + 90 * i))) for i in range(holes)])
    return comp([fl, cylz(D, t, L)]).cut(cylz(d, -1, L + 1))


def estop():
    """E-stop station, local: back on z=0, button towards +z."""
    return comp([cq.Workplane().add(boxc(70, 70, 0, 60)).edges("|Z").fillet(6).val(), cylz(28, 60, 66), cylz(40, 66, 76), cylz(34, 76, 80)])


def tower_light():
    """Base, stem and cap only; the three coloured lenses are separate (z 70.5-114.5, 116.5-160.5, 162.5-206.5)."""
    return comp([cylz(30, 0, 60), cylz(60, 60, 70), cylz(40, 70, 208), cylz(60, 208, 216)])
