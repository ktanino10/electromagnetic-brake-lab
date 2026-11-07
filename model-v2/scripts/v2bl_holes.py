# Hole sheets: printed plastic parts with screw holes, nut pockets, the side slot and the bore.
# Assembly visualisation only (CAD nominal sizes). Not printed, not purchased, not physically tested.
import sys, math, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy, bmesh
from mathutils import Vector
from v2bl_common import (MAN, MM, W, H, OUT, ROOT, CHECKS, TEXTS, chk, reset, mats, lights, still_cam, obj_pts, px,
                         label, header, check_texts, objs_in_frame, text)
from v2bl_parts import load_all, R

STILLS = OUT / "stills-holes"; STILLS.mkdir(parents=True, exist_ok=True)
FOOT = "デジタル模型の見える化（CADの名目寸法）／未印刷・未購入・実物未検証"
A0, A1 = MAN["section_deg"]
T0 = Vector((math.cos(math.radians(A0)), math.sin(math.radians(A0)), 0))
T1 = Vector((math.cos(math.radians(A1)), math.sin(math.radians(A1)), 0))
HUB = ["screw_hub%d" % i for i in range(3)]; ARM = ["screw_arm%d" % i for i in range(3)]
ONLY = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def xy(name):
    return R[name]["data"]["xy"]


def wpt(o, p):
    return o.matrix_world @ (Vector(p) * MM - Vector(o["org"]))


def setup(section=False, names=None):
    sc = reset(); M = mats(); lights(sc)
    full, sec = load_all(M, names=names, section=section)
    for d in (full, sec):
        for o in d.values():
            if o is not None:
                o["org"] = tuple(o.location)
    return sc, M, full, sec


def table(sc, M, half=400):
    me = bpy.data.meshes.new("table"); s = half * MM
    me.from_pydata([(-s, -s, -0.05 * MM), (s, -s, -0.05 * MM), (s, s, -0.05 * MM), (-s, s, -0.05 * MM)], [], [(0, 1, 2, 3)])
    o = bpy.data.objects.new("table", me); sc.collection.objects.link(o); o.data.materials.append(M["table"])
    return o


def hide(objs):
    for o in objs:
        if o is not None:
            o.hide_render = True; o.hide_viewport = True


def lab(sc, cam, M, body, mat, targets, dx, dy, size=26, align="LEFT"):
    p0 = px(sc, cam, targets[0])
    return label(sc, cam, M, body, p0[0] + dx, p0[1] + dy, size, mat, align, targets)


def shoot(sc, cam, name, objs):
    if objs:
        objs_in_frame(sc, cam, objs, name)
    check_texts(sc, cam, name)
    sc.render.filepath = str(STILLS / name)
    bpy.ops.render.render(write_still=True)


def dashes(sc, M, segs, r=0.22, on=2.0, off=1.4):
    bm = bmesh.new()
    for p0, p1 in segs:
        a, b = Vector(p0), Vector(p1); d = b - a; L = d.length; u = d.normalized()
        q = u.to_track_quat("Z", "Y").to_matrix().to_4x4()
        t = 0.0
        while t < L - 0.2:
            seg = min(on, L - t); c = a + u * (t + seg / 2)
            m = q.copy(); m.translation = c * MM
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r * MM, radius2=r * MM, depth=seg * MM, matrix=m)
            t += on + off
    me = bpy.data.meshes.new("axis_lines"); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("axis_lines", me); sc.collection.objects.link(o); o.data.materials.append(M["arrow"])
    return o


# ---------------- H1: the six printed parts from above ----------------
def h1():
    sc, M, F, S = setup(names=["base", "coil", "hub", "armature", "spring0", "spring1", "spring2", "cap"])
    table(sc, M)
    F["base"].rotation_euler.z = math.radians(-90 - A1)          # side slot faces the camera
    F["coil"].location = Vector((-122, 0, 0)) * MM
    F["armature"].location = Vector((124, 0, 0)) * MM
    F["hub"].location = Vector((-100, -98, 0)) * MM
    F["cap"].location = Vector((72, -104, 0)) * MM
    spare = F["spring0"].copy(); sc.collection.objects.link(spare)
    for k, o in enumerate([F["spring0"], F["spring1"], F["spring2"], spare]):
        a = MAN["strap_angles"][k if k < 3 else 0]
        o.location = Vector((0, -86 - 12 * k, 0)) * MM
        o.rotation_euler.z = math.radians(-(a + 90))
    bpy.context.view_layer.update()
    objs = [o for o in F.values()] + [spare]
    cam = still_cam(sc, -90, 52, obj_pts(objs), region=(60, 200, 1860, 1005))
    header(sc, cam, M, "印刷するプラスチック部品6種とねじ穴（上から）",
           "締結はすべてM3。ねじが通る穴はØ3.4、ナットは裏側の六角穴に入る（次の図）", FOOT)
    b, h, a, c = F["base"], F["hub"], F["armature"], F["cap"]
    zt = MAN["ZT"]
    lab(sc, cam, M, "台座：中心の柱にM3通し穴 Ø3.4", M["tgrey"], [wpt(b, (0, 0, MAN["axle_top"]))], -160, -175)
    s_ = Vector((math.cos(math.radians(A1)), math.sin(math.radians(A1)), 0)) * 7.2
    lab(sc, cam, M, "柱の横溝：軸用ナットを横から入れる", M["tgrey"], [wpt(b, (s_.x, s_.y, 13.3))], 60, 150)
    lab(sc, cam, M, "コイル役リング：穴なし（溝にはめるだけ）", M["torange"], [wpt(F["coil"], (0, 40, 15.4))], -40, -150)
    lab(sc, cam, M, "円盤：M3通し穴 Ø3.4 ×3", M["tblue"], [wpt(a, (*xy(n), zt)) for n in ARM], -10, -170)
    lab(sc, cam, M, "ハブ：通し穴 Ø3.4 ×3／軸穴 Ø8.7", M["tviolet"], [wpt(h, (*xy(n), zt)) for n in HUB] +
        [wpt(h, (0, 0, MAN["hub_top"]))], -60, 120)
    sp = MAN["spring"]
    lab(sc, cam, M, "板ばね（PETG）：穴 Ø3.4 ×2　3枚＋予備1", M["tgreen"],
        [wpt(F["spring0"], (sp["a"], sp["s_hub"], zt + sp["t"])), wpt(F["spring0"], (sp["a"], sp["s_arm"], zt + sp["t"]))], -60, -72)
    lab(sc, cam, M, "キャップ：穴 Ø3.4", M["tgrey"], [wpt(c, (0, 1.7 + 2.4, MAN["axle_top"] + 2))], 40, 110)
    shoot(sc, cam, "H1_parts_top", objs)


# ---------------- H2: underside of hub and armature with hex nut pockets ----------------
def h2():
    sc, M, F, S = setup(names=["hub", "armature"] + ["nut_hub%d" % i for i in range(3)] + ["nut_arm%d" % i for i in range(3)])
    table(sc, M)
    a, h = F["armature"], F["hub"]
    a.rotation_euler.x = math.pi; a.location = Vector((-30, 0, 5.5)) * MM
    h.rotation_euler.x = math.pi; h.location = Vector((82, 0, MAN["hub_top"] - MAN["Z0"])) * MM
    bpy.context.view_layer.update()
    lift = {"hub0": -3.2, "hub2": 11.0, "arm0": -3.2, "arm1": 5.0, "arm2": 11.0}
    for tag, dz in lift.items():
        part = h if tag.startswith("hub") else a
        x, y = R["nut_" + tag]["data"]["xy"]
        top = wpt(part, (x, y, MAN["Z0"]))
        F["nut_" + tag].location = top + Vector((0, 0, dz * MM))
    hide([F["nut_hub1"]])
    bpy.context.view_layer.update()
    objs = [o for k, o in F.items() if k != "nut_hub1"]
    cam = still_cam(sc, -62, 56, obj_pts(objs), region=(60, 210, 1860, 1005))
    header(sc, cam, M, "裏返すと見える：六角ナット穴（ハブ3か所・円盤3か所）",
           "ナットは六角穴にはまるので、上からねじを締めても回らない（図は上下を逆にして表示）", FOOT)
    z0 = MAN["Z0"]
    lab(sc, cam, M, "六角穴：二面幅5.9mm・深さ3.2mm", M["tblue"], [wpt(a, (*R["nut_arm1"]["data"]["xy"], z0)),
        wpt(a, (*R["nut_arm2"]["data"]["xy"], z0))], -330, -150)
    lab(sc, cam, M, "M3ナット（二面幅5.5mm・厚さ2.4mm）", M["tsteel"], [F["nut_hub2"].location + Vector((0, 0, 2.4 * MM))], 80, -120)
    lab(sc, cam, M, "はめ込んだ状態", M["tsteel"], [F["nut_arm0"].location + Vector((0, 0, 3.2 * MM))], 60, 140)
    lab(sc, cam, M, "空の六角穴：奥の小さな段差はサポートなしで印刷するためのブリッジ", M["tviolet"],
        [wpt(h, (*R["nut_hub1"]["data"]["xy"], z0 + 3.4))], 250, 110, align="RIGHT")
    shoot(sc, cam, "H2_underside_nut_pockets", objs)


def sec_scene(names_hidden=()):
    sc, M, F, S = setup(section=True)
    hide(F.values())
    hide([S[n] for n in names_hidden])
    return sc, M, F, S


# ---------------- H3: one spring screw in section ----------------
def h3():
    sc, M, F, S = sec_scene()
    c = Vector((*xy("screw_hub0"), 0))
    pts = [(c + T0 * s + Vector((0, 0, z))) * MM for s in (-11, 11) for z in (14.5, 28.5)]
    cam = still_cam(sc, A0 + 90, 8, pts, region=(470, 190, 1450, 1005))
    header(sc, cam, M, "断面で見る：M3×6でハブ・板ばねを固定するところ",
           "ねじは平座金と板ばね、ハブの通し穴を通り、下の六角穴のナットへ（ねじ山は見た目用の表示）", FOOT)
    P = lambda lam, z: (c + T0 * lam + Vector((0, 0, z))) * MM
    lab(sc, cam, M, "M3×6 六角穴付きボルト", M["tsteel"], [P(1.0, 25.6)], -420, -90)
    lab(sc, cam, M, "平座金 M3（厚さ0.5）", M["tsteel"], [P(2.9, 24.05)], -330, -10)
    lab(sc, cam, M, "板ばね（厚さ0.8）", M["tgreen"], [P(2.9, 23.4)], -310, 70)
    lab(sc, cam, M, "ハブ（紫・印刷）", M["tviolet"], [P(4.2, 22.3)], -260, 150)
    lab(sc, cam, M, "通し穴 Ø3.4（ねじ外径3.0）", M["tsteel"], [P(-1.6, 22.2)], 260, -150)
    lab(sc, cam, M, "M3ナット：六角穴の天井まで引き上げて締まる", M["tsteel"], [P(-2.6, 19.5)], 200, 30)
    lab(sc, cam, M, "ナットにかかるねじ長さ 最小約2.2mm（計算）", M["tsteel"], [P(-0.9, 18.8)], 240, 150)
    shoot(sc, cam, "H3_section_spring_screw", [S["screw_hub0"], S["nut_hub0"], S["washer_hub0"]])


# ---------------- H4: centre post, side slot and the M3x25 axle screw ----------------
def h4():
    sc, M, F, S = sec_scene()
    pts = [(T1 * s + Vector((0, 0, z))) * MM for s in (-12, 46) for z in (2, 38)]
    cam = still_cam(sc, A1 - 90, 8, pts, region=(60, 190, 1860, 1005))
    header(sc, cam, M, "断面で見る：中心の柱・横溝ナット・軸ボルトM3×25",
           "軸ボルトはキャップと平座金から柱の通し穴を下り、横溝に入れたナットへねじ込む", FOOT)
    P = lambda lam, z: (T1 * lam + Vector((0, 0, z))) * MM
    lab(sc, cam, M, "軸ボルト M3×25", M["tsteel"], [P(0.6, 30.5)], -330, -150)
    lab(sc, cam, M, "キャップ＋平座金", M["tgrey"], [P(5.0, 34.8)], 130, -40)
    lab(sc, cam, M, "ハブの軸穴 Ø8.7 と柱 Ø8.0：すき間0.35", M["tviolet"], [P(4.2, 29.0)], 120, -60)
    lab(sc, cam, M, "柱の中のM3通し穴 Ø3.4", M["tgrey"], [P(1.6, 21.0)], -420, -40)
    lab(sc, cam, M, "横溝のナット（幅5.9×高さ2.6の溝）", M["tsteel"], [P(2.0, 13.3)], -440, 110)
    lab(sc, cam, M, "円盤側：六角穴のナット＋M3×6", M["tblue"], [P(39.5, 19.6)], -60, 170)
    shoot(sc, cam, "H4_section_center_post", [S["screw_axle"], S["nut_axle"], S["washer_axle"], S["cap"]])


# ---------------- H5: exploded view with screw axes ----------------
def h5():
    sc, M, F, S = setup()
    table(sc, M, half=6000)
    L = 40.0
    lift = dict(hub=L, armature=L, spring0=L + 9, spring1=L + 9, spring2=L + 9, cap=L + 34)
    for n, ent in R.items():
        k = ent["kind"]
        dz = lift.get(n, 0.0)
        if k == "nut_M3" and n != "nut_axle":
            dz = L - 11
        elif k == "washer_M3":
            dz = L + 16 if n != "washer_axle" else L + 42
        elif k == "screw_M3x6":
            dz = L + 30
        elif k == "screw_M3x25":
            dz = L + 76
        F[n].location += Vector((0, 0, dz * MM))
    nut = F["nut_axle"]; nut.location += T1 * 26 * MM + Vector((0, 0, 0.6 * MM))
    segs = []
    for n in HUB + ARM:
        x, y = xy(n); segs.append(((x, y, MAN["Z0"] + L - 11), (x, y, 24.3 + L + 30 - 6)))
    segs.append(((0, 0, 14.6), (0, 0, 36.3 + L + 76 - 25)))
    segs.append((tuple(T1 * 22 + Vector((0, 0, 13.3))), tuple(T1 * 5 + Vector((0, 0, 13.3)))))
    dashes(sc, M, segs)
    bpy.context.view_layer.update()
    objs = list(F.values())
    cam = still_cam(sc, -66, 14, obj_pts(objs), region=(520, 175, 1400, 1012))
    header(sc, cam, M, "分解図：ねじ・ナット・平座金が通る穴の位置", "橙の点線＝ねじの通り道。数はM3×6 6本、M3×25 1本、ナット7個、平座金7枚", FOOT)
    lab(sc, cam, M, "M3×25（軸ボルト）", M["tsteel"], [F["screw_axle"].location], -420, 0)
    lab(sc, cam, M, "平座金", M["tsteel"], [F["washer_axle"].location], 300, 0)
    lab(sc, cam, M, "キャップ", M["tgrey"], [F["cap"].location + Vector((0, 0, 2 * MM))], -380, 0)
    lab(sc, cam, M, "M3×6 ×6＋平座金", M["tsteel"], [F["screw_arm0"].location, F["washer_arm0"].location], 330, -20)
    lab(sc, cam, M, "板ばね ×3", M["tgreen"], [F["spring0"].matrix_world.translation], 380, 0)
    lab(sc, cam, M, "ハブ・円盤", M["tblue"], [F["armature"].location + Vector((0, 0, 3 * MM))], -400, 0)
    lab(sc, cam, M, "M3ナット ×6（六角穴へ）", M["tsteel"], [F["nut_arm1"].location], -330, 40)
    lab(sc, cam, M, "柱の横溝へ入れるナット", M["tsteel"], [nut.location], -380, 40)
    lab(sc, cam, M, "台座・コイル役リング", M["tgrey"], [Vector((0, 0, 3 * MM)) + T1 * 55 * MM], -300, 60)
    shoot(sc, cam, "H5_exploded_axes", objs)


SHOTS = dict(H1=h1, H2=h2, H3=h3, H4=h4, H5=h5)
for k, f in SHOTS.items():
    if not ONLY or k in ONLY:
        f()
rep = dict(n_checks=len(CHECKS), n_failed=sum(not c["ok"] for c in CHECKS), checks=CHECKS)
(ROOT / "results").mkdir(exist_ok=True)
json.dump(rep, open(ROOT / "results" / ("blender-holes-report%s.json" % ("-" + "-".join(ONLY) if ONLY else "")), "w"),
          ensure_ascii=False, indent=1)
print("HOLES CHECKS", rep["n_checks"], "FAILED", rep["n_failed"])
for c in CHECKS:
    if not c["ok"]:
        print("FAIL", c)
