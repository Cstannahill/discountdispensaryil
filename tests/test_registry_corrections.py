"""A corrected map point survives a registry import; the registry's own address is untouched."""
import tempfile
import unittest
from pathlib import Path

from backend import storage
from backend.domain import digest
from backend.storage import Store
from test_storage import observation


class CoordinateCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.db', Path(self.tmp.name) / 'evidence')
        self.saved = storage.CORRECTED_COORDINATES
        self.store_id = digest(['illinois-map', 'shop'])[:24]

    def tearDown(self):
        storage.CORRECTED_COORDINATES = self.saved
        self.tmp.cleanup()

    def test_a_registry_import_restores_the_corrected_map_point(self):
        storage.CORRECTED_COORDINATES = {self.store_id: (40.13379, -87.552129, 'test')}
        self.db.import_registry([observation()], 'source')
        with self.db.connection() as conn:
            row = conn.execute('SELECT name, address, latitude, longitude FROM live_stores WHERE id=?', (self.store_id,)).fetchone()
        self.assertEqual(('Test Shop', '100 Main St', 40.13379, -87.552129), tuple(row))


if __name__ == '__main__':
    unittest.main()
