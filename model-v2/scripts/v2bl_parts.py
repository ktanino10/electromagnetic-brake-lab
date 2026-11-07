# Part loading, origins and visual threads for the v2 teaching model (appearance only).
import math
import bmesh
from mathutils import Vector
from v2bl_common import MAN, MM, load, set_origin, bbox_origin, smooth, chk

R = MAN["render"]
COLOR = dict(base="grey", coil="orange", cap="cap", hub="violet", armature="blue")


def mat_for(name, M):
    if name.startswith("spring"):
        return M["green"]
    if name.split("_")[0] in ("screw", "washer", "nut"):
        return M["metal"]
    return M[COLOR[name]]


def hw_origin(ent):
    d = ent.get("data")
    if ent["kind"].startswith("screw"):
        return Vector((d["xy"][0], d["xy"][1], d["z_bearing"])) * MM
    if ent["kind"] in ("washer_M3", "nut_M3"):
        return Vector((d["xy"][0], d["xy"][1], d["z0"])) * MM
    return None


def _shank(bm, length, top=0.3, seg=48, half=None):
    """Right-hand M3 thread, local frame: axis = Z, z = 0 at the head bearing face (BU)."""
    p = MAN["pitch"]; rmaj = MAN["shcs"]["d"] / 2; depth = 0.27
    z_top, z_tip = top, -length
    n = int(round((z_top - z_tip) / (p / 10)))
    rings = []
    for k in range(n + 1):
        z = z_top - (z_top - z_tip) * k / n
        ring = []
        for j in range(seg):
            th = 2 * math.pi * j / seg
            ph = (z / p - th / (2 * math.pi)) % 1.0
            r = min(rmaj - depth * 2 * min(ph, 1 - ph), 1.1 + (z - z_tip))
            ring.append(bm.verts.new((r * math.cos(th) * MM, r * math.sin(th) * MM, z * MM)))
        rings.append(ring)
    faces = []
    for k in range(n):
        a, b = rings[k], rings[k + 1]
        for j in range(seg):
            faces.append(bm.faces.new((a[j], b[j], b[(j + 1) % seg], a[(j + 1) % seg])))
    ct = bm.verts.new((0, 0, z_top * MM)); cb = bm.verts.new((0, 0, z_tip * MM))
    for j in range(seg):
        faces.append(bm.faces.new((ct, rings[0][j], rings[0][(j + 1) % seg])))
        faces.append(bm.faces.new((cb, rings[n][(j + 1) % seg], rings[n][j])))
    for f in faces:
        f.smooth = True
    return faces


def _cut_head(bm):
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0.002 * MM), plane_no=(0, 0, 1), clear_inner=True)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)


def thread_screw(o, length, keep_normals=()):
    """Replace the CAD shank with a visual helical thread. keep_normals: list of in-plane normals n
    (local XY); for each, a shank copy is kept on the side n.v <= 0 (union = section look)."""
    bm = bmesh.new(); bm.from_mesh(o.data)
    _cut_head(bm)
    if not keep_normals:
        _shank(bm, length)
    for n in keep_normals:
        tmp = bmesh.new()
        _shank(tmp, length)
        g = tmp.verts[:] + tmp.edges[:] + tmp.faces[:]
        bmesh.ops.bisect_plane(tmp, geom=g, plane_co=(0, 0, 0), plane_no=(n[0], n[1], 0), clear_outer=True)
        bmesh.ops.holes_fill(tmp, edges=[e for e in tmp.edges if e.is_boundary], sides=0)
        me = o.data.copy(); tmp.to_mesh(me); tmp.free()
        bm.from_mesh(me)
        import bpy
        bpy.data.meshes.remove(me)
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    smooth(o, 30)          # flat cut faces and crisp thread crests after the bmesh edit
    return o


def section_normals(name):
    """Outward normals (pointing into the removed wedge) of the cut planes through this screw axis."""
    a0, a1 = [math.radians(a) for a in MAN["section_deg"]]
    n0 = (-math.sin(a0), math.cos(a0))     # wedge is CCW of plane a0
    n1 = (math.sin(a1), -math.cos(a1))     # wedge is CW of plane a1
    xy = R[name]["data"]["xy"]
    out = []
    for a, n in ((a0, n0), (a1, n1)):
        dist = -xy[0] * math.sin(a) + xy[1] * math.cos(a)
        along = xy[0] * math.cos(a) + xy[1] * math.sin(a)
        if abs(dist) < 1e-6 and along >= -1e-6:
            out.append(n)
    return out


def load_all(M, names=None, section=True, threads=True):
    """Return dict name -> full object and name -> section object (or None). Same origins for both."""
    full, sec = {}, {}
    for name, ent in R.items():
        if names and name not in names:
            continue
        o = load(ent["off"], mat_for(name, M), name)
        org = hw_origin(ent)
        if ent["kind"] in ("washer_M3", "nut_M3"):
            zmin = min(v.co.z for v in o.data.vertices) / MM
            chk("mesh_zmin_eq_z0_" + name, abs(zmin - ent["data"]["z0"]) < 1e-3, zmin=round(zmin, 4))
        if org is None:
            org = bbox_origin(o)
        set_origin(o, org)
        if threads and ent["kind"].startswith("screw"):
            thread_screw(o, ent["data"]["length"])
        full[name] = o
        sec[name] = None
        if section and ent.get("section"):
            s = load(ent["section"], mat_for(name, M), name + "_sec")
            set_origin(s, org)
            if threads and ent["kind"].startswith("screw"):
                ns = section_normals(name)
                thread_screw(s, ent["data"]["length"], ns)
                chk("section_screw_planes_" + name, True, n_planes=len(ns))
            sec[name] = s
    return full, sec


def place(o, loc_mm=None, rot_deg=None):
    if loc_mm is not None:
        o.location = Vector(loc_mm) * MM
    if rot_deg is not None:
        o.rotation_euler = [math.radians(a) for a in rot_deg]
