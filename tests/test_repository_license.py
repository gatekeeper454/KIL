import hashlib
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
APACHE_HEADER = "Apache License\n                           Version 2.0, January 2004"
APACHE_2_0_SHA256 = "168a1be0d9bf454ebd8098bec7760a503f9c9ee7b94a049d689c455347f90c32"
KTP_CITATION_URL = "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"


class RepositoryLicenseTest(unittest.TestCase):
    def test_root_license_contains_apache_2_0_text(self):
        license_bytes = (ROOT / "LICENSE").read_bytes()
        license_text = license_bytes.decode("utf-8")

        self.assertIn(APACHE_HEADER, license_text)
        self.assertIn("TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION", license_text)
        self.assertIn("9. Accepting Warranty or Additional Liability.", license_text)
        self.assertEqual(hashlib.sha256(license_bytes).hexdigest(), APACHE_2_0_SHA256)

    def test_notice_declares_license_and_preserves_attribution(self):
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")

        self.assertIn("original KIL material is licensed under the Apache License 2.0", notice)
        self.assertIn(KTP_CITATION_URL, notice)
        self.assertIn("byte-preserved", notice)
        self.assertNotIn("no license is granted", notice)

    def test_package_metadata_points_to_the_root_license(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(metadata["project"]["license"], {"file": "LICENSE"})

    def test_readme_has_apache_2_0_license_section(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## License", readme)
        self.assertIn(
            "Original KIL material is licensed under the Apache License 2.0.",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
