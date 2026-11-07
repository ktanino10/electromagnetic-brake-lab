"""Package unchanged print meshes as millimetre geometry-only P1S plates."""

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zipfile


MODEL_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PARTS = (
    "01_base_grey.stl",
    "02_coil_ring_orange.stl",
    "03_hub_violet.stl",
    "04_armature_blue.stl",
    "05_leaf_spring_green_print4.stl",
    "06_retaining_cap_grey.stl",
)
PLATES = {
    "01-body-PLA-candidate": [(0, 80, 80), (3, 195, 80), (1, 70, 200),
                              (2, 160, 200), (5, 210, 200)],
    "02-springs-PETG-candidate": [(4, 68, 96), (4, 128, 96),
                                 (4, 68, 116), (4, 128, 116)],
}
COLORS = ("#8b939c", "#e59636", "#9474c4", "#5596d5", "#68aa78", "#8b939c")
ET.register_namespace("", MODEL_NS)


def tag(name):
    return f"{{{MODEL_NS}}}{name}"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_stl(path):
    raw = path.read_bytes()
    require(len(raw) >= 84, f"Short STL: {path.name}")
    count = struct.unpack_from("<I", raw, 80)[0]
    require(len(raw) == 84 + 50 * count and count > 0, f"Invalid STL: {path.name}")
    vertices, triangles, lookup = [], [], {}
    for face in range(count):
        indexes = []
        for corner in range(3):
            point = struct.unpack_from("<3f", raw, 84 + 50 * face + 12 + 12 * corner)
            require(all(math.isfinite(x) for x in point), "Nonfinite vertex")
            if point not in lookup:
                lookup[point] = len(vertices)
                vertices.append(point)
            indexes.append(lookup[point])
        require(len(set(indexes)) == 3, "Degenerate indexed triangle")
        triangles.append(tuple(indexes))
    edges = Counter(tuple(sorted((face[i], face[(i + 1) % 3])))
                    for face in triangles for i in range(3))
    require(all(count == 2 for count in edges.values()), f"Open mesh: {path.name}")
    directed = Counter((face[i], face[(i + 1) % 3])
                       for face in triangles for i in range(3))
    require(all(count == directed[(b, a)] for (a, b), count in directed.items()),
            f"Inconsistent winding: {path.name}")
    bounds = [[min(point[k] for point in vertices) for k in range(3)],
              [max(point[k] for point in vertices) for k in range(3)]]
    require(abs(bounds[0][2]) < 1e-6, f"Print mesh is not flat on Z=0: {path.name}")
    return {"vertices": vertices, "triangles": triangles, "bounds": bounds,
            "sha256": hashlib.sha256(raw).hexdigest(), "raw": raw}


def write_zip(path, contents):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, f"Damaged ZIP: {path.name}")


def make_plate(path, placements, meshes):
    model = ET.Element(tag("model"), unit="millimeter",
                       attrib={"{http://www.w3.org/XML/1998/namespace}lang": "en-US"})
    ET.SubElement(model, tag("metadata"), name="Title").text = path.stem
    ET.SubElement(model, tag("metadata"), name="Description").text = (
        "Geometry and placement only; no printer/filament/process settings or G-code. "
        "Unsliced hand-operated nonmagnetic teaching model. Read START-HERE.txt."
    )
    resources = ET.SubElement(model, tag("resources"))
    for index in sorted({p[0] for p in placements}):
        item = ET.SubElement(resources, tag("object"), id=str(index + 1),
                             type="model", name=PARTS[index].removesuffix(".stl"))
        mesh = ET.SubElement(item, tag("mesh"))
        vertices = ET.SubElement(mesh, tag("vertices"))
        triangles = ET.SubElement(mesh, tag("triangles"))
        for point in meshes[index]["vertices"]:
            ET.SubElement(vertices, tag("vertex"), **dict(zip("xyz", map(repr, point))))
        for face in meshes[index]["triangles"]:
            ET.SubElement(triangles, tag("triangle"),
                          **dict(zip(("v1", "v2", "v3"), map(str, face))))
    build = ET.SubElement(model, tag("build"))
    for index, x, y in placements:
        ET.SubElement(build, tag("item"), objectid=str(index + 1),
                      transform=f"1 0 0 0 1 0 0 0 1 {x} {y} 0")
    write_zip(path, {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
            '</Types>'
        ).encode(),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
            '</Relationships>'
        ).encode(),
        "3D/3dmodel.model": ET.tostring(model, encoding="utf-8", xml_declaration=True),
    })


def verify_plate(path, placements, meshes, source_dir=None):
    with zipfile.ZipFile(path) as archive:
        require(len(archive.namelist()) == 3, "Unexpected 3MF content")
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
    require(model.attrib["unit"] == "millimeter", "Wrong units")
    objects = {int(o.attrib["id"]): o for o in model.findall(f"{tag('resources')}/{tag('object')}")}
    items = model.findall(f"{tag('build')}/{tag('item')}")
    require(len(items) == len(placements), "Wrong object count")
    records, boxes = [], []
    for item, (index, tx, ty) in zip(items, placements):
        require(int(item.attrib["objectid"]) == index + 1, "Wrong mesh instance")
        transform = list(map(float, item.attrib["transform"].split()))
        require(transform == [1, 0, 0, 0, 1, 0, 0, 0, 1, tx, ty, 0], "Wrong transform")
        mesh = objects[index + 1].find(tag("mesh"))
        vertices = [tuple(float(v.attrib[k]) for k in "xyz")
                    for v in mesh.find(tag("vertices"))]
        triangles = [tuple(int(t.attrib[k]) for k in ("v1", "v2", "v3"))
                     for t in mesh.find(tag("triangles"))]
        require(vertices == meshes[index]["vertices"], "Source vertex mismatch")
        require(triangles == meshes[index]["triangles"], "Source triangle mismatch")
        bounds = [[min(v[k] + (tx, ty, 0)[k] for v in vertices) for k in range(3)],
                  [max(v[k] + (tx, ty, 0)[k] for v in vertices) for k in range(3)]]
        lo, hi = bounds
        require(all(0 <= lo[k] <= hi[k] <= 256 for k in range(3)), "Outside P1S volume")
        require(lo[0] >= 18 or lo[1] >= 28, "Intersects front-left 18x28 exclusion")
        for previous in boxes:
            gap = max(lo[0] - previous[1][0], previous[0][0] - hi[0],
                      lo[1] - previous[1][1], previous[0][1] - hi[1])
            require(gap >= 5, "Part bounding boxes have less than 5 mm separation")
        boxes.append(bounds)
        source_dir = source_dir or Path(__file__).resolve().parent.parent / "model-v2/stl/print"
        source = os.path.relpath(source_dir / PARTS[index], path.parent)
        records.append({"source": Path(source).as_posix(), "translation_mm": [tx, ty, 0],
                        "bounds_mm": bounds, "triangles": len(triangles),
                        "source_sha256": meshes[index]["sha256"]})
    return {"file": path.name, "instances": records, "source_geometry_exact": True,
            "minimum_axis_aligned_box_separation_mm": 5,
            "bed_exclusion_mm": [[0, 0], [18, 28]], "sliced": False,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def preview_svg(path, placements, meshes):
    rows = ['<svg xmlns="http://www.w3.org/2000/svg" width="768" height="858" viewBox="0 0 256 286">',
            '<rect width="256" height="286" fill="#ffffff"/>',
            '<rect x="0.5" y="0.5" width="255" height="255" fill="#f3f5f7" stroke="#718096"/>',
            '<rect x="0" y="228" width="18" height="28" fill="#f3b4b4"/>']
    labels = []
    for index, tx, ty in placements:
        vertices = meshes[index]["vertices"]
        rows.append(f'<g fill="{COLORS[index]}">')
        for face in meshes[index]["triangles"]:
            p = [vertices[v] for v in face]
            area = ((p[1][0] - p[0][0]) * (p[2][1] - p[0][1])
                    - (p[1][1] - p[0][1]) * (p[2][0] - p[0][0]))
            if area > 1e-8:
                points = " ".join(f"{v[0]+tx:.5f},{256-v[1]-ty:.5f}" for v in p)
                rows.append(f'<polygon points="{points}"/>')
        rows.append("</g>")
        labels.append(f'<text x="{tx}" y="{256-ty+2}" text-anchor="middle" '
                      f'font-family="sans-serif" font-size="5" fill="#12171d">{index+1:02d}</text>')
    rows.extend(labels)
    rows.extend(['<text x="6" y="268" font-family="sans-serif" font-size="5">'
                 'P1S: 256 x 256 mm / top projection / front at bottom</text>',
                 '<text x="6" y="279" font-family="sans-serif" font-size="4.3">'
                 'Red: 18 x 28 mm exclusion. Geometry only; NOT a sliced preview.</text>',
                 '</svg>'])
    path.write_text("\n".join(rows), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Original stl/print folder")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    meshes = [read_stl(args.source / part) for part in PARTS]
    report = {"scope": "Geometry-only plate placement, not slicer/physical validation",
              "printer": "Bambu Lab P1S", "nozzle_mm_assumed_not_confirmed": 0.4,
              "slicer_installed_or_run": False, "printed": False,
              "printer_connected": False, "plates": []}
    for name, placements in PLATES.items():
        path = output / f"{name}.3mf"
        make_plate(path, placements, meshes)
        report["plates"].append(verify_plate(path, placements, meshes, args.source))
        preview_svg(output / f"{name}.svg", placements, meshes)
    for name, mesh in zip(PARTS, meshes):
        require(hashlib.sha256((args.source / name).read_bytes()).hexdigest() == mesh["sha256"],
                f"Original input changed: {name}")
    (output / "geometry-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"plates": len(report["plates"]),
                      "printed_instances_in_plates": sum(len(x["instances"]) for x in report["plates"]),
                      "unique_parts": len(PARTS), "geometry_checks": "passed",
                      "sliced": False}, indent=2))


if __name__ == "__main__":
    main()
