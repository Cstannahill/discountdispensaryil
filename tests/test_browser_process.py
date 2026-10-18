import unittest
from backend.browser_render import _close_streams


class BrowserProcessTests(unittest.TestCase):
    def test_failed_pipe_cleanup_does_not_mask_the_rendering_failure(self):
        class Stream:
            closed=False
            def close(self):
                self.closed=True
                raise OSError(22,'Invalid argument')
        streams=[Stream(),Stream(),Stream()]
        _close_streams(streams)
        self.assertTrue(all(stream.closed for stream in streams))
