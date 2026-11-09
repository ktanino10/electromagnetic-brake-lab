"""Verify repository-relative delivery hashes, plates, media and local links."""
import argparse
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote
import zipfile
from png_metadata import private_text_fields

ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "validation"
EXCLUDED = {"node_modules", "__pycache__", ".git"}
EDITED = {
    "model-v2/GUIDE.txt", "model-v2/brake-viewer-v2.html",
    "model-v2/blender/brake-teaching-model-v2.blend",
    "model-v2/scripts/package_delivery.py", "model-v2/scripts/v2bl_common.py",
    "model-v2/web/index.html", "model-v2/web/viewer.html",
    "model-v2/web/package.json", "model-v2/web/test.mjs", "model-v2/web/test-media.mjs",
    "print-prep/START-HERE.txt", "print-prep/build_plates.py", "print-prep/geometry-checks.json",
}
MEDIA = {
    "model-v2/brake-assembly-v2.mp4": 88,
    "videos/pico-brake-mechanism-explainer.mp4": 92,
    "videos/pico-brake-four-angles.mp4": 40,
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def record_sources(args):
    records = {}
    for source, destination in ((args.source_model, ROOT / "model-v2"),
                                (args.source_prep, ROOT / "print-prep")):
        require(source is not None, "Both approved source directories are required")
        for target in sorted(destination.rglob("*")):
            if not target.is_file() or any(part in EXCLUDED for part in target.parts):
                continue
            if destination.name == "model-v2" and target.parent.name == "results" and target.name not in {
                    "assembly-manifest.json", "print-model-v2-validation.json"}:
                continue
            original = source / target.relative_to(destination)
            if original.is_file():
                rel = target.relative_to(ROOT).as_posix()
                source_sha = sha(original)
                if rel not in EDITED:
                    require(source_sha == sha(target), f"Copied input differs: {rel}")
                records[rel] = {"source_sha256": source_sha,
                                "repository_sha256": sha(target),
                                "byte_identical": source_sha == sha(target)}
    for original, rel in ((args.source_explainer, "videos/pico-brake-mechanism-explainer.mp4"),
                          (args.source_multiview, "videos/pico-brake-four-angles.mp4")):
        require(original is not None, "Approved source video paths are required")
        require(sha(original) == sha(ROOT / rel), f"Video differs: {rel}")
        records[rel] = {"source_sha256": sha(original), "repository_sha256": sha(ROOT / rel),
                        "byte_identical": True}
    (VALIDATION / "input-hashes.json").write_text(json.dumps(records, indent=2) + "\n")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for key, value in attrs if key in ("href", "src") and value)


def check_links():
    checks = 0
    for path in (ROOT / "README.md", ROOT / "index.html", ROOT / "videos/watch.html",
                 ROOT / "model-v2/brake-viewer-v2.html", ROOT / "model-v2/watch-assembly.html",
                 ROOT / "model-v2/web/viewer.html"):
        if path.suffix == ".md":
            urls = re.findall(r"\]\(([^)]+)\)", path.read_text())
        else:
            parser = Links()
            parser.feed(path.read_text())
            urls = parser.urls
        for url in urls:
            if url.startswith(("data:", "#")):
                continue
            if url.startswith(("https://github.com/ktanino10/electromagnetic-brake-lab",
                               "https://ktanino10.github.io/electromagnetic-brake-lab/")):
                continue
            require("://" not in url, f"Unexpected external HTML link: {path.name}")
            target = (path.parent / unquote(url.split("#")[0])).resolve()
            require(target.is_relative_to(ROOT) and target.exists(),
                    f"Broken local link: {path.relative_to(ROOT)} -> {url}")
            checks += 1
    return checks


def check_public_content():
    flags = (b"/Users/", b"session-state", b"github_pat_", b"ghp_",
             b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----")
    checked = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix == ".log" or path.parent == ROOT / "validation":
            continue
        if path.suffix == ".png":
            require(not private_text_fields(path.read_bytes(), flags),
                    f"Private PNG text metadata: {path.relative_to(ROOT)}")
            checked += 1
        elif path.suffix in {".zip", ".FCStd", ".3mf"}:
            with zipfile.ZipFile(path) as archive:
                require(archive.testzip() is None, f"Archive CRC failure: {path.name}")
                for name in archive.namelist():
                    data = archive.read(name)
                    require(not any(flag in data for flag in flags), f"Private marker: {path.name}/{name}")
                    if name.lower().endswith(".png"):
                        require(not private_text_fields(data, flags),
                                f"Private PNG text metadata: {path.name}/{name}")
                checked += len(archive.namelist())
        elif path.suffix in {".py", ".mjs", ".js", ".html", ".txt", ".md", ".json", ".step", ".svg"}:
            # This validator necessarily contains marker literals, not private values.
            if path == Path(__file__).resolve():
                continue
            require(not any(flag in path.read_bytes() for flag in flags),
                    f"Private marker: {path.relative_to(ROOT)}")
            checked += 1
    return checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-sources", action="store_true")
    parser.add_argument("--source-model", type=Path)
    parser.add_argument("--source-prep", type=Path)
    parser.add_argument("--source-explainer", type=Path)
    parser.add_argument("--source-multiview", type=Path)
    args = parser.parse_args()
    VALIDATION.mkdir(exist_ok=True)
    if args.record_sources:
        record_sources(args)
    inputs = json.loads((VALIDATION / "input-hashes.json").read_text())
    require(inputs, "No input hashes recorded")
    remediation_path = VALIDATION / "png-metadata-remediation.json"
    remediated = (json.loads(remediation_path.read_text())["files"]
                  if remediation_path.exists() else {})
    for rel, record in inputs.items():
        # The validator evolves independently; its historical source hash remains in the audit record.
        if ROOT / rel == Path(__file__).resolve():
            continue
        expected = record["repository_sha256"]
        if rel in remediated:
            change = remediated[rel]
            require(change["before_sha256"] == expected and change["decoded_pixels_identical"]
                    and change["nontext_chunks_identical"], f"Invalid PNG remediation: {rel}")
            expected = change["after_sha256"]
        require(sha(ROOT / rel) == expected, f"Input changed: {rel}")
        if rel not in EDITED:
            require(record["byte_identical"], f"Unexpected modification: {rel}")
    for rel in MEDIA:
        require(inputs[rel]["byte_identical"], f"Video changed: {rel}")
    require(len(list((ROOT / "model-v2/stl/print").glob("*.stl"))) == 6, "Expected six print STLs")
    require(len(list((ROOT / "model-v2/blender/stills-holes").glob("*.png"))) == 5, "Expected five hole diagrams")
    spec = importlib.util.spec_from_file_location("plates", ROOT / "print-prep/build_plates.py")
    plates = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plates)
    source = ROOT / "model-v2/stl/print"
    meshes = [plates.read_stl(source / name) for name in plates.PARTS]
    plate_checks = [plates.verify_plate(ROOT / "print-prep" / f"{name}.3mf", placements, meshes)
                    for name, placements in plates.PLATES.items()]
    probe = shutil.which("ffprobe")
    decoder = shutil.which("ffmpeg")
    require(probe and decoder, "Install ffprobe/ffmpeg to validate media")
    media = []
    for rel, duration in MEDIA.items():
        info = json.loads(subprocess.check_output(
            [probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(ROOT / rel)]))
        require(abs(float(info["format"]["duration"]) - duration) < .1, f"Video duration: {rel}")
        videos = [stream for stream in info["streams"] if stream["codec_type"] == "video"]
        require(len(videos) == 1, f"Expected one video stream: {rel}")
        subprocess.run([decoder, "-v", "error", "-xerror", "-i", str(ROOT / rel),
                        "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL)
        media.append({"file": rel, "duration_seconds": duration,
                      "dimensions": [videos[0]["width"], videos[0]["height"]],
                      "audio_streams": sum(s["codec_type"] == "audio" for s in info["streams"]),
                      "full_decode": True})
    native = json.loads((VALIDATION / "blender-portability.json").read_text())
    require(native["geometry_and_animation_unchanged"], "Blender geometry changed")
    require(native["repository_sha256"] == sha(ROOT / "model-v2/blender/brake-teaching-model-v2.blend"),
            "Blender differs from sanitized scene")
    report = {"status": "PASS", "scope": "Digital relocation and geometry only; not slicing or physical validation",
              "input_files": len(inputs),
              "byte_identical_inputs": sum(sha(ROOT / rel) == record["source_sha256"]
                                           for rel, record in inputs.items()),
              "local_links_checked": check_links(), "public_content_members_checked": check_public_content(),
              "plates": plate_checks, "videos": media, "sliced": False,
              "printed": False, "physically_tested": False, "printer_connected": False}
    report_name = "delivery-checks-after-png-remediation.json" if remediated else "delivery-checks.json"
    (VALIDATION / report_name).write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: {len(inputs)} input hashes, 2 geometry plates, 3 decoded videos, local links and content scan")


if __name__ == "__main__":
    main()
