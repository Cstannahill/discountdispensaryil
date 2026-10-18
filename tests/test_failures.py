import unittest
from backend.failures import FailureCode, classify, next_action, agent_eligible, ACTIONS


class FailureClassificationTests(unittest.TestCase):
    def check(self, message, code, **context):
        self.assertIs(classify(message, **context), code, message)

    def test_audit_messages_map_to_codes(self):
        cases = {
            'No retailer locator connector configured for this brand': FailureCode.NO_LEAD,
            'Public website search found no corroborated candidate; inspect search attempts': FailureCode.NO_LEAD,
            'No corroborated public menu endpoint was found': FailureCode.NO_LEAD,
            'Retailer requires age/terms confirmation; menu not fetched': FailureCode.GATE_AGE_TERMS,
            'Provider found; license-specific menu context not corroborated': FailureCode.GATE_LICENSE,
            'Menu identity has no corroborated matching address': FailureCode.LEAD_UNVERIFIED,
            'Candidate website found; branch name/locality or street address still needs matching': FailureCode.LEAD_UNVERIFIED,
            'Retailer locator did not expose a corroborated branch/menu link': FailureCode.LEAD_UNVERIFIED,
            'Menu source address conflicts with registry': FailureCode.BRANCH_MISMATCH,
            'Detected menu belongs to a different street address: 1 Main': FailureCode.BRANCH_MISMATCH,
            'Access challenge in this acquisition session (HTTP 403); browser/session access is unresolved': FailureCode.CHALLENGE_BLOCKED,
            'Public endpoint returned HTTP 403': FailureCode.HTTP_REJECTED,
            'Public fetch failed: ConnectError': FailureCode.TRANSPORT_ERROR,
            '{"code": "incomplete_generic_menu", "message": "No structured products extracted; JavaScript or an additional schema extractor may be required"}': FailureCode.RENDER_BLANK,
            '{"code": "incomplete_generic_menu", "message": "Products extracted, but source advertises no independently verifiable full-menu total"}': FailureCode.TOTAL_UNVERIFIABLE,
            '{"code": "incomplete_menu", "message": "Sweed SSR query cache missing"}': FailureCode.DRIFT,
            'Sweed menu changed across independent complete traversals': FailureCode.UNSTABLE,
            'empty_or_large_drop_requires_independent_confirmation': FailureCode.SUSPICIOUS_DROP,
            'Sweed missing products or inconsistent advertised total': FailureCode.COUNT_MISMATCH,
            'Generic page limit reached': FailureCode.PAGINATION_UNKNOWN,
            'locator.click: Timeout 30000ms exceeded.': FailureCode.GATE_UNKNOWN,
            'Unsupported menu provider': FailureCode.PROVIDER_UNSUPPORTED,
            'Rendered page exceeds response size limit (29078756 > 26214400 bytes)': FailureCode.RESPONSE_TOO_LARGE,
            '{"code": "incomplete_generic_menu", "message": "Rendered page exceeds response size limit"}': FailureCode.RESPONSE_TOO_LARGE,
        }
        for message, code in cases.items():
            self.check(message, code)

    def test_redirected_generic_menu_is_drift_and_unidentifiable_product_is_schema_unknown(self):
        self.check('Generic menu redirected to a different source hostname; rediscovery required; missing_traversal_evidence', FailureCode.DRIFT)
        self.check('Structured product has no stable source identity; missing_traversal_evidence', FailureCode.SCHEMA_UNKNOWN)
        self.check('Menu source belongs to a different location: 290.66 mi from the registry address', FailureCode.BRANCH_MISMATCH)

    def test_unknown_text_is_explicit_and_status_hints_apply(self):
        self.check('something nobody planned for', FailureCode.UNKNOWN)
        self.check('', FailureCode.UNKNOWN)
        self.check(None, FailureCode.UNKNOWN)
        self.check('', FailureCode.BRANCH_MISMATCH, resolution_status='identity_conflict')
        self.check('odd text', FailureCode.BRANCH_MISMATCH, resolution_status='identity_conflict')
        self.check('odd text', FailureCode.GATE_AGE_TERMS, resolution_status='blocked')

    def test_challenge_takes_precedence_over_generic_http_text(self):
        self.check('Access challenge (HTTP 403)', FailureCode.CHALLENGE_BLOCKED)

    def test_every_code_has_an_action_and_challenge_never_goes_to_agent(self):
        for code in FailureCode:
            self.assertIn(code, ACTIONS)
            self.assertTrue(next_action(code))
        self.assertFalse(agent_eligible(FailureCode.CHALLENGE_BLOCKED))
        self.assertFalse(agent_eligible(FailureCode.TRANSPORT_ERROR))
        self.assertTrue(agent_eligible(FailureCode.RENDER_BLANK))
        self.assertTrue(agent_eligible(FailureCode.GATE_UNKNOWN))


if __name__ == '__main__':
    unittest.main()
