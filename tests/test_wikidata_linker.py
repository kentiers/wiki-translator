"""
Unit tests for Wikidata Linker System (wiki_translator/wikidata_linker.py).
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from wiki_translator.wikidata_linker import (
    WikidataLinker,
    default_wikidata_linker,
)


class TestWikidataLinker(unittest.TestCase):
    def setUp(self):
        self.linker = WikidataLinker()

    def test_default_instance(self):
        self.assertIsInstance(default_wikidata_linker, WikidataLinker)

    def test_get_item_id_from_enwiki_direct_success(self):
        mock_response = {
            "entities": {
                "Q250250": {
                    "id": "Q250250",
                    "type": "item",
                    "labels": {"en": {"value": "Alfred Enoch"}},
                }
            },
            "success": 1,
        }
        with patch.object(self.linker, "_make_request", return_value=(mock_response, None)):
            qid = self.linker.get_item_id_from_enwiki("Alfred Enoch")
            self.assertEqual(qid, "Q250250")

    def test_get_item_id_from_enwiki_missing_direct_then_search(self):
        # Direct lookup returns -1 / missing
        mock_direct = {
            "entities": {
                "-1": {
                    "site": "enwiki",
                    "title": "Kevin Macdonald",
                    "missing": "",
                }
            },
            "success": 1,
        }
        mock_search = {
            "search": [
                {
                    "id": "Q1344373",
                    "title": "Q1344373",
                    "label": "Kevin Macdonald",
                    "description": "Scottish director",
                }
            ]
        }

        def mock_req(params, method="GET"):
            if params.get("action") == "wbgetentities":
                return mock_direct, None
            elif params.get("action") == "wbsearchentities":
                return mock_search, None
            return None, "Not found"

        with patch.object(self.linker, "_make_request", side_effect=mock_req):
            with patch("urllib.request.urlopen", side_effect=Exception("network err")):
                qid = self.linker.get_item_id_from_enwiki("Kevin Macdonald")
                self.assertEqual(qid, "Q1344373")

    def test_get_item_id_from_enwiki_empty(self):
        qid = self.linker.get_item_id_from_enwiki("   ")
        self.assertIsNone(qid)

    def test_link_idwiki_sitelink_dry_run(self):
        res = self.linker.link_idwiki_sitelink(
            item_id="Q250250",
            id_title="Alfred Enoch",
            username="TestUser",
            bot_password="testpassword",
            dry_run=True,
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["item_id"], "Q250250")
        self.assertEqual(res["id_title"], "Alfred Enoch")
        self.assertEqual(res["linksite"], "idwiki")
        self.assertIn("Q250250", res["url"])
        self.assertIsNone(res["error"])

    def test_link_idwiki_sitelink_invalid_qid(self):
        res = self.linker.link_idwiki_sitelink(
            item_id="InvalidID",
            id_title="Alfred Enoch",
            username="TestUser",
            bot_password="testpassword",
            dry_run=False,
        )
        self.assertFalse(res["success"])
        self.assertIn("Invalid Wikidata item ID", res["error"])

    def test_link_idwiki_sitelink_auth_failure(self):
        with patch.object(self.linker, "_authenticate_bot_password", return_value=(False, "Bad credentials")):
            res = self.linker.link_idwiki_sitelink(
                item_id="Q250250",
                id_title="Alfred Enoch",
                username="TestUser",
                bot_password="testpassword",
                dry_run=False,
            )
            self.assertFalse(res["success"])
            self.assertEqual(res.get("reason"), "auth_failed")
            self.assertIn("Wikidata authentication failed: Bad credentials", res["error"])
    def test_link_idwiki_sitelink_csrf_failure(self):
        with patch.object(self.linker, "_authenticate_bot_password", return_value=(True, None)):
            with patch.object(self.linker, "_get_csrf_token", return_value=(None, "No token")):
                res = self.linker.link_idwiki_sitelink(
                    item_id="Q250250",
                    id_title="Alfred Enoch",
                    username="TestUser",
                    bot_password="testpassword",
                    dry_run=False,
                )
                self.assertFalse(res["success"])
                self.assertIn("Failed to get Wikidata CSRF token", res["error"])

    def test_link_idwiki_sitelink_success(self):
        mock_entity_resp = {
            "entity": {
                "id": "Q250250",
                "sitelinks": {
                    "idwiki": {
                        "site": "idwiki",
                        "title": "Alfred Enoch",
                        "badges": [],
                    }
                },
            },
            "success": 1,
        }
        with patch.object(self.linker, "_authenticate_bot_password", return_value=(True, None)):
            with patch.object(self.linker, "_get_csrf_token", return_value=("test_csrf_token", None)):
                with patch.object(self.linker, "_make_request", return_value=(mock_entity_resp, None)) as mock_post:
                    res = self.linker.link_idwiki_sitelink(
                        item_id="Q250250",
                        id_title="Alfred Enoch",
                        username="TestUser",
                        bot_password="testpassword",
                        dry_run=False,
                    )
                    self.assertTrue(res["success"])
                    self.assertFalse(res["dry_run"])
                    self.assertEqual(res["item_id"], "Q250250")
                    self.assertEqual(res["sitelink"]["title"], "Alfred Enoch")
                    self.assertIsNone(res["error"])
                    mock_post.assert_called_once()
                    called_params = mock_post.call_args[0][0]
                    self.assertEqual(called_params["action"], "wbsetsitelink")
                    self.assertEqual(called_params["id"], "Q250250")
                    self.assertEqual(called_params["linksite"], "idwiki")
                    self.assertEqual(called_params["linktitle"], "Alfred Enoch")

    def test_link_idwiki_sitelink_api_error_response(self):
        mock_err_resp = {
            "error": {
                "code": "failed-save",
                "info": "Conflict with other page",
            }
        }
        with patch.object(self.linker, "_authenticate_bot_password", return_value=(True, None)):
            with patch.object(self.linker, "_get_csrf_token", return_value=("test_csrf_token", None)):
                with patch.object(self.linker, "_make_request", return_value=(mock_err_resp, None)):
                    res = self.linker.link_idwiki_sitelink(
                        item_id="Q250250",
                        id_title="Alfred Enoch",
                        username="TestUser",
                        bot_password="testpassword",
                        dry_run=False,
                    )
                    self.assertFalse(res["success"])
                    self.assertIn("Conflict with other page", res["error"])


    def test_circuit_breaker_prevents_repeated_login_attempts(self):
        # First call triggers login failure and trips the breaker
        login_resp = {"login": {"result": "Failed", "reason": "WrongPass"}}
        with patch.object(self.linker, "_make_request") as mock_req:
            mock_req.side_effect = [
                ({"query": {"tokens": {"logintoken": "tok123"}}}, None),
                (login_resp, None),
            ]
            res1 = self.linker.link_idwiki_sitelink(
                item_id="Q250250",
                id_title="Alfred Enoch",
                username="TestUser",
                bot_password="bad_password",
                dry_run=False,
            )
            self.assertFalse(res1["success"])
            self.assertEqual(res1.get("reason"), "auth_failed")
            self.assertTrue(self.linker._auth_failed)
            self.assertEqual(mock_req.call_count, 2)

        # Second call MUST be blocked by circuit breaker without making any login HTTP request
        with patch.object(self.linker, "_make_request") as mock_req2:
            res2 = self.linker.link_idwiki_sitelink(
                item_id="Q250250",
                id_title="Alfred Enoch",
                username="TestUser",
                bot_password="bad_password",
                dry_run=False,
            )
            self.assertFalse(res2["success"])
            self.assertEqual(res2.get("reason"), "auth_failed")
            # Absolutely NO network/request calls made
            mock_req2.assert_not_called()

    def test_resolve_credentials_prefers_wikidata_env_vars(self):
        with patch.dict(
            "os.environ",
            {
                "WIKIDATA_BOT_USERNAME": "WDUser@bot",
                "WIKIDATA_BOT_PASSWORD": "WDPassword123",
                "WIKI_BOT_USERNAME": "WPUser@bot",
                "WIKI_BOT_PASSWORD": "WPPassword123",
            },
            clear=True,
        ):
            u, p = self.linker._resolve_credentials()
            self.assertEqual(u, "WDUser@bot")
            self.assertEqual(p, "WDPassword123")

    def test_resolve_credentials_fallback_to_wiki_env_vars(self):
        with patch.dict(
            "os.environ",
            {
                "WIKI_BOT_USERNAME": "WPUser@bot",
                "WIKI_BOT_PASSWORD": "WPPassword123",
            },
            clear=True,
        ):
            u, p = self.linker._resolve_credentials()
            self.assertEqual(u, "WPUser@bot")
            self.assertEqual(p, "WPPassword123")

    def test_missing_credentials_fails_gracefully_without_login(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(self.linker, "_make_request") as mock_req:
                res = self.linker.link_idwiki_sitelink(
                    item_id="Q250250",
                    id_title="Alfred Enoch",
                    username=None,
                    bot_password=None,
                    dry_run=False,
                )
                self.assertFalse(res["success"])
                self.assertEqual(res.get("reason"), "auth_failed")
                mock_req.assert_not_called()

if __name__ == "__main__":
    unittest.main()
