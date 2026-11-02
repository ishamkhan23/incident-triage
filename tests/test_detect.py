"""Run with: python -m unittest discover tests"""
import os
import subprocess
import sys
import tempfile
import unittest

from triage import detect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestDetect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.log = os.path.join(cls.tmp, "app.log")
        subprocess.run([sys.executable, os.path.join(ROOT, "generate_logs.py"),
                        "--out", cls.log], check=True, capture_output=True)
        cls.incidents, cls.stats = detect.detect(cls.log)

    def kinds(self):
        return sorted((i.kind, i.code) for i in self.incidents)

    def test_finds_all_planted_incidents(self):
        self.assertEqual(self.kinds(), [
            ("error_spike", "E_DB_POOL"),
            ("job_failed", "E_DATA_MISMATCH"),
            ("job_failed", "E_FILE_MISSING"),
            ("job_stuck", "STUCK_JOB"),
        ])

    def test_background_errors_are_not_spikes(self):
        spikes = [i for i in self.incidents if i.kind == "error_spike"]
        self.assertEqual(len(spikes), 1)
        self.assertEqual(spikes[0].service, "trade-capture")

    def test_parses_every_line(self):
        self.assertEqual(self.stats["lines"], self.stats["parsed"])

    def test_bad_line_is_skipped(self):
        self.assertIsNone(detect.parse_line("garbage that is not a log line"))


if __name__ == "__main__":
    unittest.main()
