#!/usr/bin/env python3
"""Validate the public KorriSco catalog without requiring Flutter."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from PIL import UnidentifiedImageError
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog.json"
SCHEMA_PATH = ROOT / "schema" / "game.schema.json"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ValidationFailure(Exception):
    pass


def load_json(path: Path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationFailure(f"{path.relative_to(ROOT)}: invalid JSON ({exc})") from exc


def fail(path: str, message: str) -> None:
    raise ValidationFailure(f"{path}: {message}")


def validate_relative_path(value: object, *, field: str, prefix: str) -> Path:
    if not isinstance(value, str) or not value:
        fail(field, "must be a non-empty string")
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        fail(field, "must be a relative path without URL, query string, or fragment")
    if value.startswith("/") or "\\" in value or ".." in Path(value).parts:
        fail(field, "must be a safe relative path")
    if not value.startswith(prefix):
        fail(field, f"must start with {prefix}")
    return ROOT / value


def validate_image(value: object, *, game_id: str, field: str) -> Path:
    expected = f"images/{game_id}.webp"
    image_path = validate_relative_path(value, field=field, prefix="images/")
    if value != expected:
        fail(field, f"must equal {expected}")
    if not image_path.is_file():
        fail(field, f"file does not exist: {value}")
    size = image_path.stat().st_size
    if size > 100 * 1024:
        fail(field, f"file is too large ({size} bytes; maximum is 102400)")
    try:
        with Image.open(image_path) as image:
            detected_format = image.format
            image.verify()
        with Image.open(image_path) as image:
            image.load()
            dimensions = image.size
    except (OSError, SyntaxError, UnidentifiedImageError) as exc:
        fail(field, f"file is not a decodable WebP image ({exc})")
    if detected_format != "WEBP":
        fail(field, f"file format must be WebP, detected {detected_format or 'unknown'}")
    if dimensions != (256, 256):
        fail(field, f"image dimensions must be 256x256, got {dimensions[0]}x{dimensions[1]}")
    return image_path.resolve()


def validate_catalog(catalog: dict, schema: dict) -> None:
    if catalog.get("schemaVersion") != 1:
        fail("catalog.json.schemaVersion", "must equal 1")
    if not isinstance(catalog.get("catalogVersion"), str) or not catalog["catalogVersion"].strip():
        fail("catalog.json.catalogVersion", "must be a non-empty string")
    if catalog.get("language") != "fr":
        fail("catalog.json.language", "must equal fr for V1")
    games = catalog.get("games")
    if not isinstance(games, list):
        fail("catalog.json.games", "must be an array")

    ids: set[str] = set()
    paths: set[str] = set()
    referenced_paths: set[Path] = set()
    referenced_image_paths: set[Path] = set()

    for index, entry in enumerate(games):
        entry_path = f"catalog.json.games[{index}]"
        if not isinstance(entry, dict):
            fail(entry_path, "must be an object")
        for required in ("id", "name", "players", "path"):
            if required not in entry:
                fail(entry_path, f"missing required field {required}")
        game_id = entry["id"]
        if not isinstance(game_id, str) or not ID_PATTERN.fullmatch(game_id):
            fail(f"{entry_path}.id", "must match lowercase kebab-case")
        if game_id in ids:
            fail(f"{entry_path}.id", f"duplicate id {game_id}")
        ids.add(game_id)
        if not isinstance(entry["name"], str) or not entry["name"].strip():
            fail(f"{entry_path}.name", "must be a non-empty string")
        players = entry["players"]
        if not isinstance(players, dict) or not isinstance(players.get("min"), int) or players["min"] < 1:
            fail(f"{entry_path}.players", "min must be an integer >= 1")
        maximum = players.get("max")
        if maximum is not None and (not isinstance(maximum, int) or maximum < players["min"]):
            fail(f"{entry_path}.players.max", "must be null or an integer >= min")
        path = validate_relative_path(entry["path"], field=f"{entry_path}.path", prefix="games/")
        if entry["path"] in paths:
            fail(f"{entry_path}.path", "duplicate catalog path")
        paths.add(entry["path"])
        referenced_paths.add(path.resolve())
        if not path.is_file():
            fail(f"{entry_path}.path", f"file does not exist: {entry['path']}")
        if path.name != f"{game_id}.json":
            fail(f"{entry_path}.path", "filename must be games/<id>.json")
        if "icon" in entry and (not isinstance(entry["icon"], str) or not entry["icon"].strip()):
            fail(f"{entry_path}.icon", "must be a non-empty string")
        if "minimumAge" in entry and (
            not isinstance(entry["minimumAge"], int) or entry["minimumAge"] < 0
        ):
            fail(f"{entry_path}.minimumAge", "must be an integer >= 0")
        detail = load_json(path)
        errors = sorted(Draft202012Validator(schema).iter_errors(detail), key=lambda error: list(error.path))
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.path) or "<root>"
            fail(str(path.relative_to(ROOT)), f"schema error at {location}: {error.message}")
        if detail.get("id") != game_id:
            fail(str(path.relative_to(ROOT)), f"id {detail.get('id')!r} does not match catalog id {game_id!r}")
        detail_players = detail.get("players", {})
        if detail_players.get("max") is not None and detail_players["max"] < detail_players["min"]:
            fail(str(path.relative_to(ROOT)), "players.max must be >= players.min")
        index_image = entry.get("image")
        detail_image = detail.get("image")
        if (index_image is None) != (detail_image is None):
            fail(
                f"{path.relative_to(ROOT)}.image",
                "image must be declared identically in catalog.json and the game detail",
            )
        if index_image is not None and index_image != detail_image:
            fail(
                f"{path.relative_to(ROOT)}.image",
                "image path differs between catalog.json and the game detail",
            )
        if index_image is not None:
            referenced_image_paths.add(
                validate_image(index_image, game_id=game_id, field=f"{entry_path}.image")
            )

    for orphan in sorted((ROOT / "games").glob("*.json")) if (ROOT / "games").is_dir() else []:
        if orphan.resolve() not in referenced_paths:
            fail(str(orphan.relative_to(ROOT)), "orphan game file is not referenced by catalog.json")
    for orphan in sorted((ROOT / "images").glob("*.webp")) if (ROOT / "images").is_dir() else []:
        if orphan.resolve() not in referenced_image_paths:
            fail(str(orphan.relative_to(ROOT)), "orphan WebP image is not referenced by catalog.json")


def main() -> int:
    try:
        catalog = load_json(CATALOG_PATH)
        schema = load_json(SCHEMA_PATH)
        if not isinstance(catalog, dict):
            fail("catalog.json", "root must be an object")
        if not isinstance(schema, dict):
            fail("schema/game.schema.json", "root must be an object")
        validate_catalog(catalog, schema)
    except ValidationFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Catalog validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
