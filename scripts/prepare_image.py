#!/usr/bin/env python3
"""Prepare a catalog illustration from a square PNG, JPEG, or WebP source."""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from PIL import UnidentifiedImageError

from validate_catalog import ID_PATTERN


ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = ROOT / "images"
MAX_OUTPUT_BYTES = 100 * 1024
MIN_QUALITY = 40
QUALITY_STEP = 5
SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}


class PrepareError(Exception):
    pass


def fail(message: str) -> None:
    raise PrepareError(message)


def load_source(source_path: Path) -> tuple[Image.Image, tuple[int, int], str]:
    if not source_path.is_file():
        fail(f"source file does not exist: {source_path}")
    try:
        with Image.open(source_path) as source:
            source_format = source.format
            if source_format not in SUPPORTED_FORMATS:
                fail(f"unsupported source format: {source_format or 'unknown'}")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            oriented.load()
            image = oriented.copy()
    except (OSError, SyntaxError, UnidentifiedImageError) as exc:
        fail(f"source is not a decodable image: {exc}")
    return image, image.size, source_format


def convert_for_webp(image: Image.Image) -> Image.Image:
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")


def encode_candidates(image: Image.Image) -> tuple[bytes, int]:
    final_image = convert_for_webp(image)
    resized = final_image.resize((256, 256), Image.Resampling.LANCZOS)
    for quality in range(95, MIN_QUALITY - 1, -QUALITY_STEP):
        output = io.BytesIO()
        resized.save(output, format="WEBP", quality=quality, method=6)
        encoded = output.getvalue()
        if len(encoded) <= MAX_OUTPUT_BYTES:
            return encoded, quality
    fail(
        "could not produce a WebP at or below 100 KiB while keeping quality "
        f"at or above {MIN_QUALITY}"
    )


def write_atomically(destination: Path, data: bytes, *, force: bool) -> None:
    if destination.exists() and not force:
        fail(f"destination already exists: {destination} (use --force to replace it)")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{destination.stem}.", suffix=".tmp", dir=destination.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    except OSError as exc:
        fail(f"could not write {destination}: {exc}")
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a square PNG, JPEG, or WebP source as a catalog WebP illustration."
    )
    parser.add_argument("source", type=Path, help="source PNG, JPEG, or WebP file")
    parser.add_argument("id", help="catalog game id in lowercase kebab-case")
    parser.add_argument("--force", action="store_true", help="replace an existing images/<id>.webp")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if not ID_PATTERN.fullmatch(args.id):
            fail("id must use lowercase kebab-case ASCII")
        source = args.source.expanduser().resolve()
        image, source_dimensions, _ = load_source(source)
        if source_dimensions[0] != source_dimensions[1]:
            fail(f"source must be square, got {source_dimensions[0]}x{source_dimensions[1]}")
        if source_dimensions[0] < 256:
            fail(f"source must be at least 256x256, got {source_dimensions[0]}x{source_dimensions[1]}")
        encoded, quality = encode_candidates(image)
        destination = IMAGES_DIR / f"{args.id}.webp"
        write_atomically(destination, encoded, force=args.force)
    except PrepareError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if "image" in locals():
            image.close()
    print(f"source dimensions: {source_dimensions[0]}x{source_dimensions[1]}")
    print("final dimensions: 256x256")
    print(f"WebP quality: {quality}")
    print(f"final size: {len(encoded) / 1024:.1f} KiB ({len(encoded)} bytes)")
    print(f"output: {destination.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
