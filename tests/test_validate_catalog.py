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
        (self.root / "games").mkdir()
        (self.root / "schema").mkdir()
        shutil.copy(REPOSITORY_ROOT / "schema/game.schema.json", self.root / "schema/game.schema.json")
        self.original_root = validate_catalog.ROOT
        self.original_catalog_path = validate_catalog.CATALOG_PATH
        self.original_schema_path = validate_catalog.SCHEMA_PATH
        validate_catalog.ROOT = self.root
        validate_catalog.CATALOG_PATH = self.root / "catalog.json"
        validate_catalog.SCHEMA_PATH = self.root / "schema/game.schema.json"

    def tearDown(self):
        validate_catalog.ROOT = self.original_root
        validate_catalog.CATALOG_PATH = self.original_catalog_path
        validate_catalog.SCHEMA_PATH = self.original_schema_path
        self.tempdir.cleanup()

    def write_catalog(self, index_image=None, detail_image=None, games=None):
        games = games or [
            {
                "id": "test-game",
                "name": "Test game",
                "players": {"min": 2, "max": 4},
                "path": "games/test-game.json",
            }
        ]
        if index_image is not None:
            games[0]["image"] = index_image
        detail = {
            "schemaVersion": 1,
            "id": games[0]["id"],
            "name": games[0]["name"],
            "players": games[0]["players"],
            "result": {"type": "score", "winner": "highest"},
            "rounds": {"enabled": False},
            "playMode": "individual",
            "rules": "Règle de test.",
        }
        if detail_image is not None:
            detail["image"] = detail_image
        (self.root / "games/test-game.json").write_text(json.dumps(detail), encoding="utf-8")
        (self.root / "catalog.json").write_text(
            json.dumps({
                "schemaVersion": 1,
                "catalogVersion": "test",
                "language": "fr",
                "games": games,
            }),
            encoding="utf-8",
        )

    def validate(self):
        catalog = validate_catalog.load_json(validate_catalog.CATALOG_PATH)
        schema = validate_catalog.load_json(validate_catalog.SCHEMA_PATH)
        validate_catalog.validate_catalog(catalog, schema)

    def write_webp(self, path, size=(256, 256), quality=80):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", size, (20, 40, 80))
        image.save(path, format="WEBP", quality=quality)

    def write_image(self, path, image_format, size=(256, 256)):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", size, (20, 40, 80))
        image.save(path, format=image_format)

    def assert_invalid(self):
        with self.assertRaises(validate_catalog.ValidationFailure):
            self.validate()

    def test_game_without_image_is_valid(self):
        self.write_catalog()
        self.validate()

    def test_valid_webp_and_multiple_images_are_valid(self):
        self.write_catalog("images/test-game.webp", "images/test-game.webp")
        self.write_webp(self.root / "images/test-game.webp")
        self.validate()

        second = {
            "id": "second-game",
            "name": "Second game",
            "players": {"min": 2, "max": 4},
            "path": "games/second-game.json",
            "image": "images/second-game.webp",
        }
        second_detail = {
            "schemaVersion": 1,
            "id": "second-game",
            "name": "Second game",
            "players": {"min": 2, "max": 4},
            "result": {"type": "score", "winner": "highest"},
            "rounds": {"enabled": False},
            "playMode": "individual",
            "rules": "Règle de test.",
            "image": "images/second-game.webp",
        }
        (self.root / "games/second-game.json").write_text(json.dumps(second_detail), encoding="utf-8")
        catalog = json.loads((self.root / "catalog.json").read_text(encoding="utf-8"))
        catalog["games"].append(second)
        (self.root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        self.write_webp(self.root / "images/second-game.webp")
        self.validate()

    def test_image_must_be_declared_in_both_index_and_detail(self):
        self.write_catalog(index_image="images/test-game.webp")
        self.assert_invalid()
        self.write_catalog(detail_image="images/test-game.webp")
        self.assert_invalid()

    def test_index_and_detail_image_paths_must_match(self):
        self.write_catalog("images/test-game.webp", "images/other.webp")
        self.assert_invalid()

    def test_image_name_and_extension_are_strict(self):
        for image_path in (
            "images/other.webp",
            "images/test-game.png",
            "images/test-game.jpeg",
            "images/test-game.webp?x=1",
            "images/test-game.webp#fragment",
            "images/../test-game.webp",
            "/images/test-game.webp",
            "images\\test-game.webp",
            "http://example.test/test-game.webp",
            "https://example.test/test-game.webp",
            "file:images/test-game.webp",
            "data:image/webp;base64,AAAA",
        ):
            with self.subTest(image_path=image_path):
                self.write_catalog(image_path, image_path)
                self.assert_invalid()

    def test_png_and_jpeg_bytes_are_rejected_even_with_webp_extension(self):
        for image_format in ("PNG", "JPEG"):
            with self.subTest(image_format=image_format):
                self.write_catalog("images/test-game.webp", "images/test-game.webp")
                self.write_image(self.root / "images/test-game.webp", image_format)
                self.assert_invalid()

    def test_missing_invalid_and_undecodable_images_are_rejected(self):
        self.write_catalog("images/test-game.webp", "images/test-game.webp")
        self.assert_invalid()
        image_path = self.root / "images/test-game.webp"
        image_path.parent.mkdir()
        image_path.write_bytes(b"not a WebP")
        self.assert_invalid()

    def test_dimensions_must_be_exactly_256_by_256(self):
        for size in ((255, 256), (256, 255), (257, 256), (256, 257)):
            with self.subTest(size=size):
                self.write_catalog("images/test-game.webp", "images/test-game.webp")
                self.write_webp(self.root / "images/test-game.webp", size=size)
                self.assert_invalid()

    def test_file_must_not_exceed_100_kib(self):
        self.write_catalog("images/test-game.webp", "images/test-game.webp")
        image_path = self.root / "images/test-game.webp"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(os.urandom(100 * 1024 + 1))
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
