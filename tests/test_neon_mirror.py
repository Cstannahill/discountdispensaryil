import os
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

from backend import neon_mirror


class MirrorAsyncTests(unittest.TestCase):
    def run_and_wait(self):
        neon_mirror.mirror_async(str(neon_mirror.Path(neon_mirror.__file__).resolve().parent.parent / "terpscout.db"))
        for t in threading.enumerate():
            if t.name == "terpscout-neon-mirror":
                t.join(5)

    def test_scratch_database_is_never_mirrored(self):
        with mock.patch.object(neon_mirror, "mirror") as m:
            neon_mirror.mirror_async("some-test.db")
            m.assert_not_called()

    def test_noop_without_url(self):
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(neon_mirror, "database_url", side_effect=neon_mirror.MirrorError("x")), \
             mock.patch.object(neon_mirror, "mirror") as m:
            self.run_and_wait()
            m.assert_not_called()

    def test_failure_is_swallowed(self):
        with mock.patch.dict(sys.modules, {"psycopg": types.ModuleType("psycopg")}), mock.patch.object(neon_mirror, "database_url", return_value="u"), \
             mock.patch.object(neon_mirror, "mirror", side_effect=RuntimeError("boom")) as m:
            self.run_and_wait()
            self.assertTrue(m.called)

    def test_slim_drops_raw_and_keeps_fields(self):
        cols = ["id", "payload_json"]
        row = neon_mirror.slim("live_offers", ("a", '{"name":"n","raw":{"big":1}}'), cols)
        self.assertEqual(row, ("a", '{"name":"n"}'))
        self.assertEqual(neon_mirror.slim("live_stores", ("a", "b"), cols), ("a", "b"))

    def test_slim_bakes_the_product_link_before_dropping_raw(self):
        cols = ["id", "endpoint_id", "payload_json"]
        payload = '{"source_id":"p1","source_url":"https://dutchie.com/embedded-menu/ab12","raw":{}}'
        row = neon_mirror.slim("live_offers", ("a", "e1", payload), cols, {"e1": ("dutchie", "https://dutchie.com/embedded-menu/ab12", "recreational")})
        self.assertEqual(row[2], '{"source_id":"p1","source_url":"https://dutchie.com/embedded-menu/ab12/product/p1"}')


if __name__ == "__main__":
    unittest.main()
