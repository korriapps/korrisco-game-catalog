import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
import validate_catalog  # noqa: E402


class CatalogValidationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "schema").mkdir()
        shutil.copy(REPOSITORY_ROOT / "schema/catalog.schema.json", self.root / "schema/catalog.schema.json")
        self.original_root = validate_catalog.ROOT
        self.original_catalog_path = validate_catalog.CATALOG_PATH
        self.original_schema_path = validate_catalog.SCHEMA_PATH
        validate_catalog.ROOT = self.root
        validate_catalog.CATALOG_PATH = self.root / "catalog.json"
        validate_catalog.SCHEMA_PATH = self.root / "schema/catalog.schema.json"

    def tearDown(self):
        validate_catalog.ROOT = self.original_root
        validate_catalog.CATALOG_PATH = self.original_catalog_path
        validate_catalog.SCHEMA_PATH = self.original_schema_path
        self.tempdir.cleanup()

    def standard_entry(self, **overrides):
        entry = {
            "id": "test-game",
            "name": "Test game",
            "players": {"min": 2, "max": 4},
            "playMode": "individual",
            "requiredCapabilities": [],
            "gameRules": {
                "type": "standard",
                "scoring": {"type": "points", "inputMode": "scalar"},
                "victory": {"type": "ranking", "direction": "highest", "tiePolicy": "shared"},
            },
            "rules": "Règle de test.",
        }
        entry.update(overrides)
        return entry

    def write_catalog(self, entries=None):
        entries = entries or [self.standard_entry()]
        index_entries = []
        games_root = self.root / "games"
        games_root.mkdir(exist_ok=True)
        for entry in entries:
            detail = {"schemaVersion": 2, **entry}
            game_path = games_root / f"{entry['id']}.json"
            game_path.write_text(json.dumps(detail), encoding="utf-8")
            index_entries.append({
                key: entry[key]
                for key in (
                    "id", "name", "players", "playMode", "requiredCapabilities",
                    "icon", "image", "minimumAge",
                )
                if key in entry
            } | {"path": f"games/{entry['id']}.json"})
        catalog = {
            "schemaVersion": 2,
            "catalogVersion": "test",
            "language": "fr",
            "games": index_entries,
        }
        (self.root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    def validate(self):
        catalog = validate_catalog.load_json(validate_catalog.CATALOG_PATH)
        schema = validate_catalog.load_json(validate_catalog.SCHEMA_PATH)
        validate_catalog.validate_catalog(catalog, schema)

    def write_webp(self, path, size=(256, 256), quality=80):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (20, 40, 80)).save(path, format="WEBP", quality=quality)

    def assert_invalid(self):
        with self.assertRaises(validate_catalog.ValidationFailure):
            self.validate()

    def test_valid_v2_standard_catalog(self):
        self.write_catalog()
        self.validate()

    def test_published_games_preserve_migrated_v1_behavior(self):
        catalog = json.loads((REPOSITORY_ROOT / "catalog.json").read_text(encoding="utf-8"))
        games = {
            entry["id"]: json.loads(
                (REPOSITORY_ROOT / entry["path"]).read_text(encoding="utf-8")
            )
            for entry in catalog["games"]
        }
        self.assertEqual(set(games), {
            "defi-des-manches", "relais-chronometre", "scrabble", "echecs", "petanque",
        })
        self.assertEqual(games["defi-des-manches"]["players"], {"min": 2, "max": 8})
        self.assertEqual(games["defi-des-manches"]["gameRules"]["progression"]["count"], 5)
        self.assertEqual(games["relais-chronometre"]["playMode"], "teams")
        self.assertEqual(games["relais-chronometre"]["gameRules"]["victory"]["direction"], "shortest")
        self.assertEqual(games["scrabble"]["minimumAge"], 10)
        self.assertIsNone(games["scrabble"]["gameRules"]["progression"]["count"])
        self.assertEqual(games["echecs"]["players"], {"min": 2, "max": 2})
        self.assertEqual(games["echecs"]["gameRules"]["scoring"]["type"], "winLoss")
        self.assertFalse(games["echecs"]["gameRules"]["victory"]["allowMultiple"])

    def test_valid_v2_declarative_catalog(self):
        definition = {
            "schemaVersion": 5,
            "counters": [{"id": "points", "initialValue": 0, "scope": "participant"}],
            "actions": [{
                "id": "addPoints",
                "parameters": [
                    {"id": "participant", "type": "participant"},
                    {"id": "points", "type": "integer", "minValue": 1, "maxValue": 6},
                ],
                "operations": [{
                    "type": "add", "counter": "points",
                    "value": {"type": "parameter", "parameter": "points"},
                    "participantParameter": "participant",
                }],
            }],
            "targets": [{"id": "thirteen", "counter": "points", "comparison": "atLeast", "value": 13}],
            "transitions": [],
            "outcome": {"type": "targetReached", "target": "thirteen"},
        }
        entry = {
            "id": "declarative-game",
            "name": "Declarative game",
            "players": {"min": 2, "max": 2},
            "playMode": "teams",
            "requiredCapabilities": [
                "counter.v1", "action.v1", "action.counter.add.v1", "target.v1",
                "outcome.targetReached.v1", "action.integerBounds.v1",
            ],
            "gameRules": {"type": "declarative", "definition": definition},
        }
        self.write_catalog([entry])
        self.validate()

    def test_valid_v6_ranking_declarative_catalog(self):
        definition = {
            "schemaVersion": 6,
            "counters": [{"id": "points", "initialValue": 0, "scope": "participant"}],
            "actions": [], "targets": [], "transitions": [],
            "ranking": {
                "source": {"type": "participantCounter", "counterId": "points"},
                "direction": "descending", "tiePolicy": "competition",
                "eliminatedPolicy": "include",
            },
        }
        entry = {
            "id": "ranking-game", "name": "Ranking game", "players": {"min": 2},
            "playMode": "individual", "requiredCapabilities": ["counter.v1", "ranking.v1"],
            "gameRules": {"type": "declarative", "definition": definition},
        }
        self.write_catalog([entry])
        self.validate()

    def test_ranking_requires_existing_participant_counter(self):
        definition = {
            "schemaVersion": 6, "counters": [], "actions": [], "targets": [],
            "transitions": [], "ranking": {
                "source": {"type": "participantCounter", "counterId": "missing"},
                "direction": "descending", "tiePolicy": "competition", "eliminatedPolicy": "include",
            },
        }
        self.write_catalog([{
            "id": "ranking-game", "name": "Ranking", "players": {"min": 2},
            "playMode": "individual", "requiredCapabilities": ["ranking.v1"],
            "gameRules": {"type": "declarative", "definition": definition},
        }])
        self.assert_invalid()

    def test_ranking_rejects_global_counter(self):
        definition = {
            "schemaVersion": 6,
            "counters": [{"id": "total", "initialValue": 0, "scope": "global"}],
            "actions": [], "targets": [], "transitions": [],
            "ranking": {
                "source": {"type": "participantCounter", "counterId": "total"},
                "direction": "descending", "tiePolicy": "competition", "eliminatedPolicy": "include",
            },
        }
        self.write_catalog([{
            "id": "ranking-game", "name": "Ranking", "players": {"min": 2},
            "playMode": "individual", "requiredCapabilities": ["counter.global.v1", "ranking.v1"],
            "gameRules": {"type": "declarative", "definition": definition},
        }])
        self.assert_invalid()

    def test_ranking_requires_schema_v6_and_capability(self):
        definition = {
            "schemaVersion": 6,
            "counters": [{"id": "score", "initialValue": 0, "scope": "participant"}],
            "actions": [], "targets": [], "transitions": [],
            "ranking": {
                "source": {"type": "participantCounter", "counterId": "score"},
                "direction": "descending", "tiePolicy": "competition", "eliminatedPolicy": "include",
            },
        }
        self.write_catalog([{
            "id": "ranking-game", "name": "Ranking", "players": {"min": 2},
            "playMode": "individual", "requiredCapabilities": ["counter.v1"],
            "gameRules": {"type": "declarative", "definition": definition},
        }])
        self.assert_invalid()
        definition["schemaVersion"] = 5
        self.write_catalog([{
            "id": "ranking-game", "name": "Ranking", "players": {"min": 2},
            "playMode": "individual", "requiredCapabilities": ["counter.v1", "ranking.v1"],
            "gameRules": {"type": "declarative", "definition": definition},
        }])
        self.assert_invalid()

    def test_ranking_enum_values_are_strict(self):
        definition = {
            "schemaVersion": 6,
            "counters": [{"id": "score", "initialValue": 0, "scope": "participant"}],
            "actions": [], "targets": [], "transitions": [],
            "ranking": {
                "source": {"type": "participantCounter", "counterId": "score"},
                "direction": "highest", "tiePolicy": "shared", "eliminatedPolicy": "keep",
            },
        }
        self.write_catalog([{
            "id": "ranking-game", "name": "Ranking", "players": {"min": 2},
            "playMode": "individual", "requiredCapabilities": ["counter.v1", "ranking.v1"],
            "gameRules": {"type": "declarative", "definition": definition},
        }])
        self.assert_invalid()

    def test_image_is_optional_and_valid_image_is_accepted(self):
        entry = self.standard_entry(image="images/test-game.webp")
        self.write_catalog([entry])
        self.write_webp(self.root / "images/test-game.webp")
        self.validate()

    def test_schema_version_must_be_two(self):
        self.write_catalog()
        catalog = json.loads((self.root / "catalog.json").read_text())
        catalog["schemaVersion"] = 1
        (self.root / "catalog.json").write_text(json.dumps(catalog))
        self.assert_invalid()

    def test_duplicate_ids_are_rejected(self):
        self.write_catalog([self.standard_entry(), self.standard_entry()])
        self.assert_invalid()

    def test_index_requires_a_referenced_detail(self):
        self.write_catalog()
        (self.root / "games/test-game.json").unlink()
        self.assert_invalid()

    def test_orphan_game_detail_is_rejected(self):
        self.write_catalog()
        (self.root / "games/orphan.json").write_text(
            json.dumps({"schemaVersion": 2, "id": "orphan"}), encoding="utf-8"
        )
        self.assert_invalid()

    def test_index_and_detail_metadata_must_match(self):
        self.write_catalog()
        detail_path = self.root / "games/test-game.json"
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        detail["playMode"] = "teams"
        detail_path.write_text(json.dumps(detail), encoding="utf-8")
        self.assert_invalid()

    def test_index_and_detail_capabilities_must_match(self):
        self.write_catalog()
        detail_path = self.root / "games/test-game.json"
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        detail["requiredCapabilities"] = ["counter.v1"]
        detail_path.write_text(json.dumps(detail), encoding="utf-8")
        self.assert_invalid()

    def test_invalid_players_are_rejected(self):
        self.write_catalog([self.standard_entry(players={"min": 4, "max": 2})])
        self.assert_invalid()

    def test_unknown_play_mode_is_rejected(self):
        self.write_catalog([self.standard_entry(playMode="pairs")])
        self.assert_invalid()

    def test_unknown_game_rules_type_is_rejected(self):
        self.write_catalog([self.standard_entry(gameRules={"type": "custom"})])
        self.assert_invalid()

    def test_standard_rules_require_empty_capabilities(self):
        self.write_catalog([self.standard_entry(requiredCapabilities=["counter.v1"])])
        self.assert_invalid()

    def test_declarative_capabilities_must_match_definition(self):
        self.write_catalog([{
            "id": "declarative-game", "name": "Declarative", "players": {"min": 1},
            "playMode": "individual", "requiredCapabilities": ["counter.v1", "action.v1"],
            "gameRules": {"type": "declarative", "definition": {
                "schemaVersion": 5, "counters": [{"id": "score", "initialValue": 0, "scope": "participant"}],
                "actions": [], "targets": [], "transitions": [],
            }},
        }])
        self.assert_invalid()

    def test_image_must_exist_and_match_game_id(self):
        self.write_catalog([self.standard_entry(image="images/other.webp")])
        self.assert_invalid()
        self.write_catalog([self.standard_entry(image="images/test-game.webp")])
        self.assert_invalid()

    def test_image_must_be_webp_256_and_under_100_kib(self):
        entry = self.standard_entry(image="images/test-game.webp")
        for size in ((255, 256), (256, 255)):
            self.write_catalog([entry])
            self.write_webp(self.root / "images/test-game.webp", size=size)
            self.assert_invalid()
        self.write_catalog([entry])
        (self.root / "images").mkdir(exist_ok=True)
        (self.root / "images/test-game.webp").write_bytes(os.urandom(100 * 1024 + 1))
        self.assert_invalid()

    def test_non_webp_and_dangerous_image_paths_are_rejected(self):
        for image_path in (
            "images/test-game.png", "images/test-game.webp?x=1", "images/../test-game.webp",
            "/images/test-game.webp", "images\\test-game.webp", "https://example.test/test-game.webp",
        ):
            with self.subTest(image_path=image_path):
                self.write_catalog([self.standard_entry(image=image_path)])
                self.assert_invalid()

    def test_orphan_webp_is_rejected(self):
        self.write_catalog()
        self.write_webp(self.root / "images/orphan.webp")
        self.assert_invalid()

    def test_missing_images_directory_is_valid(self):
        self.write_catalog()
        self.validate()


if __name__ == "__main__":
    unittest.main()
