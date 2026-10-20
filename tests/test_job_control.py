"""A queued run can be cancelled before a worker takes it; a running run is never cancelled from the API."""
import tempfile
import unittest
from pathlib import Path

from backend.storage import Store


class JobControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')

    def tearDown(self):
        self.tmp.cleanup()

    def test_cancel_marks_a_queued_run_cancelled(self):
        job = self.db.enqueue(dict(discover=False))
        self.assertTrue(self.db.cancel_job(job['id']))
        self.assertEqual('cancelled', self.db.job(job['id'])['status'])

    def test_cancel_leaves_a_running_run_alone(self):
        job = self.db.enqueue(dict(discover=False))
        self.db.update_job(job['id'], 'running')
        self.assertFalse(self.db.cancel_job(job['id']))
        self.assertEqual('running', self.db.job(job['id'])['status'])

    def test_scheduler_setting_defaults_to_enabled(self):
        self.assertTrue(self.db.setting('scheduler_enabled', True))


if __name__ == '__main__':
    unittest.main()
