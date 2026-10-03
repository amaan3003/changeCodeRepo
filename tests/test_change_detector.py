"""Offline tests using real temporary Git repositories. No API credentials needed."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("detector", Path(__file__).resolve().parents[1] / "main.py")
detector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(detector)


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Detector Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.autocrlf", "false")
        (self.repo / "app.py").write_text("port = 3000\n", encoding="utf-8")
        self.first = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-m", "Test change")
        return self.git("rev-parse", "HEAD")

    def test_modified_file_and_raw_diff(self):
        (self.repo / "app.py").write_text("port = 8080\n", encoding="utf-8")
        head = self.commit()
        result = detector.detect_changes(self.repo, repository="team/demo")
        self.assertEqual(result["files"], [{"path": "app.py", "status": "modified", "file_url": f"https://github.com/team/demo/blob/{head}/app.py"}])
        self.assertEqual(result["repository_url"], "https://github.com/team/demo")
        self.assertEqual(result["commit_url"], f"https://github.com/team/demo/commit/{head}")
        self.assertEqual(result["before_sha"], self.first)
        self.assertEqual(result["after_sha"], head)
        self.assertIn("-port = 3000", result["diff"])
        self.assertIn("+port = 8080", result["diff"])

    def test_multiple_commits_in_one_push(self):
        (self.repo / "first.txt").write_text("first")
        self.commit()
        (self.repo / "second.txt").write_text("second")
        self.commit()
        result = detector.detect_changes(self.repo, before=self.first)
        self.assertEqual({f["path"] for f in result["files"]}, {"first.txt", "second.txt"})

    def test_added_deleted_and_filename_with_spaces(self):
        (self.repo / "app.py").unlink()
        (self.repo / "new file.py").write_text("new = True\n")
        self.commit()
        result = detector.detect_changes(self.repo)
        self.assertEqual(result["files"], [{"path": "app.py", "status": "deleted", "file_url": None}, {"path": "new file.py", "status": "added", "file_url": None}])

    def test_deleted_file_url_uses_previous_commit(self):
        (self.repo / "app.py").unlink()
        self.commit()
        result = detector.detect_changes(self.repo, repository="team/demo")
        self.assertEqual(result["files"][0]["file_url"], f"https://github.com/team/demo/blob/{self.first}/app.py")

    def test_file_url_encodes_spaces_and_hashes(self):
        (self.repo / "guide #1.md").write_text("Example")
        head = self.commit()
        result = detector.detect_changes(self.repo, repository="team/demo")
        self.assertEqual(result["files"][0]["file_url"], f"https://github.com/team/demo/blob/{head}/guide%20%231.md")

    def test_first_commit(self):
        result = detector.detect_changes(self.repo)
        self.assertIsNone(result["before_sha"])
        self.assertEqual(result["comparison"], "empty_tree")
        self.assertEqual(result["files"][0]["status"], "added")

    def test_new_branch_zero_baseline(self):
        result = detector.detect_changes(self.repo, before="0" * 40)
        self.assertEqual(result["comparison"], "empty_tree")
        self.assertIn("+port = 3000", result["diff"])

    def test_same_commit_has_no_changes(self):
        result = detector.detect_changes(self.repo, before=self.first, after=self.first)
        self.assertEqual(result["files"], [])
        self.assertEqual(result["diff"], "")

    def test_binary_file(self):
        (self.repo / "asset.bin").write_bytes(b"\0\x01\xff\x02")
        self.commit()
        result = detector.detect_changes(self.repo)
        self.assertEqual(result["files"][0]["path"], "asset.bin")
        self.assertIn("Binary files", result["diff"])

    def test_push_event_handoff(self):
        (self.repo / "app.py").write_text("port = 8080\n")
        head = self.commit()
        event = self.repo / "event.json"
        event.write_text(json.dumps({"before": self.first, "after": head, "ref": "refs/heads/main"}))
        output = self.repo / "result.json"
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(event), "GITHUB_REPOSITORY": "team/demo"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(detector.main(["--repo-dir", str(self.repo), "--output", str(output)]), 0)
        result = json.loads(output.read_text())
        self.assertEqual(result["repository"], "team/demo")
        self.assertEqual(result["branch"], "main")
        self.assertEqual(result["before_sha"], self.first)

    def test_missing_commit_fails(self):
        with self.assertRaises(detector.DetectionError):
            detector.detect_changes(self.repo, before="f" * 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
