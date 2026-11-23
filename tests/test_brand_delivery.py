import json
from pathlib import Path
import sys
import unittest

from tmp_dirs import tmp_dir

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _common import brand_look
from deliver import kit_projection


class BrandDelivery(unittest.TestCase):
    def test_shared_composition_look_and_projected_delivery(self):
        root = tmp_dir(self, "rfs-kit-").resolve()
        (root / "font.ttf").touch()
        kit = root / "kit.json"
        data = {"schema": "velisa/kit@1", "name": "Example", "colours": {"primary": "FFD200", "secondary": "EEEEEE"},
                "font_file": "font.ttf", "logo": "logo.png", "styles": {"caption": {"colour": "FFFFFF", "unused": 1}}}
        kit.write_text(json.dumps(data))
        original = kit.read_bytes()
        projection = kit_projection(kit)
        projected = root / "delivery.json"
        projected.write_text(json.dumps(projection))
        self.assertEqual(projection, {"colors": {"primary": "FFD200"}, "logo": str(root / "logo.png"),
                                      "font_file": str(root / "font.ttf"), "styles": {"caption": {"colour": "FFFFFF"}}})
        self.assertEqual(brand_look(kit), brand_look(projected))
        self.assertEqual(kit.read_bytes(), original)

    def test_british_fixture_has_no_injected_defaults(self):
        fixture = Path(__file__).parent / "fixtures" / "colours-british-spelling.json"
        self.assertEqual(kit_projection(fixture), {"colors": {"primary": "FFD200", "text": "FFFFFF"}, "font": "Noto Sans"})
