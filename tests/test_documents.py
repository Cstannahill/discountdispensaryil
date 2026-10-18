import unittest
from unittest.mock import Mock
from backend.documents import read_document,access_kind,SourceAccessError
from backend.network import FetchError,FetchResult


def document(body,status=200,url='https://example.com/menu'):
    return FetchResult(url,status,body.encode(),{},'capture','2026-10-17T12:00:00Z')


class DocumentAcquisitionTests(unittest.TestCase):
    def test_http_client_403_gets_a_separate_browser_observation(self):
        fetcher=Mock();fetcher.browser_options={'enabled':True};fetcher.get.side_effect=FetchError('Public endpoint returned HTTP 403','first')
        fetcher.render.return_value=document('<h1>Public menu</h1>')
        self.assertEqual(read_document('https://example.com/menu',fetcher).evidence_id,'capture')
        fetcher.render.assert_called_once()

    def test_browser_challenge_is_session_access_failure_not_empty_inventory(self):
        fetcher=Mock();fetcher.browser_options={'enabled':True};fetcher.get.side_effect=FetchError('Public endpoint returned HTTP 403')
        fetcher.render.return_value=document('<title>Attention Required! | Cloudflare</title>',403)
        with self.assertRaisesRegex(SourceAccessError,'this acquisition session') as raised:read_document('https://example.com/menu',fetcher)
        self.assertEqual(raised.exception.evidence_id,'capture')

    def test_authorized_age_gate_uses_browser_and_disabled_browser_does_not(self):
        fetcher=Mock();fetcher.get.return_value=document('Please confirm',url='https://example.com/age-gate');fetcher.browser_options={'enabled':True,'age_confirmed':True};fetcher.render.return_value=document('Menu')
        self.assertEqual(read_document('https://example.com/menu',fetcher).body,b'Menu')
        fetcher.render.reset_mock();fetcher.browser_options={'enabled':False,'age_confirmed':True}
        self.assertEqual(access_kind(read_document('https://example.com/menu',fetcher)),'age_confirmation')
        fetcher.render.assert_not_called()


class StatusEscalationTests(unittest.TestCase):
    def test_non_exception_403_from_the_http_client_gets_one_browser_observation(self):
        fetcher=Mock();fetcher.browser_options={'enabled':True};fetcher.get.return_value=document('Forbidden',403)
        fetcher.render.return_value=document('<h1>Public menu</h1>')
        self.assertEqual(read_document('https://example.com/menu',fetcher).body,b'<h1>Public menu</h1>')
        fetcher.render.assert_called_once()

    def test_a_challenge_seen_by_the_browser_too_is_still_reported(self):
        fetcher=Mock();fetcher.browser_options={'enabled':True};fetcher.get.return_value=document('<title>Just a moment...</title>',403)
        fetcher.render.return_value=document('<title>Just a moment...</title>',403)
        with self.assertRaises(SourceAccessError):read_document('https://example.com/menu',fetcher)
        fetcher.render.assert_called_once()

    def test_disabled_browser_does_not_escalate(self):
        fetcher=Mock();fetcher.browser_options={'enabled':False};fetcher.get.return_value=document('Forbidden',403)
        with self.assertRaises(SourceAccessError):read_document('https://example.com/menu',fetcher)
        fetcher.render.assert_not_called()

    def test_age_gate_that_is_also_rendered_is_not_rendered_twice(self):
        fetcher=Mock();fetcher.browser_options={'enabled':True,'age_confirmed':True};fetcher.get.side_effect=FetchError('Public endpoint returned HTTP 403')
        fetcher.render.return_value=document('Menu')
        read_document('https://example.com/menu',fetcher)
        fetcher.render.assert_called_once()
