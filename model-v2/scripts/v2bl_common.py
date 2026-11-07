# Shared helpers for the v2 assembly visualisation (not a physics simulation).
import bpy, bmesh, math, json, unicodedata, os
from pathlib import Path
from mathutils import Vector, Matrix, Euler
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path(__file__).resolve().parent.parent
RD = ROOT / "stl" / "render"
OUT = ROOT / "blender"
MAN = json.load(open(ROOT / "results" / "assembly-manifest.json"))
W, H, FPS = 1920, 1080, 24
MM = 0.1          # 1 Blender unit = 10 mm
O_REF = 20.0      # HUD design scale: design pixels map to BU at this ortho scale
font_override = os.environ.get("BRAKE_JAPANESE_FONT")
font_directory = Path("/System/Library/Fonts")
FONT = (Path(font_override).expanduser() if font_override else
        next((p for p in font_directory.iterdir()
              if unicodedata.normalize("NFC", p.name) == "ヒラギノ丸ゴ ProN W4.ttc"), None)
        if font_directory.is_dir() else None)
if FONT is None or not FONT.is_file():
    raise RuntimeError("Set BRAKE_JAPANESE_FONT to an available Japanese font; no fonts are bundled.")
CHECKS, KEYS, TEXTS = [], {}, []


def chk(name, ok, **kv):
    CHECKS.append(dict(name=name, ok=bool(ok), **kv))


def F(t):
    return int(round(t * FPS)) + 1


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.use_preferences_save = False
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = 32
    r = sc.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = W, H, 100
    r.fps = FPS
    sc.frame_start, sc.frame_end = 1, 88 * FPS
    r.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "Standard"
    wd = bpy.data.worlds.new("bg"); sc.world = wd; wd.use_nodes = True
    bg = wd.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.06, 0.07, 0.095, 1); bg.inputs[1].default_value = 0.7
    return sc


def material(name, color, metallic=0.0, emission=0.0, rough=0.45):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    s = m.node_tree.nodes["Principled BSDF"]
    s.inputs["Base Color"].default_value = (*color, 1)
    s.inputs["Metallic"].default_value = metallic
    s.inputs["Roughness"].default_value = rough
    s.inputs["Emission Color"].default_value = (*color, 1)
    s.inputs["Emission Strength"].default_value = emission
    m.surface_render_method = "DITHERED"
    return m


def mats():
    t = lambda n, c: material(n, c, emission=1.0)
    return dict(
        grey=material("grey_base", (0.46, 0.5, 0.56), 0.1), orange=material("orange_coil", (0.95, 0.42, 0.06), 0.1),
        violet=material("violet_hub", (0.42, 0.26, 0.72), 0.05), green=material("green_spring", (0.05, 0.78, 0.36), 0.0, 0.08),
        blue=material("blue_armature", (0.07, 0.4, 0.92), 0.05), cap=material("cap_light", (0.78, 0.8, 0.84), 0.05),
        metal=material("hardware_steel", (0.72, 0.74, 0.78), 0.7, 0.0, 0.3),
        table=material("table", (0.11, 0.12, 0.14), 0.0, 0.0, 0.85),
        arrow=material("arrow", (1.0, 0.55, 0.12), emission=0.6),
        white=t("t_white", (0.93, 0.95, 1.0)), dim=t("t_dim", (0.62, 0.7, 0.82)), tgreen=t("t_green", (0.25, 0.95, 0.55)),
        tblue=t("t_blue", (0.4, 0.68, 1.0)), tviolet=t("t_violet", (0.78, 0.64, 1.0)), torange=t("t_orange", (1.0, 0.62, 0.28)),
        tgrey=t("t_grey", (0.8, 0.84, 0.9)), tsteel=t("t_steel", (0.86, 0.88, 0.92)),
        badge=material("t_badge", (0.03, 0.035, 0.05), emission=1.0, rough=1.0))


def lights(sc):
    for nm, d, e, size in (("key", (1.0, -1.3, 1.6), 4.0, 3), ("fill", (-1.4, -0.4, 0.8), 1.6, 6), ("rim", (-0.3, 1.5, 1.2), 2.2, 4)):
        ld = bpy.data.lights.new(nm, "SUN"); ld.energy = e; ld.angle = math.radians(size)
        o = bpy.data.objects.new(nm, ld); sc.collection.objects.link(o)
        o.rotation_euler = Vector(d).to_track_quat("Z", "Y").to_euler()


def smooth(o, deg=30):
    o.data.shade_smooth()
    o.data.set_sharp_from_angle(angle=math.radians(deg))


def load(fn, mat, name):
    for x in bpy.context.selected_objects:
        x.select_set(False)
    bpy.ops.wm.stl_import(filepath=str(RD / fn), global_scale=MM)
    o = bpy.context.selected_objects[0]; o.name = name
    # Blender 5 keeps the import scale on the object; bake it so mesh data is in BU and scale is 1.
    o.data.transform(o.matrix_basis.copy()); o.matrix_basis = Matrix.Identity(4)
    o.data.materials.clear(); o.data.materials.append(mat)
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(o.data); bm.free()
    smooth(o, 25)
    return o


def set_origin(o, org):
    """org in BU, in the current (assembled) object space."""
    o.data.transform(Matrix.Translation(-org)); o.location = org


def bbox_origin(o):
    vs = [v.co for v in o.data.vertices]
    return Vector(((min(v.x for v in vs) + max(v.x for v in vs)) / 2, (min(v.y for v in vs) + max(v.y for v in vs)) / 2,
                   min(v.z for v in vs)))


def empty(name, parent=None, size=0.4):
    o = bpy.data.objects.new(name, None); bpy.context.scene.collection.objects.link(o)
    o.empty_display_size = size; o.parent = parent
    return o


def key(target, path, frame, value, interp="BEZIER"):
    KEYS.setdefault((target.as_pointer(), path), [target, path, {}])[2][frame] = (value, interp)


def flush_keys():
    pref = bpy.context.preferences.edit
    old = pref.keyframe_new_interpolation_type
    n = 0
    for tgt, path, d in KEYS.values():
        for fr in sorted(d):
            val, it = d[fr]
            pref.keyframe_new_interpolation_type = it
            setattr(tgt, path, val)
            tgt.keyframe_insert(path, frame=fr); n += 1
    pref.keyframe_new_interpolation_type = old
    KEYS.clear()
    return n


def show(o, spans):
    """spans: list of (t0, t1) seconds during which the object renders."""
    key(o, "hide_render", 1, True)
    for t0, t1 in spans:
        key(o, "hide_render", F(t0), False)
        key(o, "hide_render", F(t1), True)


# ---------- camera rig ----------
def rot_of(az, el):
    return Euler((math.radians(90 - el), 0, math.radians(az + 90)))


def fit_state(pts, az, el, region=(40, 175, 1880, 1010)):
    R = rot_of(az, el).to_matrix()
    rt, up, bk = R.col[0], R.col[1], R.col[2]
    xs = [p.dot(rt) for p in pts]; ys = [p.dot(up) for p in pts]; zs = [p.dot(bk) for p in pts]
    x0, y0, x1, y1 = region
    scale = max((max(xs) - min(xs)) * W / (x1 - x0), (max(ys) - min(ys)) * W / (y1 - y0))
    S = scale / W
    cx = (max(xs) + min(xs)) / 2 - ((x0 + x1) / 2 - W / 2) * S
    cy = (max(ys) + min(ys)) / 2 + ((y0 + y1) / 2 - H / 2) * S
    return dict(target=rt * cx + up * cy + bk * (sum(zs) / len(zs)), rot=rot_of(az, el), scale=scale, az=az, el=el)


def box_pts(x0, x1, y0, y1, z0, z1):
    return [Vector((x, y, z)) * MM for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def obj_pts(objs):
    bpy.context.view_layer.update()
    return [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]


def px(sc, cam, p):
    u, v, _ = world_to_camera_view(sc, cam, p)
    return u * W, (1 - v) * H


# ---------- still camera + HUD (used by the hole sheets) ----------
def still_cam(sc, az, el, pts, region=(60, 190, 1860, 1000)):
    cam = sc.camera
    if cam is None:
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
        cam.data.type = "ORTHO"; cam.data.clip_start = 0.01; cam.data.clip_end = 2000
    s = fit_state(pts, az, el, region)
    cam.rotation_euler = s["rot"]
    cam.location = s["target"] + s["rot"].to_matrix().col[2] * 300
    cam.data.ortho_scale = s["scale"]
    bpy.context.view_layer.update()
    return cam


def text(sc, cam, body, x, y, size, mat, align="LEFT"):
    S = cam.data.ortho_scale / W
    d = bpy.data.curves.new("txt", "FONT"); d.body = body; d.size = size * S
    d.font = bpy.data.fonts.load(str(FONT), check_existing=True); d.align_x = align; d.align_y = "CENTER"
    o = bpy.data.objects.new("txt", d); sc.collection.objects.link(o)
    o.parent = cam; o.location = ((x - W / 2) * S, (H / 2 - y) * S, -1)
    o.data.materials.append(mat)
    TEXTS.append(o)
    return o


def text_box(sc, cam, o):
    bpy.context.view_layer.update()
    cs = [world_to_camera_view(sc, cam, o.matrix_world @ Vector(c)) for c in o.bound_box]
    return (min(c.x for c in cs) * W, (1 - max(c.y for c in cs)) * H, max(c.x for c in cs) * W, (1 - min(c.y for c in cs)) * H)


def cam_poly(sc, cam, pts, z, mat, name):
    S = cam.data.ortho_scale / W
    me = bpy.data.meshes.new(name)
    me.from_pydata([((x - W / 2) * S, (H / 2 - y) * S, z) for x, y in pts], [], [list(range(len(pts)))]); me.update()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o.parent = cam
    o.data.materials.append(mat)
    return o


def leader(sc, cam, a, b, mat, w=1.6, dot=5.0):
    dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / n * w, dx / n * w
    cam_poly(sc, cam, [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)], -1.001, mat, "lead")
    cam_poly(sc, cam, [(b[0] + dot * math.cos(k * math.pi / 6), b[1] + dot * math.sin(k * math.pi / 6)) for k in range(12)], -1.001, mat, "dot")


def label(sc, cam, M, body, x, y, size, mat, align="LEFT", targets=(), pad=8):
    """targets: world points (Vector, BU) or pixel tuples."""
    o = text(sc, cam, body, x, y, size, mat, align)
    b = text_box(sc, cam, o)
    x0, y0, x1, y1 = b[0] - pad, b[1] - pad * 0.7, b[2] + pad, b[3] + pad * 0.7
    cam_poly(sc, cam, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], -1.002, M["badge"], "badge")
    for t in targets:
        t = px(sc, cam, t) if isinstance(t, Vector) else t
        s0 = (min(max(t[0], x0), x1), min(max(t[1], y0), y1))
        leader(sc, cam, s0, t, mat)
    return o


def header(sc, cam, M, title, sub, footer):
    cam_poly(sc, cam, [(0, 0), (W, 0), (W, 150), (0, 150)], -1.003, M["badge"], "topbar")
    cam_poly(sc, cam, [(0, 1025), (W, 1025), (W, H), (0, H)], -1.003, M["badge"], "botbar")
    text(sc, cam, title, 48, 52, 46, M["white"])
    text(sc, cam, sub, 48, 110, 28, M["dim"])
    text(sc, cam, footer, W / 2, 1052, 22, M["dim"], "CENTER")


def check_texts(sc, cam, shot):
    bpy.context.view_layer.update()
    boxes, bad = [], []
    for o in TEXTS:
        b = text_box(sc, cam, o)
        if not (b[0] >= 8 and b[1] >= 8 and b[2] <= W - 8 and b[3] <= H - 8):
            bad.append(o.data.body[:16])
        boxes.append((o.data.body[:16], b))
    ov = [(boxes[i][0], boxes[j][0]) for i in range(len(boxes)) for j in range(i + 1, len(boxes))
          if boxes[i][1][0] < boxes[j][1][2] and boxes[j][1][0] < boxes[i][1][2]
          and boxes[i][1][1] < boxes[j][1][3] and boxes[j][1][1] < boxes[i][1][3]]
    chk(shot + "_texts_in_frame", not bad, out=bad)
    chk(shot + "_texts_no_overlap", not ov, overlaps=ov)
    TEXTS.clear()


def objs_in_frame(sc, cam, objs, shot, margin=0.0):
    bpy.context.view_layer.update()
    out = []
    for o in objs:
        for v in o.data.vertices:
            u = world_to_camera_view(sc, cam, o.matrix_world @ v.co)
            if not (margin <= u.x <= 1 - margin and margin <= u.y <= 1 - margin):
                out.append(o.name); break
    chk(shot + "_objects_in_frame", not out, out=out)
