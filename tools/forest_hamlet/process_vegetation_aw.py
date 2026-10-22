#!/usr/bin/env python3
"""Compile vegetation colors with installed AW; pair untouched linear normals.

The official world.compile workflow processes the color sprites. Independently
authored tangent-space normal images bypass palette mapping and are accepted
only when their canvas and alpha agree exactly with the official output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from PIL import Image

from process_materials_aw import installed_cli, sha


NAMES = ("broadleaf_a", "broadleaf_b", "fir", "grass", "fern", "reeds",
         "flowers_white", "flowers_pink", "window_flowers", "lily_pad")
PREVIEW_GROUND = "assets/forest-hamlet/textures/grass.png"


def dump(path: Path, document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def freeze(path: Path, document) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != document:
            raise RuntimeError(f"Frozen production input changed: {path}; use a new run ID")
    else:
        dump(path, document)


def rgba(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        if opened.format != "PNG" or opened.mode != "RGBA":
            raise RuntimeError(f"Expected an RGBA PNG: {path}")
        return opened.copy()


def alpha_digest(image: Image.Image) -> str:
    return hashlib.sha256(image.getchannel("A").tobytes()).hexdigest()


def verify_preview_ground(root: Path) -> None:
    with Image.open(root / PREVIEW_GROUND) as opened:
        preview = opened.convert("RGBA")
    if preview.size != (64, 64) or preview.getchannel("A").getextrema() != (255, 255):
        raise RuntimeError("The unused AW catalog ground requires the existing opaque 64x64 grass surface")


def verify_pair(color: Image.Image, normal: Image.Image, item: dict) -> dict:
    name = item["name"]
    size = tuple(item["size"])
    if color.size != size or normal.size != size:
        raise RuntimeError(f"{name}: color/normal canvas differs from {size}")
    alpha = color.getchannel("A")
    alpha_values = set(alpha.getdata())
    if alpha_values != {0, 255}:
        raise RuntimeError(f"{name}: expected a nonempty binary-alpha cutout with transparent margin")
    if alpha.tobytes() != normal.getchannel("A").tobytes():
        raise RuntimeError(f"{name}: normal/color alpha differs; refusing a misregistered pair")
    bbox = alpha.getbbox()
    rect = [bbox[0], bbox[1], bbox[2]-bbox[0], bbox[3]-bbox[1]]
    if item.get("visible_rect") is not None and list(item["visible_rect"]) != rect:
        raise RuntimeError(f"{name}: declared visible_rect differs from actual alpha {rect}")
    error = 0.0
    minimum_z = 1.0
    vectors = set()
    for r, g, b, a in normal.getdata():
        if not a:
            continue
        x, y, z = r / 127.5 - 1.0, g / 127.5 - 1.0, b / 127.5 - 1.0
        length = math.sqrt(x*x+y*y+z*z)
        error = max(error, abs(length-1.0))
        minimum_z = min(minimum_z, z)
        vectors.add((r, g, b))
    if error > 0.012 or minimum_z < -0.01:
        raise RuntimeError(f"{name}: invalid outward 8-bit unit normals (error {error:.6f}, min Z {minimum_z:.6f})")
    if len(vectors) < 8:
        raise RuntimeError(f"{name}: normal map has insufficient nonflat directional information")
    pivot = item["pivot"]
    if len(pivot) != 2 or not (0 <= pivot[0] <= size[0] and 0 <= pivot[1] <= size[1]):
        raise RuntimeError(f"{name}: pivot lies outside the image canvas")
    height = float(item["height_m"])
    if not math.isfinite(height) or height <= 0:
        raise RuntimeError(f"{name}: height_m must be a positive visible physical height")
    return {"visible_rect": rect, "alpha_sha256": alpha_digest(color),
            "visible_pixels": sum(1 for a in alpha.getdata() if a),
            "normal_max_length_error": error, "normal_min_z": minimum_z,
            "normal_unique_vectors": len(vectors)}


def recipe_document(root: Path, recipe: Path, preparation: dict) -> dict:
    def relative(value: str) -> str:
        source = (root / value).resolve()
        source.relative_to(root)
        return Path(os.path.relpath(source, recipe.parent)).as_posix()
    verify_preview_ground(root)
    sheets = [{"id": "opaque-preview", "path": "preview-ground.png", "grid": [1, 1],
               "background": {"mode": "alpha", "color": [255, 0, 255], "tolerance": 0}}]
    assets = []
    for item in preparation["assets"]:
        name = item["name"]
        color = rgba(root / item["color"])
        bbox = color.getchannel("A").getbbox()
        width, height = bbox[2]-bbox[0], bbox[3]-bbox[1]
        # Native AW maps source_anchor onto the inclusive visible pixel lattice
        # (width-1,height-1). A root just below the final pixel is intentional.
        anchor = [(item["pivot"][0]-bbox[0])/max(1,width-1),
                  (item["pivot"][1]-bbox[1])/max(1,height-1)]
        if any(a < -0.25 or a > 1.25 for a in anchor):
            raise RuntimeError(f"{name}: structural anchor exceeds native AW's supported visible-bound range")
        sheets.append({"id": name, "path": relative(item["color"]), "grid": [1, 1],
                       "background": {"mode": "alpha", "color": [255, 0, 255], "tolerance": 0}})
        assets.append({"id": f"plant.{name}", "sheet": name, "slot": [0, 0], "kind": "prop",
                       "size": item["size"], "pivot": item["pivot"], "footprint": [1, 1],
                       "visual_scale": {"width": width, "source_anchor": anchor}})
    # Native world.compile v1 requires a ground catalog member. Its preview
    # output is unused; vegetation always uses the supported prop branch.
    assets.insert(0, {"id": "preview.ground", "sheet": "opaque-preview",
                      "slot": [0, 0], "kind": "ground", "ground_projection": "topdown_repeat",
                      "trim": [1/64, 1/64, 63/64, 63/64],
                      "size": [64, 32], "pivot": [32, 16], "footprint": [1, 1]})
    processing = {"palette_size": int(preparation.get("palette_size", 128)),
                  "alpha_threshold": 128, "require_visual_scale": True}
    palette = preparation.get("palette")
    if palette:
        processing["palette_file"] = relative(palette["path"])
    return {"schema_version": 1, "id": "forest.hamlet." + recipe.parent.name.replace("-", "."), "sheets": sheets, "assets": assets,
            "map": {"width": 1, "height": 1, "default_ground": "preview.ground", "cells": [], "instances": []},
            "processing": processing,
            "production_notes": {"intended_output": "Ten camera-facing HD2D vegetation color cutouts",
                                 "normal_policy": "Normal images bypass this color-only workflow; pair validation rejects any alpha or canvas change",
                                 "source_geometry": "Prepared cutout canvas and visible dimensions are preserved exactly",
                                 "discarded_preview": "Native catalog-required ground uses the existing opaque 64x64 grass surface; its compiled preview is never used in the game",
                                 "review_status": "pending"}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--run-id", default="forest-hamlet-20261022-vegetation-r1")
    parser.add_argument("--preparation", default="art/inputs/forest-hamlet/vegetation-r1/preparation.json")
    parser.add_argument("--config", default="art/inputs/forest-hamlet/workbench-project.yaml")
    parser.add_argument("--recipe", help="Explicit native AW recipe path; create it if absent, preserve it if present; default vegetation.recipe.yaml beside preparation")
    args = parser.parse_args()
    if not args.run_id or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in args.run_id):
        raise ValueError("run-id must be a lowercase safe directory name")
    root = args.project.resolve()
    preparation_path = root / args.preparation
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    if preparation.get("schema_version") != 1:
        raise RuntimeError("Preparation must use schema_version 1")
    if sorted(item["name"] for item in preparation["assets"]) != sorted(NAMES):
        raise RuntimeError("Preparation must contain exactly the ten named vegetation assets")
    checked = {}
    for item in preparation["assets"]:
        for field in ("color", "normal"):
            (root / item[field]).resolve().relative_to(root)
        checked[item["name"]] = verify_pair(rgba(root / item["color"]), rgba(root / item["normal"]), item)
    config = root / args.config
    recipe = root / args.recipe if args.recipe else preparation_path.parent / "vegetation.recipe.yaml"
    verify_preview_ground(root)
    # Native AW deliberately confines sheets to the recipe directory. Retain an
    # exact source copy there; both identities are part of the frozen closure.
    preview_copy = recipe.parent / "preview-ground.png"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    if preview_copy.exists():
        if sha(preview_copy) != sha(root / PREVIEW_GROUND):
            raise RuntimeError("Frozen opaque preview source changed; use a new input directory")
    else:
        shutil.copyfile(root / PREVIEW_GROUND, preview_copy)
    if not args.recipe or not recipe.exists():
        # JSON is a YAML subset accepted by the native scene-sheet v1 loader.
        freeze(recipe, recipe_document(root, recipe, preparation))
    source_files = list(dict.fromkeys([*preparation.get("source_files", []), PREVIEW_GROUND,
                                      preview_copy.relative_to(root).as_posix()]))
    for path in source_files:
        (root / path).resolve().relative_to(root)
        if not (root / path).is_file():
            raise FileNotFoundError(path)
    run = root / "art/derived/workbench/world" / args.run_id
    evidence = root / "art/derived/forest-hamlet" / args.run_id
    evidence.mkdir(parents=True, exist_ok=True)
    inputs = [preparation_path, config, recipe] + [root / x[field] for x in preparation["assets"] for field in ("color", "normal")]
    inputs += [root / path for path in source_files]
    palette = preparation.get("palette")
    if palette:
        inputs.append(root / palette["path"])
    freeze(evidence / "vegetation-frozen-inputs.json", {
        "schema_version": 1, "run_id": args.run_id,
        "inputs": [{"path": path.relative_to(root).as_posix(), "sha256": sha(path)} for path in inputs],
        "driver_sha256": sha(Path(__file__)), "normal_convention": "OpenGL tangent +X right, +Y up, +Z outward"})
    cli = [installed_cli("aw"), "--project", str(root), "--project-config", str(config)]

    def execute(label: str, command: list[str]) -> None:
        freeze(evidence / f"{label}.command.json", command)
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=300)
        (evidence / f"{label}.stdout.json").write_text(result.stdout, encoding="utf-8")
        (evidence / f"{label}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode:
            print(result.stdout)
            print(result.stderr)
            raise RuntimeError(f"{label} failed with exit {result.returncode}; native evidence retained")

    if run.exists():
        execute("aw-resume", cli + ["workflow", "resume", "--run", str(run), "--json"])
    else:
        execute("aw-validate", cli + ["workflow", "validate", "world.compile", "--input", str(recipe), "--json"])
        execute("aw-run", cli + ["workflow", "run", "world.compile", "--input", str(recipe),
                                 "--output", str(run), "--bypass-rectify", "--json"])
    record = json.loads((run / "run.json").read_text(encoding="utf-8"))
    if record.get("status") != "completed" or record.get("workflow") != "world.compile":
        raise RuntimeError("The official AW run is not a completed world.compile run")
    palette_colors = None
    if palette:
        document = json.loads((root / palette["path"]).read_text(encoding="utf-8"))
        if document.get("schema_version") != 1:
            raise RuntimeError("Frozen palette must use schema_version 1")
        palette_colors = {tuple(int(color[i:i+2], 16) for i in (1, 3, 5)) for color in document["colors"]}
    # Verify every pair before changing the runtime set, so an AW alignment or
    # palette failure cannot leave half the species updated.
    ready = []
    for item in preparation["assets"]:
        name = item["name"]
        candidates = [p for p in run.rglob(f"plant.{name}.png") if p.parent.name == "images" and "steps" in p.parts]
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one official compiled image for {name}; got {candidates}")
        compiled = candidates[0]
        image = rgba(compiled)
        normal = rgba(root / item["normal"])
        metrics = verify_pair(image, normal, item)
        if metrics["alpha_sha256"] != checked[name]["alpha_sha256"]:
            raise RuntimeError(f"{name}: native AW compilation changed the source cutout alignment")
        colors = {(r, g, b) for r, g, b, a in image.getdata() if a}
        if palette_colors is not None and not colors <= palette_colors:
            raise RuntimeError(f"{name}: native output contains colors outside the frozen palette")
        ready.append((item, compiled, metrics, len(colors)))
    target_dir = root / "assets/forest-hamlet/vegetation"
    target_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    runtime = []
    for item, compiled, metrics, color_count in ready:
        name = item["name"]
        color_target = target_dir / f"{name}.png"
        normal_target = target_dir / f"{name}_normal.png"
        shutil.copyfile(compiled, color_target)
        shutil.copyfile(root / item["normal"], normal_target)
        outputs.append({"name": name, "size": item["size"], "pivot": item["pivot"],
                        "height_m": item["height_m"], "source": compiled.relative_to(root).as_posix(),
                        "runtime": color_target.relative_to(root).as_posix(), "sha256": sha(color_target),
                        "normal_source": item["normal"], "normal_runtime": normal_target.relative_to(root).as_posix(),
                        "normal_sha256": sha(normal_target), "color_palette_colors": color_count,
                        "paired_alpha_equal": True, **metrics})
        runtime.append({"id": name, "color": color_target.name, "normal": normal_target.name,
                        "size_px": item["size"], "pivot_px": item["pivot"], "visible_rect_px": metrics["visible_rect"],
                        "height_m": item["height_m"], "wind_weight": item.get("wind_weight", 1.0),
                        "color_sha256": sha(color_target), "normal_sha256": sha(normal_target),
                        "alpha_sha256": metrics["alpha_sha256"]})
    manifest_path = target_dir / "manifest.json"
    dump(manifest_path, {"schema": 1, "normal_convention": "OpenGL", "assets": runtime})
    summary = {"schema_version": 1, "workflow": "world.compile", "execution_status": "completed",
               "aw_run": (run / "run.json").relative_to(root).as_posix(), "aw_run_sha256": sha(run / "run.json"),
               "producer_version": record.get("producer_version"), "implementation": record.get("implementation"),
               "recipe": recipe.relative_to(root).as_posix(), "preparation": preparation_path.relative_to(root).as_posix(),
               "source_files": source_files, "palette": palette,
               "preview_ground": {"source": PREVIEW_GROUND, "sha256": sha(root / PREVIEW_GROUND),
                                  "native_sheet": preview_copy.relative_to(root).as_posix(),
                                  "role": "opaque native catalog input only; compiled preview not used at runtime"},
               "runtime_manifest": manifest_path.relative_to(root).as_posix(), "runtime_manifest_sha256": sha(manifest_path),
               "normal_workflow": preparation.get("normal_workflow", "independently authored geometric relief; not diffuse luminance"),
               "normal_convention": "OpenGL tangent +X right, +Y up, +Z outward",
               "outputs": outputs, "human_aesthetic_approval": "pending", "native_godot_validation": "separate_scene_evidence",
               "note": "AW officially compiled the ten color PNGs. Normals are independently authored, unchanged linear vector PNGs; dimensions and alpha are checked against the official outputs before pairing. The required catalog preview ground is unused."}
    summary_path = evidence / "vegetation-summary.json"
    dump(summary_path, summary)
    dump(target_dir.parent / "vegetation-production.json", {"run_id": args.run_id,
         "summary": summary_path.relative_to(root).as_posix(), "asset_count": len(outputs)})
    print(json.dumps({"status": "completed", "summary": summary_path.relative_to(root).as_posix(),
                      "assets": len(outputs), "paired_images": len(outputs)*2}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
