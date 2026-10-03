import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
import prepare_image  # noqa: E402


class PrepareImageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source_dir = self.root / "sources"
        self.source_dir.mkdir()
        self.original_root = prepare_image.ROOT
        self.original_images_dir = prepare_image.IMAGES_DIR
        prepare_image.ROOT = self.root
        prepare_image.IMAGES_DIR = self.root / "images"

    def tearDown(self):
        prepare_image.ROOT = self.original_root
        prepare_image.IMAGES_DIR = self.original_images_dir
        self.tempdir.cleanup()

    def write_source(self, name="source.png", image_format="PNG", size=(512, 512), mode="RGB"):
        path = self.source_dir / name
        image = Image.new(mode, size, (20, 40, 80, 0) if mode == "RGBA" else (20, 40, 80))
        image.save(path, format=image_format)
        image.close()
        return path

    def run_prepare(self, source, game_id="test-game", force=False):
        args = [str(source), game_id]
        if force:
            args.append("--force")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = prepare_image.main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def read_output(self, game_id="test-game"):
        output = self.root / f"images/{game_id}.webp"
        with Image.open(output) as image:
            image.load()
            return output.read_bytes(), image.format, image.size, image.mode, image.getpixel((0, 0))

    def test_png_jpeg_and_webp_sources_produce_valid_output(self):
        for image_format, extension in (("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")):
            with self.subTest(image_format=image_format):
                source = self.write_source(f"source.{extension}", image_format=image_format)
                game_id = f"test-{extension}"
                result, stdout, stderr = self.run_prepare(source, game_id=game_id)
                self.assertEqual(result, 0, stderr)
                data, output_format, size, _, _ = self.read_output(game_id)
                self.assertEqual(output_format, "WEBP")
                self.assertEqual(size, (256, 256))
                self.assertLessEqual(len(data), 100 * 1024)
                self.assertIn("WebP quality:", stdout)
                self.assertIn("final size:", stdout)

    def test_non_square_source_is_rejected(self):
        source = self.write_source(size=(512, 256))
        result, _, stderr = self.run_prepare(source)
        self.assertNotEqual(result, 0)
        self.assertIn("source must be square", stderr)

    def test_source_smaller_than_256_is_rejected(self):
        source = self.write_source(size=(128, 128))
        result, _, stderr = self.run_prepare(source)
        self.assertNotEqual(result, 0)
        self.assertIn("at least 256x256", stderr)

    def test_missing_and_fake_sources_are_rejected(self):
        result, _, stderr = self.run_prepare(self.source_dir / "missing.png")
        self.assertNotEqual(result, 0)
        self.assertIn("does not exist", stderr)
        fake = self.source_dir / "fake.png"
        fake.write_bytes(b"not an image")
        result, _, stderr = self.run_prepare(fake)
        self.assertNotEqual(result, 0)
        self.assertIn("not a decodable image", stderr)

    def test_invalid_ids_are_rejected_without_writing_outside_images(self):
        source = self.write_source()
        for game_id in ("", "Scrabble", "sea salt paper", "../scrabble", "scrabble/test"):
            with self.subTest(game_id=game_id):
                result, _, stderr = self.run_prepare(source, game_id)
                self.assertNotEqual(result, 0)
                self.assertIn("lowercase kebab-case", stderr)
        self.assertFalse((self.root / "scrabble.webp").exists())

    def test_existing_destination_requires_force(self):
        source = self.write_source()
        first_result, _, first_stderr = self.run_prepare(source)
        self.assertEqual(first_result, 0, first_stderr)
        original = (self.root / "images/test-game.webp").read_bytes()
        second_result, _, second_stderr = self.run_prepare(source)
        self.assertNotEqual(second_result, 0)
        self.assertIn("already exists", second_stderr)
        self.assertEqual(original, (self.root / "images/test-game.webp").read_bytes())
        forced_result, _, forced_stderr = self.run_prepare(source, force=True)
        self.assertEqual(forced_result, 0, forced_stderr)

    def test_transparency_is_preserved(self):
        source = self.source_dir / "transparent.png"
        image = Image.new("RGBA", (512, 512), (255, 0, 0, 0))
        image.putpixel((256, 256), (255, 0, 0, 255))
        image.save(source, format="PNG")
        image.close()
        result, _, stderr = self.run_prepare(source)
        self.assertEqual(result, 0, stderr)
        _, output_format, size, mode, transparent_pixel = self.read_output()
        self.assertEqual(output_format, "WEBP")
        self.assertEqual(size, (256, 256))
        self.assertIn("A", mode)
        self.assertLess(transparent_pixel[3], 20)

    def test_source_is_not_modified_and_json_files_are_not_touched(self):
        source = self.write_source()
        source_before = source.read_bytes()
        catalog = self.root / "catalog.json"
        detail = self.root / "game.json"
        catalog.write_text("catalog", encoding="utf-8")
        detail.write_text("detail", encoding="utf-8")
        result, _, stderr = self.run_prepare(source)
        self.assertEqual(result, 0, stderr)
        self.assertEqual(source_before, source.read_bytes())
        self.assertEqual(catalog.read_text(encoding="utf-8"), "catalog")
        self.assertEqual(detail.read_text(encoding="utf-8"), "detail")


if __name__ == "__main__":
    unittest.main()
