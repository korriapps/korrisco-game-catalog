#!/usr/bin/env python3
"""Validate the public KorriSco V2 catalog without requiring Flutter."""

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
SCHEMA_PATH = ROOT / "schema" / "catalog.schema.json"
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


def _derived_capabilities(definition: dict) -> set[str]:
    """Mirror only the small capability derivation table of RuleDefinition.

    Flutter remains authoritative for semantic rule validation. This check is
    deliberately limited to the published capability names and their direct
    structural triggers.
    """
    capabilities: set[str] = set()
    counters = definition.get("counters", [])
    actions = definition.get("actions", [])
    transitions = definition.get("transitions", [])
    if counters:
        capabilities.add("counter.v1")
    if actions:
        capabilities.add("action.v1")
    operation_types = {
        operation.get("type")
        for action in actions
        for operation in action.get("operations", [])
    }
    for operation_type, capability in (
        ("add", "action.counter.add.v1"),
        ("subtract", "action.counter.subtract.v1"),
        ("set", "action.counter.set.v1"),
    ):
        if operation_type in operation_types:
            capabilities.add(capability)
    if "eliminate" in operation_types:
        capabilities.update({"elimination.v1", "operation.participant.eliminate.v1"})
    if definition.get("targets"):
        capabilities.add("target.v1")
    outcome_type = (definition.get("outcome") or {}).get("type")
    if outcome_type == "targetReached":
        capabilities.add("outcome.targetReached.v1")
    elif outcome_type == "lastActive":
        capabilities.add("outcome.lastActive.v1")
    if transitions:
        capabilities.add("transition.v1")
        condition_types = {
            transition.get("condition", {}).get("type") for transition in transitions
        }
        if "counter" in condition_types:
            capabilities.add("condition.counter.v1")
        if "actionParameter" in condition_types:
            capabilities.add("condition.actionIntegerParameter.v1")
        if any(
            operation.get("type") == "eliminate"
            for transition in transitions
            for operation in transition.get("operations", [])
        ):
            capabilities.update({"elimination.v1", "operation.participant.eliminate.v1"})
    if any(counter.get("scope") == "global" for counter in counters):
        capabilities.add("counter.global.v1")
    if any(
        parameter.get("type") == "integer"
        and (parameter.get("minValue") is not None or parameter.get("maxValue") is not None)
        for action in actions
        for parameter in action.get("parameters", [])
    ):
        capabilities.add("action.integerBounds.v1")
    if definition.get("ranking") is not None:
        capabilities.add("ranking.v1")
    return capabilities


def validate_catalog(catalog: dict, schema: dict) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(catalog), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "<root>"
        fail("catalog.json", f"schema error at {location}: {error.message}")

    ids: set[str] = set()
    paths: set[str] = set()
    referenced_game_paths: set[Path] = set()
    referenced_image_paths: set[Path] = set()
    games = catalog["games"]
    for index, entry in enumerate(games):
        entry_path = f"catalog.json.games[{index}]"
        game_id = entry["id"]
        if not ID_PATTERN.fullmatch(game_id):
            fail(f"{entry_path}.id", "must match lowercase kebab-case")
        if game_id in ids:
            fail(f"{entry_path}.id", f"duplicate id {game_id}")
        ids.add(game_id)
        path = entry["path"]
        if path in paths:
            fail(f"{entry_path}.path", f"duplicate path {path}")
        paths.add(path)
        detail_path = validate_relative_path(path, field=f"{entry_path}.path", prefix="games/")
        if path != f"games/{game_id}.json":
            fail(f"{entry_path}.path", f"must equal games/{game_id}.json")
        detail = load_json(detail_path)
        referenced_game_paths.add(detail_path.resolve())
        validate_game_detail(detail, schema, entry, entry_path, detail_path)
        players = entry["players"]
        if players.get("max") is not None and players["max"] < players["min"]:
            fail(f"{entry_path}.players", "max must be greater than or equal to min")

        if "image" in entry:
            referenced_image_paths.add(
                validate_image(entry["image"], game_id=game_id, field=f"{entry_path}.image")
            )

    games_directory = ROOT / "games"
    if games_directory.is_dir():
        for orphan in sorted(games_directory.glob("*.json")):
            if orphan.resolve() not in referenced_game_paths:
                fail(str(orphan.relative_to(ROOT)), "orphan game definition is not referenced by catalog.json")

    for orphan in sorted((ROOT / "images").glob("*.webp")) if (ROOT / "images").is_dir() else []:
        if orphan.resolve() not in referenced_image_paths:
            fail(str(orphan.relative_to(ROOT)), "orphan WebP image is not referenced by catalog.json")


def validate_game_detail(
    detail: dict,
    schema: dict,
    entry: dict,
    entry_path: str,
    detail_path: Path,
) -> None:
    detail_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/gameDetail",
    }
    errors = sorted(
        Draft202012Validator(detail_schema).iter_errors(detail),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "<root>"
        fail(f"{detail_path.relative_to(ROOT)}", f"schema error at {location}: {error.message}")

    relative = str(detail_path.relative_to(ROOT))
    if detail["id"] != entry["id"]:
        fail(relative, f"id {detail['id']!r} does not match index id {entry['id']!r}")
    for key in ("name", "players", "playMode", "requiredCapabilities", "minimumAge", "icon", "image"):
        if entry.get(key) != detail.get(key):
            fail(
                relative,
                f"{key} does not match catalog index: index={entry.get(key)!r}, detail={detail.get(key)!r}",
            )
    players = detail["players"]
    if players.get("max") is not None and players["max"] < players["min"]:
        fail(f"{relative}.players", "max must be greater than or equal to min")
    capabilities = set(detail["requiredCapabilities"])
    rules = detail["gameRules"]
    if rules["type"] == "standard":
        if capabilities:
            fail(f"{relative}.requiredCapabilities", "standard games must declare an empty array")
    else:
        definition = rules["definition"]
        if "ranking" in definition and definition["schemaVersion"] != 6:
            fail(
                f"{relative}.gameRules.definition.ranking",
                "ranking requires declarative definition schemaVersion 6",
            )
        ranking = definition.get("ranking")
        if ranking is not None:
            source = ranking["source"]
            counter_id = source["counterId"]
            counters = {counter["id"]: counter for counter in definition["counters"]}
            counter = counters.get(counter_id)
            if counter is None:
                fail(
                    f"{relative}.gameRules.definition.ranking.source.counterId",
                    f"unknown participant counter {counter_id!r}",
                )
            if counter["scope"] != "participant":
                fail(
                    f"{relative}.gameRules.definition.ranking.source.counterId",
                    "ranking source must reference a participant counter",
                )
        derived = _derived_capabilities(definition)
        if capabilities != derived:
            fail(
                f"{relative}.requiredCapabilities",
                f"must match derived capabilities; expected {sorted(derived)}, got {sorted(capabilities)}",
            )
    if "image" in detail:
        validate_image(detail["image"], game_id=detail["id"], field=f"{relative}.image")


def main() -> int:
    try:
        catalog = load_json(CATALOG_PATH)
        schema = load_json(SCHEMA_PATH)
        if not isinstance(catalog, dict):
            fail("catalog.json", "root must be an object")
        if not isinstance(schema, dict):
            fail("schema/catalog.schema.json", "root must be an object")
        validate_catalog(catalog, schema)
    except ValidationFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Catalog validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
