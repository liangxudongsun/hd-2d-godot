#!/usr/bin/env python3
"""Deterministic source preparation for the forest hamlet AW material workflow.

This is project-side input preparation, not an Asset Workbench receipt.
The original atlas is immutable. No interpolation, color generation, normal
inference or review approval is performed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps


ATLAS_SHA256 = "fea6c0c48d91eed01d0f77a181994700d2f813124b6c37a0542c1e178a450f26"
MATERIALS = {
    "grass": (0, 0, 627, 627),
    "earth": (627, 0, 1254, 627),
    "wood": (0, 627, 627, 1254),
    "stone": (627, 627, 1254, 1254),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=Path("art/inputs/forest-hamlet/material-atlas.png"))
    parser.add_argument("--output", type=Path, default=Path("art/inputs/forest-hamlet/prepared-pixel-r2"))
    parser.add_argument("--tile-size", type=int, default=64)
    parser.add_argument("--palette-colors", type=int, default=16)
    args = parser.parse_args()
    if args.tile_size not in (64, 128, 256) or not 4 <= args.palette_colors <= 64:
        raise ValueError("Use 64/128/256 tile size and 4..64 colors per material")
    side = args.tile_size
    half = side // 2
    slot = side + 8
    root = args.project.resolve()
    source = root / args.source
    output = root / args.output
    actual_hash = sha256(source)
    if actual_hash != ATLAS_SHA256:
        raise ValueError(f"Source digest mismatch: {actual_hash}")
    with Image.open(source) as opened:
        if opened.size != (1254, 1254):
            raise ValueError(f"Unexpected atlas size: {opened.size}")
        atlas = opened.convert("RGB")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    # AW's scene-sheet contract requires transparent gutters around every slot.
    sheet = Image.new("RGBA", (slot * 2, slot * 2), (0, 0, 0, 0))
    palette = []
    for index, (name, box) in enumerate(MATERIALS.items()):
        patch = atlas.crop(box).resize((half, half), Image.Resampling.NEAREST)
        tile = Image.new("RGB", (side, side))
        tile.paste(patch, (0, 0))
        tile.paste(ImageOps.mirror(patch), (half, 0))
        tile.paste(ImageOps.flip(patch), (0, half))
        tile.paste(ImageOps.flip(ImageOps.mirror(patch)), (half, half))
        if tile.crop((0, 0, 1, side)).tobytes() != tile.crop((side-1, 0, side, side)).tobytes():
            raise AssertionError("Opposite X edges do not match")
        if tile.crop((0, 0, side, 1)).tobytes() != tile.crop((0, side-1, side, side)).tobytes():
            raise AssertionError("Opposite Y edges do not match")
        dest = output / f"{name}.png"
        tile.save(dest, optimize=False, compress_level=9)
        sheet.paste(tile.convert("RGBA"), ((index % 2) * slot + 4, (index // 2) * slot + 4))
        # Choose a restrained source-color palette; AW performs the final mapping.
        # AW, not this preparation step, maps the image to this frozen palette.
        source_colors = sorted(set(patch.getdata()))
        representatives = patch.quantize(colors=args.palette_colors, method=Image.Quantize.MEDIANCUT,
                                          dither=Image.Dither.NONE).convert("RGB")
        for representative in sorted(set(representatives.getdata())):
            color = list(min(source_colors, key=lambda candidate: sum(
                (candidate[channel] - representative[channel]) ** 2 for channel in range(3))))
            if color not in palette:
                palette.append(color)
        records.append({"material": name, "path": dest.relative_to(root).as_posix(), "sha256": sha256(dest),
                        "crop_xyxy": list(box), "size": [side, side], "source_sample_size": [half, half],
                        "filter": "nearest", "seam_method": "mirrored_2x2_exact_edges",
                        "opposite_edges_equal": True, "review_status": "pending"})
    sheet_path = output / "material-sheet.png"
    sheet.save(sheet_path, optimize=False, compress_level=9)
    palette_path = output / "palette.json"
    palette_document = {"schema_version": 1,
                        "colors": ["#{:02x}{:02x}{:02x}".format(*color) for color in palette]}
    palette_path.write_text(json.dumps(palette_document, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema_version": 1, "kind": "project_source_preparation",
                "seed": None, "algorithm": "fixed_crop_nearest_mirror2x2_v2",
                "source": {"path": source.relative_to(root).as_posix(), "sha256": actual_hash, "size": [1254, 1254]},
                "sheet": {"path": sheet_path.relative_to(root).as_posix(), "sha256": sha256(sheet_path), "grid": [2, 2]},
                "palette": {"path": palette_path.relative_to(root).as_posix(), "sha256": sha256(palette_path),
                            "count": len(palette), "source_colors_only": True,
                            "selection": f"{args.palette_colors} median-cut representatives per material, snapped to nearest exact source RGB; stable first-index tie break"},
                "outputs": records,
                "limitations": ["Mirrored repetition may be visible; inspect in the assembled scene.",
                                "This record is project preparation; official AW receipts are separate.",
                                "No human aesthetic approval is implied."]}
    (output / "preparation.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"prepared": [item["path"] for item in records], "source_sha256": actual_hash}, ensure_ascii=False))


if __name__ == "__main__":
    main()
