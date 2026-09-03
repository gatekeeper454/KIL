from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProjectBoundaryTests(unittest.TestCase):
    def test_unrelated_project_name_is_absent_from_tracked_files(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout.split(b"\0")
        needle = ("shadow" + "claw").casefold()
        offenders: list[str] = []
        for encoded_path in tracked:
            if not encoded_path:
                continue
            relative = encoded_path.decode("utf-8")
            try:
                contents = (ROOT / relative).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if needle in contents.casefold():
                offenders.append(relative)
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
