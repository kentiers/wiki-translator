"""
Unit tests for the unified MediaWikiApiClient.
"""

import json
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.parse
import urllib.request

from wiki_translator.http_client import (
    DEFAULT_API_URL,
    DEFAULT_USER_AGENT,
    DEFAULT_WIKIDATA_API_URL,
    MediaWikiApiClient,
    default_idwiki_client,
    default_wikidata_client,
)


class TestMediaWikiApiClient(unittest.TestCase):
    """Unit tests for MediaWikiApiClient request serialization, cookie tracking, and error handling."""

    def setUp(self):
        self.client = MediaWikiApiClient(
            api_url="https://id.wikipedia.org/w/api.php",
            user_agent="TestUserAgent/1.0",
            timeout=10.0,
        )

    def test_initialization_defaults(self):
        client = MediaWikiApiClient()
        self.assertEqual(client.api_url, DEFAULT_API_URL)
        self.assertEqual(client.user_agent, DEFAULT_USER_AGENT)
        self.assertEqual(client.timeout, 15.0)
        self.assertEqual(client.cookie_jar, {})

        # Verify singletons
        self.assertEqual(default_idwiki_client.api_url, DEFAULT_API_URL)
        self.assertEqual(default_wikidata_client.api_url, DEFAULT_WIKIDATA_API_URL)

    def test_initialization_custom(self):
        self.assertEqual(self.client.api_url, "https://id.wikipedia.org/w/api.php")
        self.assertEqual(self.client.user_agent, "TestUserAgent/1.0")
        self.assertEqual(self.client.timeout, 10.0)
        self.assertEqual(self.client.cookie_jar, {})

    @patch("urllib.request.urlopen")
    def test_get_request_serialization_and_query_encoding(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers.get_all.return_value = []
        mock_resp.read.return_value = json.dumps({"query": {"tokens": {"logintoken": "tok123"}}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        params = {"action": "query", "meta": "tokens", "type": "login"}
        payload, err = self.client.get(params)

        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["query"]["tokens"]["logintoken"], "tok123")

        mock_urlopen.assert_called_once()
        req: urllib.request.Request = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)
        self.assertTrue(req.full_url.startswith("https://id.wikipedia.org/w/api.php?"))

        # Verify query parameters parsed from URL
        parsed_url = urllib.parse.urlparse(req.full_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        self.assertEqual(query_params["action"], ["query"])
        self.assertEqual(query_params["meta"], ["tokens"])
        self.assertEqual(query_params["type"], ["login"])
        self.assertEqual(query_params["format"], ["json"])

        # Verify User-Agent header
        self.assertEqual(req.headers.get("User-agent"), "TestUserAgent/1.0")

    @patch("urllib.request.urlopen")
    def test_post_request_body_encoding_and_content_type(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers.get_all.return_value = []
        mock_resp.read.return_value = json.dumps({"edit": {"result": "Success"}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        post_params = {
            "action": "edit",
            "title": "Pengguna:Test/Bak pasir",
            "text": "Konten draf ensiklopedis dengan karakter khusus: é, à, ü.",
            "token": "csrf123+\\",
        }
        payload, err = self.client.post(post_params)

        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["edit"]["result"], "Success")

        mock_urlopen.assert_called_once()
        req: urllib.request.Request = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "https://id.wikipedia.org/w/api.php")
        self.assertEqual(
            req.headers.get("Content-type"), "application/x-www-form-urlencoded"
        )
        self.assertEqual(req.headers.get("User-agent"), "TestUserAgent/1.0")

        # Verify POST body decoding and UTF-8 handling
        self.assertIsNotNone(req.data)
        body_decoded = req.data.decode("utf-8")
        parsed_body = urllib.parse.parse_qs(body_decoded)
        self.assertEqual(parsed_body["action"], ["edit"])
        self.assertEqual(parsed_body["title"], ["Pengguna:Test/Bak pasir"])
        self.assertEqual(
            parsed_body["text"],
            ["Konten draf ensiklopedis dengan karakter khusus: é, à, ü."],
        )
        self.assertEqual(parsed_body["format"], ["json"])
        self.assertEqual(parsed_body["token"], ["csrf123+\\"])

    @patch("urllib.request.urlopen")
    def test_set_cookie_parsing_single_and_multiple_headers(self, mock_urlopen):
        mock_resp = MagicMock()
        # MediaWiki sends multiple Set-Cookie headers for session, token, and user ID
        mock_resp.headers.get_all.return_value = [
            "idwikiUserID=12345; Path=/; Domain=.wikipedia.org; Secure; HttpOnly",
            "idwikiUserName=EditorUser; Path=/; Domain=.wikipedia.org; Secure; HttpOnly",
            "idwikiSession=sess_abc987xyz; Path=/; Domain=.wikipedia.org; Secure; HttpOnly",
        ]
        mock_resp.read.return_value = json.dumps({"login": {"result": "Success"}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        payload, err = self.client.post({"action": "login", "lgname": "EditorUser"})
        self.assertIsNone(err)

        expected_cookies = {
            "idwikiUserID": "12345",
            "idwikiUserName": "EditorUser",
            "idwikiSession": "sess_abc987xyz",
        }
        self.assertEqual(self.client.cookie_jar, expected_cookies)

    @patch("urllib.request.urlopen")
    def test_subsequent_request_sends_stored_cookies(self, mock_urlopen):
        # 1. First request captures cookies
        login_resp = MagicMock()
        login_resp.headers.get_all.return_value = [
            "sessionID=session_secret_token; Path=/",
            "wikiToken=tok_987; Path=/",
        ]
        login_resp.read.return_value = json.dumps({"login": {"result": "Success"}}).encode("utf-8")

        # 2. Second request
        edit_resp = MagicMock()
        edit_resp.headers.get_all.return_value = []
        edit_resp.read.return_value = json.dumps({"edit": {"result": "Success"}}).encode("utf-8")

        mock_urlopen.return_value.__enter__.side_effect = [login_resp, edit_resp]

        self.client.post({"action": "login"})
        self.client.post({"action": "edit", "title": "Target"})

        self.assertEqual(mock_urlopen.call_count, 2)
        second_req: urllib.request.Request = mock_urlopen.call_args_list[1][0][0]

        cookie_header = second_req.headers.get("Cookie")
        self.assertIsNotNone(cookie_header)
        self.assertIn("sessionID=session_secret_token", cookie_header)
        self.assertIn("wikiToken=tok_987", cookie_header)

    @patch("urllib.request.urlopen")
    def test_clear_cookies_resets_session_state(self, mock_urlopen):
        # Seed cookies
        self.client._cookie_jar["sessionID"] = "session_secret_token"
        self.client._cookie_jar["user"] = "Editor"
        self.assertEqual(len(self.client.cookie_jar), 2)

        self.client.clear_cookies()
        self.assertEqual(self.client.cookie_jar, {})

        # Verify next request does NOT contain Cookie header
        mock_resp = MagicMock()
        mock_resp.headers.get_all.return_value = []
        mock_resp.read.return_value = json.dumps({"query": {}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.client.get({"action": "query"})
        req: urllib.request.Request = mock_urlopen.call_args[0][0]
        self.assertNotIn("Cookie", req.headers)

    @patch("urllib.request.urlopen")
    def test_error_handling_http_500(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://id.wikipedia.org/w/api.php",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )

        payload, err = self.client.get({"action": "query"})
        self.assertIsNone(payload)
        self.assertIsNotNone(err)
        self.assertIn("500", err)
        self.assertIn("Internal Server Error", err)

    @patch("urllib.request.urlopen")
    def test_error_handling_network_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("timed out")

        payload, err = self.client.post({"action": "edit"})
        self.assertIsNone(payload)
        self.assertIsNotNone(err)
        self.assertIn("timed out", err)

    @patch("urllib.request.urlopen")
    def test_error_handling_invalid_json(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.headers.get_all.return_value = []
        mock_resp.read.return_value = b"<html><head><title>502 Bad Gateway</title></head></html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        payload, err = self.client.get({"action": "query"})
        self.assertIsNone(payload)
        self.assertIsNotNone(err)
        self.assertGreater(len(err), 0)

    @patch("urllib.request.urlopen")
    def test_retry_on_transient_error_succeeds_on_retry(self, mock_urlopen):
        err_503 = urllib.error.HTTPError(
            "https://id.wikipedia.org/w/api.php", 503, "Service Unavailable", {}, None
        )
        success_resp = MagicMock()
        success_resp.headers.get_all.return_value = []
        success_resp.read.return_value = b'{"query": {"pages": [{"pageid": 123}]}}'

        # Fail twice with 503, succeed on 3rd try
        mock_urlopen.side_effect = [
            err_503,
            err_503,
            MagicMock(__enter__=MagicMock(return_value=success_resp), __exit__=MagicMock(return_value=False)),
        ]

        payload, err = self.client.request({"action": "query"})
        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["query"]["pages"][0]["pageid"], 123)
        self.assertEqual(mock_urlopen.call_count, 3)


if __name__ == "__main__":
    unittest.main()
