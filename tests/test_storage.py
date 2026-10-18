import json
from pathlib import Path
import tempfile
import unittest

from backend.storage import Store


def observation(key="shop", name="Test Shop", lat=40.98, lon=-89.04):
    return dict(source_key=key, name=name, address="100 Main St", city="Rutland", state="IL",
                latitude=lat, longitude=lon, serves_medical=False, raw={"name": name})


def item(identity="one", **changes):
    value = dict(source_id=identity, variant_id="base", name="Flower", brand="Brand", category="flower",
                 source_category="Flower", subcategory="", strain_type="Hybrid", thc_pct="20",
                 weight_grams="3.5", weight_label="3.5g", regular_price="40.00", effective_price="35.00",
                 conditional=False, available=True, source_url="https://example.com/menu", raw={})
    return dict(value, **changes)


def snapshot(items, **changes):
    return dict(dict(items=items, complete=True, expected_count=len(items), pages=[{"page": 1}],
                     errors=[], evidence=["test-evidence"], authoritative_zero=False,
                     provider="fixture", adapter_version="1"), **changes)


class StorageTests(unittest.TestCase):
    def test_fresh_retained_snapshot_is_not_a_successful_latest_attempt(self):
        self.apply([item()],now='2026-10-17T08:00:00+00:00')
        self.db.record_endpoint_failure(self.endpoint['id'],'failed','Network failed',now='2026-10-17T09:00:00+00:00')
        coverage=self.db.coverage(self.region['id'],now='2026-10-17T09:05:00+00:00')['counts']
        self.assertEqual(coverage['fresh_menus'],0)
        self.assertEqual(coverage['fresh_accepted_snapshots'],1)
        self.assertEqual(coverage['stores_with_accepted_menus'],1)

    def test_paginated_generic_urls_share_the_catalog_endpoint_without_merging_filters(self):
        values=[]
        for url in ['https://example.com/shop','https://example.com/shop?page=1','https://example.com/shop?page=97']:
            values.append(self.db.save_endpoint(self.shop['id'],dict(url=url,provider='generic',license_type='recreational')))
        self.assertEqual(len({value['id'] for value in values}),1)
        filtered=self.db.save_endpoint(self.shop['id'],dict(url='https://example.com/shop?category=flower&page=2',provider='generic',license_type='recreational'))
        self.assertNotEqual(filtered['id'],values[0]['id'])
        self.assertIn('category=flower',filtered['url'])

    def test_page_anchors_do_not_create_additional_menu_endpoints(self):
        first=self.db.save_endpoint(self.shop['id'],dict(url='https://example.com/menu#main-nav',provider='generic',license_type='recreational'))
        second=self.db.save_endpoint(self.shop['id'],dict(url='https://example.com/menu#main-content',provider='generic',license_type='recreational'))
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(first['url'],'https://example.com/menu')

    def test_directory_endpoints_are_retired_without_deleting_diagnostic_history(self):
        bad=self.db.save_endpoint(self.shop['id'],dict(url='https://www.jointcommerce.com/dispensaries/example/menu',provider='generic',license_type='recreational'))
        self.db.record_endpoint_failure(bad['id'],'partial','Old extraction failure')
        self.db.retire_discovery_only_endpoints()
        self.assertNotIn(bad['id'],[e['id'] for e in self.db.endpoints()])
        self.assertEqual(self.db.endpoint(bad['id'])['status'],'superseded')

    def test_legacy_anchor_identity_is_reused_after_url_canonicalization(self):
        with self.db.connection() as conn:
            conn.execute("INSERT INTO live_endpoints(id,store_id,url,provider,license_type,resolution_json,status) VALUES (?,?,?,?,?,?,?)",
                         ('legacy-anchor',self.shop['id'],'https://example.com/other-menu#main-nav','generic','recreational','{}','pending'))
        self.db.retire_discovery_only_endpoints()
        saved=self.db.save_endpoint(self.shop['id'],dict(url='https://example.com/other-menu',provider='generic',license_type='recreational'))
        self.assertEqual(saved['id'],'legacy-anchor')

    def test_partial_extraction_is_inspectable_without_replacing_accepted_catalog(self):
        self.apply([item('accepted')])
        result=self.apply([item('partial')],complete=False,errors=['No advertised total'])
        observed=self.db.menu_observations(self.endpoint['id'])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(observed['items'][0]['source_id'],'partial')
        self.assertEqual(self.db.menu_products(self.endpoint['id'])['items'][0]['source_id'],'accepted')

    def test_directory_product_count_is_scoped_to_selected_license(self):
        self.apply([item()])
        med=self.db.save_endpoint(self.shop['id'],dict(url='https://example.com/medical',provider='fixture',provider_store_id='test',license_type='medicinal',resolution_evidence=['e']))
        self.db.apply_snapshot(med['id'],snapshot([item('med1'),item('med2')]))
        self.assertEqual(self.db.stores_in_region(self.region['id'],'recreational')[0]['product_count'],1)
        self.assertEqual(self.db.stores_in_region(self.region['id'],'medicinal')[0]['product_count'],2)

    def test_menu_read_rejects_version_change_during_query(self):
        from unittest.mock import patch
        self.apply([item()])
        paginate = self.db._paginate
        def concurrent_update(*args, **kwargs):
            self.db.set_setting('data_version', self.db.setting('data_version') + 1)
            return paginate(*args, **kwargs)
        with patch.object(self.db, '_paginate', side_effect=concurrent_update):
            with self.assertRaisesRegex(ValueError, 'refresh_required'):
                self.db.menu_products(self.endpoint['id'])

    def test_blank_name_is_retained_and_quarantined_without_rejecting_full_menu(self):
        result = self.apply([item("a"), item("b", name="   ")])
        self.assertEqual(result["status"], "complete")
        rows = self.db.menu_products(self.endpoint["id"], now="2026-10-17T08:00:00+00:00")
        self.assertEqual(rows["total"], 2)
        unnamed = next(row for row in rows["items"] if row["source_id"] == "b")
        self.assertIn("missing_product_name", unnamed["exclusion_reasons"])
        self.assertFalse(unnamed["eligible"])
        self.assertEqual(self.db.query_offers(self.region["id"], now="2026-10-17T08:00:00+00:00")["total"], 1)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.db = Store(self.path / "test.db", self.path / "evidence")
        self.db.import_registry([observation()], "source-evidence", "2026-10-08", now="2026-10-17T06:00:00+00:00")
        self.region = self.db.create_region(40.9844, -89.0388, "ZIP 61358", 50)
        self.shop = self.db.stores_in_region(self.region["id"])[0]
        self.endpoint = self.db.save_endpoint(self.shop["id"], dict(url="https://example.com/menu", provider="fixture",
                                          provider_store_id="test", license_type="recreational", resolution_evidence=["source-evidence"]))

    def tearDown(self):
        self.tmp.cleanup()

    def apply(self, items, **changes):
        return self.db.apply_snapshot(self.endpoint["id"], snapshot(items, **changes), now="2026-10-17T07:00:00+00:00")

    def test_initial_full_snapshot_and_restart_retain_all_products(self):
        result = self.apply([item(str(i)) for i in range(1007)])
        self.assertEqual(result["status"], "complete")
        reopened = Store(self.path / "test.db", self.path / "evidence")
        page = reopened.query_offers(self.region["id"], page_size=20, now="2026-10-17T08:00:00+00:00")
        self.assertEqual(page["total"], 1007)
        self.assertEqual(len(page["items"]), 20)

    def test_weight_and_name_changes_update_without_price_change(self):
        self.apply([item()])
        self.apply([item(weight_grams="7", name="Corrected")])
        row = self.db.query_offers(self.region["id"], now="2026-10-17T08:00:00+00:00")["items"][0]
        self.assertEqual((row["name"], row["weight_grams"], row["price_per_gram"]), ("Corrected", "7", "5.00"))
        self.assertEqual(row["last_diff_action"], "updated")

    def test_partial_or_unvalidated_empty_does_not_erase_catalog(self):
        self.apply([item("a"), item("b")])
        for incoming in [snapshot([], complete=False, errors=["timeout"]), snapshot([])]:
            result = self.db.apply_snapshot(self.endpoint["id"], incoming, now="2026-10-17T08:00:00+00:00")
            self.assertNotEqual(result["status"], "complete")
        page = self.db.query_offers(self.region["id"], now="2026-10-17T08:01:00+00:00")
        self.assertEqual(page["total"], 2)
        self.assertEqual(self.db.endpoint(self.endpoint["id"])["last_success_at"], "2026-10-17T07:00:00+00:00")

    def test_large_drop_requires_independent_confirmation(self):
        self.apply([item(str(i)) for i in range(10)])
        changed = snapshot([item("0")])
        first = self.db.apply_snapshot(self.endpoint["id"], changed, now="2026-10-17T08:00:00+00:00")
        self.assertEqual(first["status"], "suspicious")
        too_soon = self.db.apply_snapshot(self.endpoint["id"], changed, now="2026-10-17T08:00:30+00:00")
        self.assertEqual(too_soon["status"], "suspicious")
        confirmed = self.db.apply_snapshot(self.endpoint["id"], changed, now="2026-10-17T08:01:01+00:00")
        self.assertEqual(confirmed["status"], "complete")
        self.assertEqual(self.db.query_offers(self.region["id"], now="2026-10-17T08:02:00+00:00")["total"], 1)

    def test_duplicate_or_count_mismatch_snapshot_cannot_remove(self):
        self.apply([item("a"), item("b")])
        self.assertEqual(self.apply([item("a"), item("a")])["status"], "partial")
        self.assertEqual(self.apply([item("a")], expected_count=2)["status"], "partial")
        self.assertEqual(self.db.query_offers(self.region["id"], now="2026-10-17T08:00:00+00:00")["total"], 2)

    def test_unknown_mass_and_conditional_prices_retained_but_not_ranked(self):
        self.apply([item("a", weight_grams=None), item("b", conditional=True),
                    item("c", category="edibles", source_category="Edible", weight_grams=None)])
        self.assertEqual(self.db.query_offers(self.region["id"], now="2026-10-17T08:00:00+00:00")["total"], 0)
        menu = self.db.menu_products(self.endpoint["id"], now="2026-10-17T08:00:00+00:00")
        self.assertEqual(menu["total"], 3)
        self.assertTrue(all(not row["eligible"] for row in menu["items"]))

    def test_stale_excluded_and_new_failure_visible(self):
        self.apply([item()])
        self.db.record_endpoint_failure(self.endpoint["id"], "failed", "HTTP 403", now="2026-10-17T08:00:00+00:00")
        cover = self.db.coverage(self.region["id"], now="2026-10-17T08:01:00+00:00")
        self.assertEqual(cover["counts"]["failed_menus"], 1)
        self.assertEqual(cover["counts"]["fresh_menus"], 0)
        self.assertEqual(cover['counts']['fresh_accepted_snapshots'],1)
        self.assertEqual(self.db.query_offers(self.region["id"], now="2026-10-17T20:00:00+00:00")["total"], 0)
        self.assertEqual(self.db.query_offers(self.region["id"], include_stale=True, now="2026-10-17T20:00:00+00:00")["total"], 1)

    def test_medical_and_other_endpoint_identity_isolation(self):
        med = self.db.save_endpoint(self.shop["id"], dict(url="https://example.com/medical", provider="fixture",
                                   provider_store_id="test", license_type="medicinal", resolution_evidence=["e"]))
        self.apply([item()])
        self.db.apply_snapshot(med["id"], snapshot([item(effective_price="20")]), now="2026-10-17T07:00:00+00:00")
        rec = self.db.query_offers(self.region["id"], license_type="recreational", now="2026-10-17T08:00:00+00:00")
        medical = self.db.query_offers(self.region["id"], license_type="medicinal", now="2026-10-17T08:00:00+00:00")
        self.assertEqual(rec["items"][0]["effective_price"], "35.00")
        self.assertEqual(medical["items"][0]["effective_price"], "20.00")

    def test_idempotent_snapshot_and_pagination_data_version(self):
        self.apply([item("a"), item("b")])
        before = self.db.diffs(self.region["id"])["total"]
        self.apply([item("a"), item("b")])
        self.assertEqual(self.db.diffs(self.region["id"])["total"], before)
        page = self.db.query_offers(self.region["id"], page_size=1, now="2026-10-17T08:00:00+00:00")
        self.apply([item("a", effective_price="34"), item("b")])
        with self.assertRaisesRegex(ValueError, "refresh_required"):
            self.db.query_offers(self.region["id"], data_version=page["data_version"], now="2026-10-17T08:00:00+00:00")

    def test_catalog_includes_non_comparable_items_and_removed_on_request(self):
        self.apply([item("a"), item("b", category="edibles", weight_grams=None)])
        result = self.db.query_catalog(self.region["id"], q="Flower", now="2026-10-17T08:00:00+00:00")
        self.assertEqual(result["total"], 2)
        self.assertTrue(any(not r["eligible"] for r in result["items"]))

    def test_source_missing_store_remains_visible_as_coverage_uncertainty(self):
        self.db.import_registry([observation("new", "Other Store", 41, -89)], "e2")
        stores = self.db.stores_in_region(self.region["id"])
        self.assertEqual(len(stores), 2)
        old = next(s for s in stores if s["id"] == self.shop["id"])
        self.assertFalse(old["source_present"])

    def test_empty_confirmation_requires_both_attempts_authoritative(self):
        self.apply([item()])
        self.db.apply_snapshot(self.endpoint["id"], snapshot([], authoritative_zero=False), now="2026-10-17T08:00:00+00:00")
        result = self.db.apply_snapshot(self.endpoint["id"], snapshot([], authoritative_zero=True), now="2026-10-17T08:01:01+00:00")
        self.assertEqual(result["status"], "suspicious")
        confirmed = self.db.apply_snapshot(self.endpoint["id"], snapshot([], authoritative_zero=True), now="2026-10-17T08:02:02+00:00")
        self.assertEqual(confirmed["status"], "complete")

    def test_structured_adapter_error_is_preserved_without_overwriting_menu(self):
        self.apply([item()])
        result = self.apply([], complete=False, errors=[{"code": "incomplete_menu", "message": "HTTP 403"}])
        self.assertEqual(result["status"], "partial")
        self.assertIn("HTTP 403", self.db.endpoint(self.endpoint["id"])["last_error"])

    def test_real_strain_and_change_filters_affect_ranking(self):
        self.apply([item("a", strain_type="Indica"), item("b", strain_type="Sativa")])
        self.apply([item("a", strain_type="Indica", effective_price="30"), item("b", strain_type="Sativa")])
        filtered = self.db.query_offers(self.region["id"], strain_type="Indica", action="updated", now="2026-10-17T08:00:00+00:00")
        self.assertEqual([r["source_id"] for r in filtered["items"]], ["a"])

    def test_provider_context_change_invalidates_fresh_ranking(self):
        self.apply([item()])
        self.db.save_endpoint(self.shop["id"], dict(url="https://example.com/menu", provider="other",
                              provider_store_id="different", license_type="recreational", resolution_evidence=["new"]))
        self.assertEqual(self.db.query_offers(self.region["id"], now="2026-10-17T08:00:00+00:00")["total"], 0)
        self.assertEqual(self.db.menu_products(self.endpoint["id"])["total"], 1)

    def test_snapshot_provider_must_match_endpoint_before_acceptance(self):
        result = self.apply([item()], provider="wrong")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(self.db.menu_products(self.endpoint["id"])["total"], 0)

    def test_menu_url_change_for_same_verified_tenant_keeps_endpoint_identity(self):
        moved = self.db.save_endpoint(self.shop['id'], dict(url='https://example.com/new-menu',provider='fixture',
                                  provider_store_id='test',license_type='recreational',resolution_evidence=['new']))
        self.assertEqual(moved['id'], self.endpoint['id'])
        self.assertEqual(len(self.db.endpoints()), 1)
        self.assertEqual(moved['url'], 'https://example.com/new-menu')

    def test_existing_database_is_backed_up_before_non_destructive_migration(self):
        import sqlite3
        from contextlib import closing
        path = self.path / "legacy.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("CREATE TABLE user_data (value TEXT)")
            conn.execute("INSERT INTO user_data VALUES ('keep me')")
        Store(path, self.path / "legacy-evidence")
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT value FROM user_data").fetchone()[0], "keep me")
        with closing(sqlite3.connect(str(path) + ".before-live.sqlite3")) as conn:
            self.assertEqual(conn.execute("SELECT value FROM user_data").fetchone()[0], "keep me")


if __name__ == "__main__":
    unittest.main()
