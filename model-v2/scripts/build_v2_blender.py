"""Build the native animation and the same geometry/poses for the offline viewer."""
import sys, json, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy, bmesh
from mathutils import Vector
from v2bl_common import (ROOT, OUT, MAN, MM, W, H, CHECKS, chk, reset, mats, lights,
                         smooth, still_cam, box_pts, header, check_texts)
from v2bl_parts import load_all, R
from assembly_sequence import Sequence, DURATION, FPS, STAGES, stage_at, press_at

OUT.mkdir(exist_ok=True)
(ROOT / "web").mkdir(exist_ok=True)
sc = reset()
sc.render.fps = FPS
sc.frame_end = DURATION * FPS
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1280, 720, 100
sc.eevee.taa_render_samples = 32
M = mats()
for n in ("grey", "violet", "blue"):
    M[n].surface_render_method = "BLENDED"
lights(sc)
full, sec = load_all(M, section=True)
origins = {n: [x / MM for x in o.location] for n, o in full.items()}
seq = Sequence(MAN, origins)
spring_keys = {}


def spring_shape(o, n):
    org = Vector(origins[n]) * MM
    ang = math.radians(MAN["strap_angles"][int(n[-1])])
    normal = Vector((-math.sin(ang), math.cos(ang), 0))
    a, b = MAN["spring"]["s_root"], MAN["spring"]["s_tip"]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for i in range(1, 41):
        co = normal * ((a + (b - a) * i / 41) * MM) - org
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                              plane_co=co, plane_no=normal, dist=1e-7)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(o.data)
    bm.free()
    smooth(o, 30)
    o.shape_key_add(name="Basis")
    key = o.shape_key_add(name="Pressed")
    ds = []
    for v in key.data:
        s = (v.co + org).dot(normal) / MM
        u = min(1.0, max(0.0, (s - a) / (b - a)))
        dz = -MAN["delta"] * (3 * u * u - 2 * u * u * u) * MM
        v.co.z += dz
        ds.append(dz / MM)
    if o.name.endswith("_sec"):
        chk(o.name + "_spring_displacement_range", min(ds) >= -MAN["delta"] - 1e-6 and max(ds) <= 1e-6,
            minimum_mm=min(ds), maximum_mm=max(ds))
    else:
        chk(o.name + "_spring_endpoints", abs(min(ds) + MAN["delta"]) < 1e-6 and abs(max(ds)) < 1e-6)
    spring_keys[o.name] = key


for n in ("spring0", "spring1", "spring2"):
    spring_shape(full[n], n)
    if sec[n]:
        spring_shape(sec[n], n)

all_objs = list(full.values()) + [o for o in sec.values() if o]
for o in bpy.context.selected_objects:
    o.select_set(False)
for o in all_objs:
    o.select_set(True)
    o["part_name"] = o.name.removesuffix("_sec")
    o["section_mesh"] = o.name.endswith("_sec")
    o["units_note"] = "One exported unit = 10 CAD mm"
bpy.ops.export_scene.gltf(filepath=str(OUT / "brake-model-v2.glb"), export_format="GLB",
                          use_selection=True, export_animations=False, export_extras=True)

frames = []
pref = bpy.context.preferences.edit
old = pref.keyframe_new_interpolation_type
pref.keyframe_new_interpolation_type = "LINEAR"
for f in range(DURATION * FPS + 1):
    t = f / FPS
    poses = seq.poses(t)
    press = press_at(t)
    frames.append([[round(v, 7) for v in poses[n]] for n in seq.names])
    for n in seq.names:
        p = poses[n]
        for o, cut in ((full[n], False), (sec[n], True)):
            if o is None:
                continue
            o.location = Vector(p[:3]) * MM
            # Section plane stays in the CAD frame; assembly is fully seated during this shot.
            o.rotation_euler = (0, 0, 0 if cut else p[3])
            o.hide_render = not (71 <= t < 84) if cut else 71 <= t < 84
            if not cut and 10.5 <= t < 18 and n not in ("base", "coil", "nut_axle"):
                o.hide_render = True
            if not cut and 18 <= t < 41 and R[n]["group"] == "fixed":
                o.hide_render = True
            o.keyframe_insert("location", frame=f + 1)
            o.keyframe_insert("rotation_euler", frame=f + 1)
            if f == 0 or f in (int(10.5 * FPS), 18 * FPS, 41 * FPS, 71 * FPS, 84 * FPS):
                o.keyframe_insert("hide_render", frame=f + 1)
            if o.name in spring_keys:
                key = spring_keys[o.name]
                key.value = press
                key.keyframe_insert("value", frame=f + 1)
pref.keyframe_new_interpolation_type = old

# Independent expected endpoint and thread-advance assertions.
for n, p in seq.poses(87).items():
    chk(n + "_final_CAD_position", max(abs(a - b) for a, b in zip(p[:3], origins[n])) < 1e-5)
for name, start, end in (("screw_hub0", 34.2, 37.4), ("screw_arm1", 35.6, 38.8), ("screw_axle", 52.4, 55.2)):
    nut = R[name]["data"]["mate"]
    p0, p1 = seq.poses(start), seq.poses(end)
    relative_advance = (p0[name][2] - p1[name][2]) + (p1[nut][2] - p0[nut][2])
    turns = -(p1[name][3] - p0[name][3]) / (2 * math.pi)
    chk(name + "_thread_pitch", abs(relative_advance - turns * MAN["pitch"]) < 1e-5)
chk("press_OFF", press_at(62) == 0)
chk("press_contact", press_at(65) == 1 and press_at(77) == 1)
chk("press_release", press_at(70) == 0 and press_at(83) == 0)

payload = dict(duration=DURATION, fps=FPS, names=seq.names, origins=origins, manifest=MAN,
               stages=STAGES, frames=frames, press=[round(press_at(f / FPS), 7) for f in range(len(frames))])
(ROOT / "web" / "sequence.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

for material_name, spans in {
    "grey": [(15, 17.5), (52.4, 55.5)],
    "violet": [(34.2, 39.5), (52.4, 55.5)],
    "blue": [(34.2, 39.5)],
}.items():
    alpha = M[material_name].node_tree.nodes["Principled BSDF"].inputs["Alpha"]
    alpha.default_value = 1
    alpha.keyframe_insert("default_value", frame=1)
    for a, b in spans:
        for t, val in ((a - .2, 1), (a, .32), (b, .32), (b + .2, 1)):
            alpha.default_value = val
            alpha.keyframe_insert("default_value", frame=round(t * FPS) + 1)

# An explicit push marker, not a force vector or a calculated input.
bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0, radius2=.3, depth=.5, location=(0, 0, 0))
arrow = bpy.context.object
arrow.name = "Finger_push_marker"
arrow.data.materials.append(M["arrow"])
for t in (0, 61, 62, 63, 63.8, 67, 67.8, 70, 71, 73, 74, 74.8, 79, 79.8, 83, 84):
    a = math.radians(-60 if t < 71 else 108)
    arrow.location = (4 * math.cos(a), 4 * math.sin(a), (29 - MAN["delta"] * press_at(t)) * MM)
    arrow.hide_render = not (62 <= t < 70 or 73 <= t < 83)
    arrow.keyframe_insert("location", frame=round(t * FPS) + 1)
    arrow.keyframe_insert("hide_render", frame=round(t * FPS) + 1)

# Each stage has its own camera/HUD, avoiding label drift during camera changes.
views = [
    (-75, 48, (-116, 165, -65, 228, 0, 42)),
    (-70, 42, (-105, 78, -70, 170, 0, 85)),
    (-160, 38, (-40, 35, -35, 40, 0, 48)),
    (-70, 48, (68, 193, -60, 170, 0, 90)),
    (-70, 48, (65, 195, -60, 65, 0, 85)),
    (-70, 50, (65, 195, -60, 65, 0, 42)),
    (-70, 40, (-65, 195, -65, 65, 0, 72)),
    (-70, 40, (-62, 62, -60, 65, 0, 100)),
    (-60, 38, (-62, 62, -62, 62, 0, 44)),
    (-60, 25, (-62, 62, -62, 62, 0, 44)),
    (108, 16, (-55, 55, -55, 55, 0, 44)),
    (-60, 38, (-62, 62, -62, 62, 0, 44)),
]
shots = [(i, s, views[i]) for i, s in enumerate(STAGES)]
shots.append((12, (52.4, *STAGES[7][1:]), (-60, 32, (-62, 62, -62, 62, 0, 44))))
shots.sort(key=lambda item: item[1][0])
for j, (i, (start, counter, title, sub), view) in enumerate(shots):
    sc.camera = None
    az, el, bb = view
    cam = still_cam(sc, az, el, box_pts(*bb), region=(150, 195, 1770, 990))
    cam.name = "Camera_" + str(i)
    before = set(bpy.data.objects)
    header(sc, cam, M, counter + "  " + title, sub,
           "組立の見える化（物理シミュレーションではありません）／未印刷・未購入・実物未検証")
    hud = set(bpy.data.objects) - before
    end = shots[j + 1][1][0] if j + 1 < len(shots) else DURATION + 1
    for o in hud:
        for t, hidden in ((0, True), (start, False), (end, True)):
            o.hide_render = hidden
            o.keyframe_insert("hide_render", frame=round(t * FPS) + 1)
    marker = sc.timeline_markers.new(counter, frame=round(start * FPS) + 1)
    marker.camera = cam
    check_texts(sc, cam, "stage_" + str(i))

sc.frame_set(1)
sc.camera = bpy.data.objects["Camera_0"]
sc.render.filepath = str(OUT / "frames" / "f_")
sc["scope"] = "Prescribed assembly visualisation, NOT dynamics or manufacturing qualification"
sc["units"] = "1 BU = 10 mm"
sc["viewer_shared_sequence"] = "web/sequence.json"
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "brake-teaching-model-v2.blend"))
report = dict(n_checks=len(CHECKS), n_failed=sum(not x["ok"] for x in CHECKS), checks=CHECKS)
(ROOT / "results" / "animation-validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
print("ANIMATION CHECKS", report["n_checks"], "FAILED", report["n_failed"])
if report["n_failed"]:
    raise RuntimeError([c for c in CHECKS if not c["ok"]])
if "--stills" in sys.argv:
    (OUT / "stills-assembly").mkdir(exist_ok=True)
    for t in (0, 9.6, 16.3, 24.9, 28.5, 39.5, 45, 55.5, 60.5, 65, 77, 85):
        sc.frame_set(round(t * FPS) + 1)
        sc.render.filepath = str(OUT / "stills-assembly" / ("t_%05.1f.png" % t))
        bpy.ops.render.render(write_still=True)
