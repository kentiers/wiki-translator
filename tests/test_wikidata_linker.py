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


if __name__ == "__main__":
    unittest.main()
