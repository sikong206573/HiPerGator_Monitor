import sys
from pathlib import Path
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
from collect import make_snapshot, parse_slurm_info, parse_pending_queue, update_history  # noqa: E402


class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = (ROOT / "collector/example_slurm_info.txt").read_text()
        cls.queue = (ROOT / "collector/example_queue.txt").read_text()

    def test_parse_allocation_and_usage(self):
        data = parse_slurm_info(self.info, "qi855292.ucf")
        self.assertEqual(data["investment"]["cpu_total"], 64)
        self.assertEqual(data["investment"]["memory_total_gb"], 500)
        self.assertEqual(data["investment"]["cpu_running"], 56)
        self.assertEqual(data["investment"]["memory_running_gb"], 456)
        self.assertEqual(data["burst"]["cpu_running"], 12)

    def test_reject_unknown_allocation(self):
        with self.assertRaises(ValueError):
            parse_slurm_info(self.info, "someone-else")

    def test_reasons_are_aggregated(self):
        queue = parse_pending_queue(self.queue)
        self.assertEqual(queue["pending_total"], 7)
        self.assertEqual(queue["reasons"][0], {"reason": "QOSGrpMemLimit", "count": 4})
        self.assertNotIn("USER", str(queue))

    def test_snapshot_and_history(self):
        at = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(self.info, self.queue, "qi855292.ucf", at=at)
        history = update_history(ROOT / "tests/does_not_exist.json", snapshot)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["cpu_utilization_pct"], 87.5)
        self.assertEqual(snapshot["collected_at"], "2026-11-02T16:00:00Z")


if __name__ == "__main__":
    unittest.main()
