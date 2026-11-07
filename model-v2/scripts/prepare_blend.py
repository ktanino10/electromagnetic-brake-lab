"""Make a copied native scene portable without changing geometry or animation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy


def content_signature():
    meshes = []
    for mesh in sorted(bpy.data.meshes, key=lambda item: item.name):
        meshes.append({
            "name": mesh.name,
            "vertices": [list(vertex.co) for vertex in mesh.vertices],
            "faces": [list(face.vertices) for face in mesh.polygons],
            "keys": [[list(vertex.co) for vertex in key.data]
                     for key in mesh.shape_keys.key_blocks] if mesh.shape_keys else [],
        })
    actions = []
    for action in sorted(bpy.data.actions, key=lambda item: item.name):
        curves = []
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        curves.append({
                            "path": curve.data_path,
                            "index": curve.array_index,
                            "keys": [[list(key.co), list(key.handle_left),
                                      list(key.handle_right), key.interpolation]
                                     for key in curve.keyframe_points],
                        })
        actions.append({"name": action.name, "curves": curves})
    return hashlib.sha256(json.dumps({"meshes": meshes, "actions": actions},
                                    sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scene", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    scene = args.scene.resolve()
    source_sha = hashlib.sha256(scene.read_bytes()).hexdigest()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.preferences.use_preferences_save = False
    bpy.ops.wm.open_mainfile(filepath=str(scene), load_ui=True)
    before = content_signature()
    changed = []
    bpy.data.use_autopack = False
    for item in bpy.data.scenes:
        # Blender saves the whole fixed-size path buffer, including bytes after NUL.
        item.render.filepath = "//" + "_" * 1000
        item.render.filepath = "//frames/f_"
        changed.append("render_output")
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == "FILE_BROWSER" and space.params:
                    space.params.directory = b"//" + b"_" * 1000
                    space.params.directory = b"//"
                    changed.append("file_browser_directory")
    builtin_font = bpy.data.curves.new("_font_placeholder", "FONT")
    builtin = builtin_font.font
    for curve in bpy.data.curves:
        if isinstance(curve, bpy.types.TextCurve):
            for field in ("font", "font_bold", "font_italic", "font_bold_italic"):
                setattr(curve, field, builtin)
    bpy.data.curves.remove(builtin_font)
    for font in list(bpy.data.fonts):
        if font.packed_file:
            raise RuntimeError("Unexpected packed font: do not redistribute")
        if font.filepath and font.filepath != "<builtin>":
            bpy.data.fonts.remove(font)
            changed.append("external_font_replaced_with_builtin_placeholder")
    for text in bpy.data.texts:
        if text.filepath:
            raise RuntimeError("Unexpected external text source")
    if any(image.packed_file for image in bpy.data.images):
        raise RuntimeError("Unexpected packed image")
    assert content_signature() == before, "Geometry or animation changed"
    bpy.ops.wm.save_as_mainfile(filepath=str(scene), compress=True)
    bpy.ops.wm.open_mainfile(filepath=str(scene), load_ui=True)
    after = content_signature()
    assert after == before, "Saved geometry or animation changed"
    report = {
        "scope": "Copied Blender native scene paths only; source scene not modified",
        "source_sha256": source_sha,
        "repository_sha256": hashlib.sha256(scene.read_bytes()).hexdigest(),
        "geometry_and_animation_sha256": after,
        "geometry_and_animation_unchanged": True,
        "changed_fields": sorted(set(changed)),
        "fonts_bundled": False,
        "font_note": "Assign a locally available Japanese font for text rendering.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: portable scene saved; geometry and authored animation unchanged")


if __name__ == "__main__":
    main()
