# Screw-assembled teaching model of an armature + leaf-spring brake (v2, 3D-print data).
# Not a real brake: no coil wire, no magnet, no electricity. A finger press replaces the
# magnetic pull. Units mm. Assembly frame: Z up, axis = Z, base bottom at z = 0.
# Hardware is modelled as simplified solids (no helical thread) for fit checks only.
# Run: freecadcmd build_v2_cad.py
import FreeCAD as App, Part, Mesh, MeshPart, math, os, json, hashlib, itertools

V = App.Vector
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_CAD, OUT_PRINT, OUT_RENDER, OUT_RES = (os.path.join(ROOT, d) for d in ("cad", "stl/print", "stl/render", "results"))
for d in (OUT_CAD, OUT_PRINT, OUT_RENDER, OUT_RES):
    os.makedirs(d, exist_ok=True)

P = dict(
    # base / field (same magnetic-path look as v1)
    plate_r=60.0, plate_t=3.0, plate_chamfer=0.5, floor_z=6.0, pole_z=16.0,
    inner_ri=31.0, inner_ro=35.0, outer_ri=44.0, outer_ro=50.5,
    shoulder_r=7.0, cone_r=10.0, axle_r=4.0, axle_top=33.8, axle_chamfer=0.5,
    coil_ri=35.5, coil_ro=43.5, coil_h=9.4, gap=1.5,
    # rotor
    bore_r=4.35, hub_r=9.0, hub_h=6.0, knob_r=7.0, knob_h=10.0, knob_grooves=12, knob_groove_r=0.8, knob_groove_c=7.2,
    seat_t=5.5,                      # hub pads and armature: same thickness, so the springs lie flat
    arm_ri=30.0, arm_ro=50.0,
    pad_u0=7.3, pad_u1=16.7, pad_s0=-1.5, pad_s1=10.1,
    # leaf spring (separate print, 3 used + 1 spare)
    spr_a=12.0, spr_w=7.0, spr_t=0.8, spr_s_hub=5.5, spr_r_arm=39.5,
    # fastener interface
    hole_r=1.7, pocket_af=5.9, pocket_depth=3.2, bridge_layer=0.2,
    slot_w=5.9, slot_z0=12.0, slot_h=2.6, blind_z=9.5,
    cap_r=6.5, cap_t=2.0, cap_chamfer=0.4,
    window_hw=5.0, window_z0=6.5, window_z1=9.0, window_alpha_deg=40.0, window_angles=(60.0, 180.0, 300.0),
    mark_w=1.2, mark_d=0.6, strap_angles=(0.0, 120.0, 240.0),
)
p = P
Z0 = p["pole_z"] + p["gap"]                 # 17.5 rotor bottom (OFF)
ZT = Z0 + p["seat_t"]                         # 23.0 seat top (pads and armature)
A = p["spr_a"]
S_H = p["spr_s_hub"]
S_A = math.sqrt(p["spr_r_arm"] ** 2 - A ** 2)  # 37.632: armature screw on r = 39.5 (over the coil groove)
# ISO hardware (nominal; tolerances used in the checks)
SHCS = dict(dk=5.5, k=3.0, s=2.5, t=1.6, d=3.0, pitch=0.5)            # ISO 4762 M3
NUT = dict(s=5.5, e_min=6.01, m=2.4, d=3.0)                            # ISO 4032 M3
WASHER = dict(d1=3.2, d2=7.0, h=0.5)                                   # ISO 7089 M3
L_SPRING_SCREW, L_AXLE_SCREW = 6.0, 25.0
TOL = {6.0: 0.24, 25.0: 0.42}                                          # ISO 4762 length tolerance js15
S_ROOT = p["pad_s1"]                                                   # free span starts at the hub pad edge
S_TIP = S_A - WASHER["d2"] / 2                                         # and ends at the armature washer edge
L_FREE = S_TIP - S_ROOT
SECTION_A0 = math.degrees(math.atan2(S_H, A))                           # cut plane through hub screw of spring 0
SECTION_A1 = 120.0 + math.degrees(math.atan2(S_A, A))                   # and through armature screw of spring 1
SLOT_ANG = SECTION_A1                                                   # nut slot lies in the second cut plane


def rev(rz):
    pts = [V(r, 0, z) for r, z in rz] + [V(rz[0][0], 0, rz[0][1])]
    s = Part.Face(Part.makePolygon(pts)).revolve(V(0, 0, 0), V(0, 0, 1), 360)
    return Part.Solid(Part.Shell(s.Faces)) if s.ShapeType != "Solid" else s


def prism(pts2d, z0, z1):
    pts = [V(x, y, z0) for x, y in pts2d] + [V(pts2d[0][0], pts2d[0][1], z0)]
    return Part.Face(Part.makePolygon(pts)).extrude(V(0, 0, z1 - z0))


def box2(u0, u1, s0, s1, z0, z1):
    return Part.makeBox(u1 - u0, s1 - s0, z1 - z0, V(u0, s0, z0))


def hexagon(cx, cy, af, corner_ang=0.0):
    R = af / math.sqrt(3.0)
    return [(cx + R * math.cos(math.radians(corner_ang + 60 * i)), cy + R * math.sin(math.radians(corner_ang + 60 * i))) for i in range(6)]


def rotz(shape, ang):
    s = shape.copy(); s.rotate(V(0, 0, 0), V(0, 0, 1), ang); return s


def moved(shape, dz=0.0, dx=0.0, dy=0.0):
    s = shape.copy(); s.translate(V(dx, dy, dz)); return s


def local_to_global(u, s, ang):
    t = math.radians(ang)
    return (u * math.cos(t) - s * math.sin(t), u * math.sin(t) + s * math.cos(t))


def solid_one(shape, name):
    s = shape.removeSplitter()
    if len(s.Solids) != 1:
        raise RuntimeError("%s has %d solids" % (name, len(s.Solids)))
    return s.Solids[0]


def pocket_cutters(cu, cs, z_open, depth, af, bl, hole_top):
    """Hex nut pocket open at z_open (print bed side) + 2 sacrificial bridge layers + clearance hole.
    Local frame: u = corner direction, s = across flats. Returns (cutter, bridge ceiling heights)."""
    zc = z_open + depth
    hx = prism(hexagon(cu, cs, af, 0.0), z_open - 1.0, zc)
    hr = p["hole_r"]
    l1 = box2(cu - hr, cu + hr, cs - af / 2, cs + af / 2, zc - 0.01, zc + bl)          # strands span flat to flat
    l2 = box2(cu - hr, cu + hr, cs - hr, cs + hr, zc + bl - 0.01, zc + 2 * bl)        # strands span layer-1 gap
    hole = Part.makeCylinder(hr, hole_top - zc + 1.0, V(cu, cs, zc))
    return hx.fuse([l1, l2, hole]).removeSplitter(), (zc, zc + bl, zc + 2 * bl)


# ---------------- base / field / shoulder / axle (grey) -----------------------------------
base_profile = [
    (0.0, 0.0), (p["plate_r"] - 0.3, 0.0), (p["plate_r"], p["plate_chamfer"]),
    (p["plate_r"], p["plate_t"]), (p["outer_ro"], p["plate_t"]), (p["outer_ro"], p["pole_z"]),
    (p["outer_ri"], p["pole_z"]), (p["outer_ri"], p["floor_z"]), (p["inner_ro"], p["floor_z"]),
    (p["inner_ro"], p["pole_z"]), (p["inner_ri"], p["pole_z"]), (p["inner_ri"], p["plate_t"]),
    (p["cone_r"], p["plate_t"]), (p["shoulder_r"], p["plate_t"] + (p["cone_r"] - p["shoulder_r"])),
    (p["shoulder_r"], Z0), (p["axle_r"], Z0),
    (p["axle_r"], p["axle_top"] - p["axle_chamfer"]), (p["axle_r"] - p["axle_chamfer"], p["axle_top"]),
    (0.0, p["axle_top"]),
]
base_env = rev(base_profile)
hw = p["window_hw"]
apex = p["window_z1"] + hw / math.tan(math.radians(p["window_alpha_deg"]))
win_tz = [(-hw, p["window_z0"]), (hw, p["window_z0"]), (hw, p["window_z1"]), (0.0, apex), (-hw, p["window_z1"])]
for ang in p["window_angles"]:
    pts = [V(40.0, t_, z_) for t_, z_ in win_tz] + [V(40.0, win_tz[0][0], win_tz[0][1])]
    w_ = Part.Face(Part.makePolygon(pts)).extrude(V(16.0, 0, 0))
    base_env = base_env.cut(rotz(w_, ang))
pointer = prism([(52.0, 0.0), (58.0, -3.0), (58.0, 3.0)], p["plate_t"], p["plate_t"] + 0.8)
base_env = solid_one(base_env.fuse(pointer), "base envelope")
# Side-entry nut slot in the centre post (reachable from above before the rotor goes on).
sw, sz0, sz1 = p["slot_w"], p["slot_z0"], p["slot_z0"] + p["slot_h"]
R_slot = sw / math.sqrt(3.0)
slot_pts = [(9.5, -sw / 2), (9.5, sw / 2), (-R_slot / 2, sw / 2), (-R_slot, 0.0), (-R_slot / 2, -sw / 2)]
hr = p["hole_r"]; bl = p["bridge_layer"]
slot_cut = prism(slot_pts, sz0, sz1).fuse([
    box2(-hr, hr, -sw / 2, sw / 2, sz1 - 0.01, sz1 + bl),
    box2(-hr, hr, -hr, hr, sz1 + bl - 0.01, sz1 + 2 * bl),
    Part.makeCylinder(hr, p["axle_top"] + 1.0 - p["blind_z"], V(0, 0, p["blind_z"]))]).removeSplitter()
slot_cut = rotz(slot_cut, SLOT_ANG)
base = solid_one(base_env.cut(slot_cut), "base")
BASE_BRIDGES = (sz1, sz1 + bl, sz1 + 2 * bl)

# ---------------- coil ring (orange, unchanged from v1) --------------------------------
cp = [(p["coil_ri"], 0.0), (p["coil_ro"], 0.0)]
for zc in (1.7, 3.2, 4.7, 6.2, 7.7):
    cp += [(p["coil_ro"], zc - 0.4), (p["coil_ro"] - 0.3, zc), (p["coil_ro"], zc + 0.4)]
cp += [(p["coil_ro"], p["coil_h"])]
for r0, r1 in ((41.2, 41.8), (39.2, 39.8), (37.2, 37.8)):
    cp += [(r1, p["coil_h"]), (r1, p["coil_h"] - 0.4), (r0, p["coil_h"] - 0.4), (r0, p["coil_h"])]
cp += [(p["coil_ri"], p["coil_h"])]
coil_print = solid_one(rev(cp), "coil")
coil = moved(coil_print, p["floor_z"])

# ---------------- hub (violet) with 3 screw pads ---------------------------------------
hub_profile = [(p["bore_r"], Z0), (p["hub_r"], Z0), (p["hub_r"], Z0 + p["hub_h"]), (p["knob_r"], Z0 + p["hub_h"]),
               (p["knob_r"], Z0 + p["hub_h"] + p["knob_h"] - 0.6), (p["knob_r"] - 0.6, Z0 + p["hub_h"] + p["knob_h"]),
               (p["bore_r"], Z0 + p["hub_h"] + p["knob_h"])]
HUB_TOP = Z0 + p["hub_h"] + p["knob_h"]
hub_env = rev(hub_profile)
for i in range(p["knob_grooves"]):
    a_ = 2 * math.pi * i / p["knob_grooves"]
    hub_env = hub_env.cut(Part.makeCylinder(p["knob_groove_r"], p["knob_h"], V(p["knob_groove_c"] * math.cos(a_), p["knob_groove_c"] * math.sin(a_), Z0 + p["hub_h"] + 0.5)))
pads = [rotz(box2(p["pad_u0"], p["pad_u1"], p["pad_s0"], p["pad_s1"], Z0, ZT), ang) for ang in p["strap_angles"]]
hub_env = solid_one(hub_env.fuse(pads), "hub envelope")
hub_cut, arm_cut = [], []
for ang in p["strap_angles"]:
    c, HUB_BRIDGES = pocket_cutters(A, S_H, Z0, p["pocket_depth"], p["pocket_af"], bl, ZT)
    hub_cut.append(rotz(c, ang))
    c, ARM_BRIDGES = pocket_cutters(A, S_A, Z0, p["pocket_depth"], p["pocket_af"], bl, ZT)
    arm_cut.append(rotz(c, ang))
hub = solid_one(hub_env.cut(hub_cut), "hub")

# ---------------- armature disc (blue) ------------------------------------------------
arm_env = rev([(p["arm_ri"], Z0), (p["arm_ro"], Z0), (p["arm_ro"], ZT), (p["arm_ri"], ZT)])
mark = Part.makeBox(11.0, p["mark_w"], p["mark_d"] + 1, V(40.0, -p["mark_w"] / 2, ZT - p["mark_d"]))
arm_env = solid_one(arm_env.cut(mark), "armature envelope")
armature = solid_one(arm_env.cut(arm_cut), "armature")


# ---------------- leaf springs (green, separate flat prints) ----------------------------
def spring_local(z0):
    w2 = p["spr_w"] / 2
    body = box2(A - w2, A + w2, S_H, S_A, z0, z0 + p["spr_t"])
    ends = [Part.makeCylinder(w2, p["spr_t"], V(A, s_, z0)) for s_ in (S_H, S_A)]
    holes = [Part.makeCylinder(hr, p["spr_t"] + 2, V(A, s_, z0 - 1)) for s_ in (S_H, S_A)]
    return solid_one(body.fuse(ends).cut(holes), "spring")


def spring_pressed_local(z0, delta, n_sec=24):
    w2 = p["spr_w"] / 2
    off = spring_local(z0)
    cut_hub = box2(-50, 50, -50, S_ROOT, z0 - 5, z0 + 5)
    cut_arm = box2(-50, 50, S_TIP, 100, z0 - 5, z0 + 5)
    hub_piece = off.common(cut_hub)
    arm_piece = moved(off.common(cut_arm), -delta)
    wires = []
    for i in range(n_sec + 1):
        xi = i / n_sec
        s_ = S_ROOT + L_FREE * xi
        dz = -delta * (3 * xi ** 2 - 2 * xi ** 3)
        pts = [V(A - w2, s_, z0 + dz), V(A + w2, s_, z0 + dz), V(A + w2, s_, z0 + dz + p["spr_t"]), V(A - w2, s_, z0 + dz + p["spr_t"])]
        wires.append(Part.makePolygon(pts + [pts[0]]))
    span = Part.makeLoft(wires, True, False)
    return solid_one(hub_piece.fuse([span, arm_piece]), "pressed spring"), span


springs = [rotz(spring_local(ZT), ang) for ang in p["strap_angles"]]
delta = p["gap"]
_sp = [spring_pressed_local(ZT, delta) for _ in p["strap_angles"]]
springs_p = [rotz(s_[0], ang) for s_, ang in zip(_sp, p["strap_angles"])]
spans_p = [rotz(s_[1], ang) for s_, ang in zip(_sp, p["strap_angles"])]
spans_off = [rotz(box2(A - p["spr_w"] / 2, A + p["spr_w"] / 2, S_ROOT, S_TIP, ZT, ZT + p["spr_t"]), ang) for ang in p["strap_angles"]]

# ---------------- retaining cap (grey) -----------------------------------------------------
CAP_Z0 = p["axle_top"]
cap = rev([(hr, CAP_Z0), (p["cap_r"], CAP_Z0), (p["cap_r"], CAP_Z0 + p["cap_t"] - p["cap_chamfer"]),
           (p["cap_r"] - p["cap_chamfer"], CAP_Z0 + p["cap_t"]), (hr, CAP_Z0 + p["cap_t"])])
cap = solid_one(cap, "cap")


# ---------------- hardware (simplified, no helical thread) ----------------------------------
def make_shcs(L, x, y, zb):
    k, dk, d = SHCS["k"], SHCS["dk"], SHCS["d"]
    prof = [(0.0, zb - L), (d / 2 - 0.3, zb - L), (d / 2, zb - L + 0.3), (d / 2, zb), (dk / 2, zb),
            (dk / 2, zb + k - 0.3), (dk / 2 - 0.3, zb + k), (0.0, zb + k)]
    s_ = rev(prof)
    sock = prism(hexagon(0, 0, SHCS["s"], 0.0), zb + k - SHCS["t"], zb + k + 1.0)
    s_ = solid_one(s_.cut(sock), "screw")
    s_.translate(V(x, y, 0)); return s_


def make_nut(x, y, z0, corner_ang):
    m, af = NUT["m"], NUT["s"]
    hx = prism(hexagon(0, 0, af, 0.0), z0, z0 + m)
    rc = af / math.sqrt(3.0); r_dw = af / 2   # 30 deg chamfer starts at the inscribed circle
    ch = (rc - r_dw) * math.tan(math.radians(30))
    rv = rev([(0.0, z0), (r_dw, z0), (rc + 0.01, z0 + ch), (rc + 0.01, z0 + m - ch), (r_dw, z0 + m), (0.0, z0 + m)])
    n_ = hx.common(rv).cut(Part.makeCylinder(NUT["d"] / 2, m + 2, V(0, 0, z0 - 1)))
    n_ = solid_one(n_, "nut")
    n_.rotate(V(0, 0, 0), V(0, 0, 1), corner_ang); n_.translate(V(x, y, 0)); return n_


def make_washer(x, y, z0):
    return solid_one(Part.makeCylinder(WASHER["d2"] / 2, WASHER["h"], V(x, y, z0)).cut(
        Part.makeCylinder(WASHER["d1"] / 2, WASHER["h"] + 2, V(x, y, z0 - 1))), "washer")


Z_SPR_TOP = ZT + p["spr_t"]
Z_HEAD = Z_SPR_TOP + WASHER["h"]
NUT_CEIL = Z0 + p["pocket_depth"]
hw_items = []   # dict(name, kind, group, solid, data)
for k_, ang in enumerate(p["strap_angles"]):
    for side, s_ in (("hub", S_H), ("arm", S_A)):
        x, y = local_to_global(A, s_, ang)
        grp = "hub" if side == "hub" else "armature"
        tag = "%s%d" % (side, k_)
        hw_items.append(dict(name="screw_" + tag, kind="screw_M3x6", group=grp, solid=make_shcs(L_SPRING_SCREW, x, y, Z_HEAD),
                             data=dict(xy=[x, y], z_bearing=Z_HEAD, length=L_SPRING_SCREW, mate="nut_" + tag)))
        hw_items.append(dict(name="washer_" + tag, kind="washer_M3", group=grp, solid=make_washer(x, y, Z_SPR_TOP),
                             data=dict(xy=[x, y], z0=Z_SPR_TOP)))
        hw_items.append(dict(name="nut_" + tag, kind="nut_M3", group=grp, solid=make_nut(x, y, NUT_CEIL - NUT["m"], ang),
                             data=dict(xy=[x, y], z0=NUT_CEIL - NUT["m"], z0_loose=Z0, corner_deg=ang)))
Z_CAP_TOP = CAP_Z0 + p["cap_t"]
Z_HEAD_AXLE = Z_CAP_TOP + WASHER["h"]
hw_items.append(dict(name="screw_axle", kind="screw_M3x25", group="fixed", solid=make_shcs(L_AXLE_SCREW, 0, 0, Z_HEAD_AXLE),
                     data=dict(xy=[0, 0], z_bearing=Z_HEAD_AXLE, length=L_AXLE_SCREW, mate="nut_axle")))
hw_items.append(dict(name="washer_axle", kind="washer_M3", group="fixed", solid=make_washer(0, 0, Z_CAP_TOP), data=dict(xy=[0, 0], z0=Z_CAP_TOP)))
hw_items.append(dict(name="nut_axle", kind="nut_M3", group="fixed", solid=make_nut(0, 0, sz1 - NUT["m"], SLOT_ANG),
                     data=dict(xy=[0, 0], z0=sz1 - NUT["m"], z0_loose=sz0, corner_deg=SLOT_ANG, slot_deg=SLOT_ANG)))

parts = [dict(name="base", group="fixed", solid=base), dict(name="coil", group="fixed", solid=coil),
         dict(name="cap", group="fixed", solid=cap), dict(name="hub", group="hub", solid=hub),
         dict(name="armature", group="armature", solid=armature)]
for k_ in range(3):
    parts.append(dict(name="spring%d" % k_, group="spring", solid=springs[k_]))
bodies = parts + hw_items
BY = {b["name"]: b for b in bodies}
MATES = {(b["name"], b["data"]["mate"]) for b in hw_items if b["kind"].startswith("screw")}


def pressed_solid(b):
    if b["name"].startswith("spring"):
        return springs_p[int(b["name"][-1])]
    if b["group"] == "armature":
        return moved(b["solid"], -delta)
    return b["solid"]


# ---------------- checks ----------------------------------------------------------------------
checks = []


def chk(name, ok, **kv):
    checks.append(dict(name=name, ok=bool(ok), **kv))


def vol_common(a_, b_):
    if not a_.BoundBox.intersect(b_.BoundBox):
        return 0.0
    c = a_.common(b_)
    return c.Volume if not c.isNull() else 0.0


def dist(a_, b_):
    return a_.distToShape(b_)[0]


TOUCH = 0.05
for b in bodies:
    chk("valid_" + b["name"], b["solid"].isValid() and b["solid"].Volume > 0, volume_mm3=round(b["solid"].Volume, 3))
for s_ in springs_p:
    chk("valid_pressed_spring", s_.isValid() and len(s_.Solids) == 1, volume_mm3=round(s_.Volume, 3))


def pair_scan(state, solids, rot_groups=None, rot=0.0):
    worst, n = 0.0, 0
    for (na, sa), (nb, sb) in itertools.combinations(solids.items(), 2):
        if (na, nb) in MATES or (nb, na) in MATES:
            continue
        if rot_groups is not None and ((na in rot_groups) == (nb in rot_groups)):
            continue
        v = vol_common(sa, sb); n += 1
        if v >= TOUCH:
            chk("overlap_%s_%s_%s" % (state, na, nb), False, common_mm3=round(v, 4))
        worst = max(worst, v)
    return worst, n


ROTOR = {b["name"] for b in bodies if b["group"] in ("hub", "armature", "spring")}
off = {b["name"]: b["solid"] for b in bodies}
pressed = {b["name"]: pressed_solid(b) for b in bodies}
w_, n_ = pair_scan("off", off)
chk("no_overlap_all_pairs_off", w_ < TOUCH, pairs=n_, worst_common_mm3=round(w_, 5))
w_, n_ = pair_scan("pressed", pressed)
chk("no_overlap_all_pairs_pressed", w_ < TOUCH, pairs=n_, worst_common_mm3=round(w_, 5))
for ang in (17.0, 45.0, 90.0, 200.0):
    for state, sol in (("off", off), ("pressed", pressed)):
        rs = {k: (rotz(v, ang) if k in ROTOR else v) for k, v in sol.items()}
        w_, n_ = pair_scan("%s_rot%g" % (state, ang), rs, ROTOR, ang)
        chk("no_overlap_rotor_vs_fixed_%s_rot%g" % (state, ang), w_ < TOUCH, pairs=n_, worst_common_mm3=round(w_, 5))

chk("off_armature_gap_to_poles", abs(dist(armature, base) - delta) < 1e-3, gap_mm=round(dist(armature, base), 4))
arm_p = pressed["armature"]
chk("pressed_armature_touches_poles", dist(arm_p, base) < 1e-3, dist_mm=round(dist(arm_p, base), 4))
d_ = dist(arm_p, coil)
chk("pressed_armature_clears_coil", d_ > 0.5, clearance_mm=round(d_, 4))
for nm in ("nut_arm0", "screw_arm0"):
    d_ = dist(pressed[nm], coil)
    chk("pressed_%s_clears_coil_nominal" % nm, d_ > 0.5, clearance_mm=round(d_, 4))
d_ = min(dist(s_, base) for s_ in spans_off); chk("free_span_clears_base_off", d_ > 0.2, min_mm=round(d_, 3))
d_ = min(dist(s_, base) for s_ in spans_p); chk("free_span_clears_base_pressed", d_ > 0.2, min_mm=round(d_, 3))
others = [v for k, v in pressed.items() if not k.startswith("spring")]
others_p = [pressed["hub"], pressed["armature"]] + [pressed[b["name"]] for b in hw_items]
mid = [rotz(box2(-50, 50, S_ROOT + 1.0, S_TIP - 6.0, 0, 80), ang) for ang in p["strap_angles"]]
d_mid = min(dist(sp.common(ib), o) for sp, ib in zip(spans_p, mid) for o in others_p)
chk("pressed_free_span_mid_clears_hub_armature_hardware", d_mid > 0.15, min_mm=round(d_mid, 3))
tan = [rotz(box2(-50, 50, S_TIP - 6.0, S_TIP + 0.5, 0, 80), ang) for ang in p["strap_angles"]]
v_tan = max(sp.common(ib).common(o).Volume for sp, ib in zip(spans_p, tan) for o in others_p)
xs = [S_TIP - 6.0 + 0.01 * i for i in range(601)]
gap_an = min(delta * (1 - (3 * x ** 2 - 2 * x ** 3)) for x in [(v - S_ROOT) / (S_TIP - S_ROOT) for v in xs] if x <= 1)
chk("pressed_span_tip_zone_tangent_no_penetration", v_tan < TOUCH and gap_an >= 0, common_mm3=round(v_tan, 4),
    analytic_min_gap_mm=round(gap_an, 4),
    note="guided beam: zero slope at the clamp, so the span meets the armature tangentially there by design")
d_ = dist(hub, Part.makeCylinder(p["axle_r"], p["axle_top"] - Z0 - 0.2, V(0, 0, Z0 + 0.1)))
chk("bore_radial_clearance", abs(d_ - (p["bore_r"] - p["axle_r"])) < 1e-3, clearance_mm=round(d_, 4))
chk("hub_sits_on_shoulder", dist(hub, base) < 1e-6)
d_cap = dist(cap, hub)
chk("cap_to_hub_axial_play", abs(d_cap - (p["axle_top"] - HUB_TOP)) < 1e-3 and d_cap > 0.2, play_mm=round(d_cap, 4))
chk("cap_retains_hub_overlap_radial", p["cap_r"] > p["bore_r"] + 1.5, overlap_mm=round(p["cap_r"] - p["bore_r"], 2))
chk("spring_strain_below_1pct", 3 * p["spr_t"] * delta / L_FREE ** 2 < 0.01, strain=round(3 * p["spr_t"] * delta / L_FREE ** 2, 5))

# Threads, tips and clearances (with ISO 4762 length tolerance)
thread_report = []
for b in hw_items:
    if not b["kind"].startswith("screw"):
        continue
    L = b["data"]["length"]; tol = TOL[L]; zb = b["data"]["z_bearing"]
    nut = BY[b["data"]["mate"]]; nz0 = nut["data"]["z0"]; nz1 = nz0 + NUT["m"]
    tips = (zb - L - tol, zb - L + tol)
    eng = [nz1 - max(t_, nz0) for t_ in tips]
    floor = Z0 if b["name"] != "screw_axle" else p["blind_z"]
    rec = dict(screw=b["name"], length_mm=L, tip_z_range=[round(t_, 3) for t_ in tips], nut_z=[round(nz0, 3), round(nz1, 3)],
               engagement_mm=[round(min(eng), 3), round(max(eng), 3)], pitches_min=round(min(eng) / SHCS["pitch"], 2),
               tip_margin_to_floor_mm=round(tips[0] - floor, 3))
    thread_report.append(rec)
    chk("thread_engagement_ge_4_pitches_" + b["name"], min(eng) >= 4 * SHCS["pitch"] - 1e-9, engagement_min_mm=round(min(eng), 3))
    chk("tip_inside_part_" + b["name"], tips[0] - floor >= 0.3, margin_mm=round(tips[0] - floor, 3))
    if b["group"] == "armature":
        chk("pressed_tip_clears_coil_worst_" + b["name"], tips[0] - delta - (p["floor_z"] + p["coil_h"]) > 0.5,
            clearance_mm=round(tips[0] - delta - (p["floor_z"] + p["coil_h"]), 3))
    # hex key access: nothing above the head inside a head-diameter cylinder
    x, y = b["data"]["xy"]
    acc = Part.makeCylinder(SHCS["dk"] / 2, 80.0 - (zb + SHCS["k"]), V(x, y, zb + SHCS["k"] + 0.01))
    blk = max(vol_common(acc, s_) for k, s_ in off.items() if k != b["name"])
    chk("hex_key_access_" + b["name"], blk < 1e-6, blocked_mm3=round(blk, 4))
    sh = Part.makeCylinder(SHCS["d"] / 2, L - 0.4, V(x, y, zb - L + 0.3))
    for k, s_ in off.items():
        if k.startswith(("base", "hub", "armature", "spring", "cap")):
            d_ = dist(sh, s_)
            if d_ < 0.15 and vol_common(sh, s_) > 1e-6:
                chk("clearance_hole_%s_%s" % (b["name"], k), False, dist_mm=round(d_, 4))
chk("nut_pocket_anti_rotation", NUT["s"] < p["pocket_af"] < NUT["e_min"] and NUT["s"] < p["slot_w"] < NUT["e_min"],
    pocket_af=p["pocket_af"], slot_w=p["slot_w"], nut_s=NUT["s"], nut_e_min=NUT["e_min"])
chk("bridge_rect_fits_inside_hex", p["hole_r"] <= p["pocket_af"] / (2 * math.sqrt(3)) + 1e-9,
    hole_r=p["hole_r"], half_flat=round(p["pocket_af"] / (2 * math.sqrt(3)), 4))
chk("nut_can_drop_into_pocket", p["pocket_depth"] >= NUT["m"] + 0.6 and p["slot_h"] >= NUT["m"] + 0.15)


# Wall thickness = distance from the pocket side faces to the outside of the part (bed opening and roof excluded).
def wall_mm(cutter, envelope, z0, z1, keep=None):
    band = Part.makeBox(300, 300, z1 - z0, V(-150, -150, z0))
    c = cutter.common(band)
    if keep is not None:
        c = c.common(keep)
    outside = band.cut(envelope)
    return c.distToShape(outside)[0]


min_wall = 1.2
walls = {}
for nm, cuts, env in (("hub", hub_cut, hub_env), ("armature", arm_cut, arm_env)):
    for i, c in enumerate(cuts):
        wv = wall_mm(c, env, Z0 + 0.05, NUT_CEIL - 0.01)
        walls["%s%d" % (nm, i)] = round(wv, 3)
        chk("pocket_wall_ge_%.1f_%s%d" % (min_wall, nm, i), wv >= min_wall - 1e-6, wall_mm=round(wv, 3))
closed_half = rotz(Part.makeBox(20, 40, 50, V(-20, -20, 0)), SLOT_ANG)     # slot frame x' <= 0 (open end excluded)
wv = wall_mm(slot_cut, base_env, sz0 + 0.05, sz1 - 0.01, closed_half)
walls["slot_closed_end"] = round(wv, 3)
chk("slot_wall_ge_1.2_base", wv >= min_wall, wall_mm=round(wv, 3))
chk("roof_above_nut_ge_2mm", min(ZT - NUT_CEIL, Z0 - sz1) >= 2.0, pad_roof_mm=round(ZT - NUT_CEIL, 3), slot_roof_mm=round(Z0 - sz1, 3))
pp = hexagon(A, S_H, p["pocket_af"], 0.0)
chk("pad_wall_analytic", min(min(x for x, _ in pp) - p["pad_u0"], p["pad_u1"] - max(x for x, _ in pp),
                             p["pad_s1"] - max(y for _, y in pp), min(y for _, y in pp) - p["pad_s0"]) >= min_wall,
    walls_mm=[round(min(x for x, _ in pp) - p["pad_u0"], 3), round(p["pad_u1"] - max(x for x, _ in pp), 3),
              round(p["pad_s1"] - max(y for _, y in pp), 3), round(min(y for _, y in pp) - p["pad_s0"], 3)])
r_in = min(math.hypot(*local_to_global(x, y, 0)) for x, y in hexagon(A, S_A, p["pocket_af"], 0.0))
r_out = max(math.hypot(*local_to_global(x, y, 0)) for x, y in hexagon(A, S_A, p["pocket_af"], 0.0))
chk("armature_pockets_over_coil_groove_only", p["inner_ro"] + 0.5 < r_in and r_out < p["outer_ri"] - 0.5,
    pocket_r_range=[round(r_in, 3), round(r_out, 3)], groove=[p["inner_ro"], p["outer_ri"]])

# ---------------- mechanics (hand estimate, not FEA) -------------------------------------
w, t = p["spr_w"], p["spr_t"]
I = w * t ** 3 / 12.0
mech = dict(model="three fixed-guided leaf springs, Euler-Bernoulli; no FEA, no print anisotropy, clamp compliance ignored",
            spring=dict(L_free_mm=round(L_FREE, 3), w_mm=w, t_mm=t, I_mm4=round(I, 5)), deflection_mm=delta,
            max_surface_strain=round(3 * t * delta / L_FREE ** 2, 5), materials={})
for mat, E in (("PLA", (2300.0, 3500.0)), ("PETG", (1700.0, 2100.0))):
    ks = [3 * 12 * e * I / L_FREE ** 3 for e in E]
    fore = 0.6 * delta ** 2 / L_FREE
    out = []
    for e in E:
        k_ax = e * w * t / L_FREE
        k_lat = 12 * e * (t * w ** 3 / 12) / L_FREE ** 3
        k_eff = k_ax * k_lat * S_TIP ** 2 / (k_ax * A ** 2 + k_lat * S_TIP ** 2)
        f_lin = 3 * 12 * e * I * delta / L_FREE ** 3
        out.append(round(f_lin + 3 * 2 * k_eff * (0.6 / L_FREE) ** 2 * delta ** 3, 2))
    mech["materials"][mat] = dict(E_MPa=E, k_total_N_per_mm=[round(k, 3) for k in ks],
                                  press_force_linear_N=[round(k * delta, 2) for k in ks], press_force_with_stretch_N=out,
                                  max_stress_MPa=[round(e * 3 * t * delta / L_FREE ** 2, 1) for e in E])
mech["note"] = "Order-of-magnitude estimate. Real printed springs may differ by about a factor of 2."

# ---------------- print-orientation STLs -----------------------------------------------------
spr_print = spring_local(0.0); spr_print.translate(V(-A, -(S_H + S_A) / 2, 0)); spr_print.rotate(V(0, 0, 0), V(0, 0, 1), -90)
cap_print = moved(cap, -CAP_Z0)
parts_print = {
    "01_base_grey": (base, BASE_BRIDGES, ("slot",)),
    "02_coil_ring_orange": (coil_print, (), ()),
    "03_hub_violet": (moved(hub, -Z0), tuple(z - Z0 for z in HUB_BRIDGES), ("hub",)),
    "04_armature_blue": (moved(armature, -Z0), tuple(z - Z0 for z in ARM_BRIDGES), ("arm",)),
    "05_leaf_spring_green_print4": (spr_print, (), ()),
    "06_retaining_cap_grey": (cap_print, (), ()),
}
POCKET_XY = {"hub": [local_to_global(A, S_H, a_) for a_ in p["strap_angles"]],
             "arm": [local_to_global(A, S_A, a_) for a_ in p["strap_angles"]]}


def in_bridge_zone(kind, cx, cy):
    if kind == "slot":
        c, s_ = math.cos(math.radians(-SLOT_ANG)), math.sin(math.radians(-SLOT_ANG))
        xr, yr = cx * c - cy * s_, cx * s_ + cy * c
        return -R_slot - 0.05 <= xr <= 9.6 and abs(yr) <= sw / 2 + 0.05
    return any(math.hypot(cx - x, cy - y) <= p["pocket_af"] / math.sqrt(3) + 0.05 for x, y in POCKET_XY[kind])


def mesh_of(shape):
    return MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.01, AngularDeflection=math.radians(4), Relative=False)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


files = {}
OVERHANG_NZ = -math.sin(math.radians(45.0))
for nm, (s_, bridges, zones) in parts_print.items():
    bb = s_.BoundBox
    msh = mesh_of(s_)
    path = os.path.join(OUT_PRINT, nm + ".stl"); msh.write(path)
    over = bed = bridge = 0.0
    for f in msh.Facets:
        nz = f.Normal.z; zc = sum(pt[2] for pt in f.Points) / 3.0
        cx = sum(pt[0] for pt in f.Points) / 3.0; cy = sum(pt[1] for pt in f.Points) / 3.0
        if zc < 0.01 and nz < -0.99:
            bed += f.Area
        elif nz < OVERHANG_NZ - 1e-6:
            if nz < -0.999 and any(abs(zc - zb_) < 1e-3 for zb_ in bridges) and any(in_bridge_zone(z_, cx, cy) for z_ in zones):
                bridge += f.Area
            else:
                over += f.Area
    rd = Mesh.Mesh(path)
    files[nm] = dict(path=os.path.relpath(path, ROOT), bytes=os.path.getsize(path), sha256=sha(path), facets=rd.CountFacets,
                     bbox_mm=[round(bb.XLength, 2), round(bb.YLength, 2), round(bb.ZLength, 2)], volume_cm3=round(s_.Volume / 1000.0, 3),
                     bed_contact_mm2=round(bed, 1), overhang_gt45_mm2=round(over, 3), bridged_ceiling_mm2=round(bridge, 2))
    chk("print_%s_on_bed" % nm, abs(bb.ZMin) < 1e-6 and bed > 30.0, bed_contact_mm2=round(bed, 1))
    chk("print_%s_no_unsupported_overhang" % nm, over < 0.5, area_mm2=round(over, 3), bridged_mm2=round(bridge, 2))
    chk("print_%s_fits_180_bed" % nm, bb.XLength < 175 and bb.YLength < 175 and bb.ZLength < 175)
    chk("stl_%s_closed_manifold" % nm, rd.isSolid() and not rd.hasNonManifolds() and rd.countComponents() == 1, components=rd.countComponents())
    chk("stl_%s_volume_matches_cad" % nm, abs(rd.Volume - s_.Volume) / s_.Volume < 0.005, stl_mm3=round(rd.Volume, 2), cad_mm3=round(s_.Volume, 2))
chk("max_bridge_span_mm", max(p["pocket_af"], p["slot_w"]) <= 6.0, span_mm=max(p["pocket_af"], p["slot_w"]))

# ---------------- render meshes (assembly coordinates) + section cut-away --------------------
wedge = rotz(Part.makeCylinder(120.0, 140.0, V(0, 0, -20), V(0, 0, 1), SECTION_A1 - SECTION_A0), SECTION_A0)
render = {}
for b in bodies:
    nm = b["name"]
    render[nm] = dict(group=b["group"], kind=b.get("kind", "part"), off=nm + ".stl", section=nm + "_section.stl")
    mesh_of(b["solid"]).write(os.path.join(OUT_RENDER, nm + ".stl"))
    sec = b["solid"].cut(wedge)
    if sec.Volume > 1e-6:
        mesh_of(sec).write(os.path.join(OUT_RENDER, nm + "_section.stl"))
    else:
        render[nm]["section"] = None
    if b["group"] in ("armature", "spring"):
        ps = pressed_solid(b)
        render[nm]["pressed"] = nm + "_pressed.stl"
        mesh_of(ps).write(os.path.join(OUT_RENDER, nm + "_pressed.stl"))
        sec = ps.cut(wedge)
        render[nm]["pressed_section"] = (nm + "_pressed_section.stl") if sec.Volume > 1e-6 else None
        if sec.Volume > 1e-6:
            mesh_of(sec).write(os.path.join(OUT_RENDER, nm + "_pressed_section.stl"))
    if "data" in b:
        render[nm]["data"] = b["data"]

# ---------------- FreeCAD document + STEP ------------------------------------------------------
doc = App.newDocument("BrakeTeachingModelV2")
sheet = doc.addObject("Spreadsheet::Sheet", "Params"); sheet.Label = "寸法（手で押す教材・実ブレーキではない）"
for i, (k_, v_) in enumerate(sorted((k_, v_) for k_, v_ in P.items() if isinstance(v_, (int, float)))):
    sheet.set("A%d" % (i + 1), k_); sheet.set("B%d" % (i + 1), str(v_))
bom = doc.addObject("Spreadsheet::Sheet", "HardwareBOM"); bom.Label = "ねじ部品表（仕様のみ・未購入）"
BOM = [("六角穴付きボルト M3x6 (ISO 4762)", 6, "板ばねの固定"), ("六角穴付きボルト M3x25 (ISO 4762)", 1, "抜け止めキャップの固定"),
       ("六角ナット M3 (ISO 4032, 二面幅5.5)", 7, "部品の六角穴へ入れる"), ("平座金 M3 (ISO 7089, 外径7, 厚0.5)", 7, "ねじ頭の下"),
       ("六角棒レンチ 2.5mm", 1, "締付け工具")]
for i, row in enumerate([("品名", "数量", "用途")] + BOM):
    for j, v_ in enumerate(row):
        bom.set("%s%d" % ("ABC"[j], i + 1), str(v_))
groups = {}
for gname, glabel in (("Printed", "印刷部品（OFF位置）"), ("Hardware", "ねじ・ナット・座金（簡略形状、ねじ山なし）"), ("Pressed", "押した状態（確認用）")):
    g = doc.addObject("App::DocumentObjectGroup", gname); g.Label = glabel; groups[gname] = g
JA = dict(base="ベース・フィールド・軸（灰）", coil="コイル輪（橙・飾り）", cap="抜け止めキャップ（灰）", hub="ハブ（紫）",
          armature="アーマチュア円盤（青）", spring0="板ばね1（緑）", spring1="板ばね2（緑）", spring2="板ばね3（緑）")
doc_objs = []
for b in bodies:
    o = doc.addObject("Part::Feature", b["name"]); o.Shape = b["solid"]
    o.Label = JA.get(b["name"], b["name"])
    (groups["Printed"] if b in parts else groups["Hardware"]).addObject(o); doc_objs.append((b["name"], b["solid"]))
for b in bodies:
    if b["group"] in ("armature", "spring"):
        o = doc.addObject("Part::Feature", b["name"] + "_pressed"); o.Shape = pressed_solid(b); o.Label = JA.get(b["name"], b["name"]) + "（押した状態）"
        groups["Pressed"].addObject(o); doc_objs.append((b["name"] + "_pressed", pressed_solid(b)))
doc.recompute()
fcstd = os.path.join(OUT_CAD, "brake_teaching_model_v2_screws.FCStd")
doc.saveAs(fcstd)
step = os.path.join(OUT_CAD, "brake_teaching_model_v2_assembly_off.step")
Part.makeCompound([b["solid"] for b in bodies]).exportStep(step)
App.closeDocument(doc.Name)
d2 = App.openDocument(fcstd)
re_ok = all(d2.getObject(nm) is not None and d2.getObject(nm).Shape.isValid() and abs(d2.getObject(nm).Shape.Volume - s_.Volume) < 1e-6 * s_.Volume
            for nm, s_ in doc_objs)
chk("fcstd_reopen_shapes_match", re_ok, objects=len(doc_objs))
App.closeDocument(d2.Name)
st = Part.read(step)
chk("step_readback_solids", len(st.Solids) == len(bodies), solids=len(st.Solids), expected=len(bodies))

manifest = dict(
    units="mm", frame="Z up, axis Z, base bottom z=0", Z0=Z0, ZT=ZT, delta=delta, hub_top=HUB_TOP, axle_top=p["axle_top"],
    strap_angles=list(p["strap_angles"]), spring=dict(a=A, s_hub=S_H, s_arm=S_A, s_root=S_ROOT, s_tip=S_TIP, t=p["spr_t"], w=p["spr_w"]),
    section_deg=[SECTION_A0, SECTION_A1], slot_deg=SLOT_ANG, slot_z=[sz0, sz1], pitch=SHCS["pitch"], render=render,
    shcs=SHCS, nut=NUT, washer=WASHER)
with open(os.path.join(OUT_RES, "assembly-manifest.json"), "w") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=1)
summary = dict(
    title="Screw-assembled armature and leaf-spring brake teaching model (v2)",
    status="digital model only; not printed, not sliced, not physically tested; hardware is a specification, not purchased",
    params=P, derived=dict(Z0=Z0, ZT=ZT, S_A=S_A, L_free=L_FREE, section_deg=[SECTION_A0, SECTION_A1]),
    hardware_bom=[dict(item=a_, qty=b_, use=c_) for a_, b_, c_ in BOM], thread_report=thread_report, pocket_walls_mm=walls,
    checks=checks, n_checks=len(checks), n_failed=sum(1 for c in checks if not c["ok"]), mechanics=mech, files=files,
    cad=dict(fcstd=dict(path=os.path.relpath(fcstd, ROOT), bytes=os.path.getsize(fcstd), sha256=sha(fcstd)),
             step=dict(path=os.path.relpath(step, ROOT), bytes=os.path.getsize(step), sha256=sha(step))))
with open(os.path.join(OUT_RES, "print-model-v2-validation.json"), "w") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=1)
print("CHECKS", len(checks), "FAILED", summary["n_failed"])
for c in checks:
    if not c["ok"]:
        print("FAIL", c)
