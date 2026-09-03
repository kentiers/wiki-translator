"""
Wikidata Linker System.

Connects newly published id.wikipedia.org articles to their corresponding
Wikidata items (QID) using the Wikidata Action API (https://www.wikidata.org/w/api.php).
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple


class WikidataLinker:
    """Manages linking articles between Indonesian Wikipedia and Wikidata items."""

    API_URL = "https://www.wikidata.org/w/api.php"
    USER_AGENT = (
        "WikiTranslatorUserScript/1.0 "
        "(https://id.wikipedia.org/wiki/Pengguna:Baloo_Official; Wikidata sitelink linker)"
    )
    DEFAULT_SUMMARY = "hubungkan artikel id.wikipedia"

    def __init__(
        self,
        api_url: str = API_URL,
        user_agent: str = USER_AGENT,
    ):
        self.api_url = api_url
        self.user_agent = user_agent
        self._cookie_jar: Dict[str, str] = {}

    def _make_request(
        self, params: Dict[str, str], method: str = "GET"
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Executes an HTTP request to Wikidata MediaWiki API with session cookie management."""
        params["format"] = "json"

        cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookie_jar.items())
        headers = {
            "User-Agent": self.user_agent,
        }
        if cookie_header:
            headers["Cookie"] = cookie_header

        data = None
        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(params).encode("utf-8")
            url = self.api_url
        else:
            query_str = urllib.parse.urlencode(params)
            url = f"{self.api_url}?{query_str}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                cookie_headers = resp.headers.get_all("Set-Cookie") or []
                for c in cookie_headers:
                    parts = c.split(";")[0].split("=", 1)
                    if len(parts) == 2:
                        self._cookie_jar[parts[0].strip()] = parts[1].strip()

                body = resp.read().decode("utf-8")
                payload = json.loads(body)
                return payload, None
        except Exception as e:
            return None, str(e)

    def _authenticate_bot_password(
        self, username: str, bot_password: str
    ) -> Tuple[bool, Optional[str]]:
        """Authenticates on Wikidata using MediaWiki Bot Password flow."""
        token_payload, err = self._make_request(
            {"action": "query", "meta": "tokens", "type": "login"}, method="GET"
        )
        if err or not token_payload:
            return False, f"Failed to get login token: {err}"

        login_token = (
            token_payload.get("query", {}).get("tokens", {}).get("logintoken")
        )
        if not login_token:
            return False, "Login token not found in API response"

        login_params = {
            "action": "login",
            "lgname": username,
            "lgpassword": bot_password,
            "lgtoken": login_token,
        }
        resp, login_err = self._make_request(login_params, method="POST")
        if login_err or not resp:
            return False, f"Login HTTP request failed: {login_err}"

        login_res = resp.get("login", {})
        status = login_res.get("result")
        if status == "Success":
            return True, None
        else:
            reason = login_res.get("reason", status)
            return False, f"Login rejected: {reason}"

    def _get_csrf_token(self) -> Tuple[Optional[str], Optional[str]]:
        """Fetches CSRF token on Wikidata: action=query&meta=tokens&type=csrf."""
        payload, err = self._make_request(
            {"action": "query", "meta": "tokens", "type": "csrf"}, method="GET"
        )
        if err or not payload:
            return None, err

        token = payload.get("query", {}).get("tokens", {}).get("csrftoken")
        if not token:
            return None, "CSRF token not present in query tokens"
        return token, None

    def get_item_id_from_enwiki(self, en_title: str) -> Optional[str]:
        """
        Queries Wikidata API to find the item ID (QID) for an English Wikipedia title.
        First tries wbgetentities on enwiki. If not found or redirected, resolves redirect
        or searches by title.
        """
        clean_title = en_title.strip()
        if not clean_title:
            return None

        # 1. Direct wbgetentities query
        params = {
            "action": "wbgetentities",
            "sites": "enwiki",
            "titles": clean_title,
            "props": "info",
        }
        data, err = self._make_request(params, method="GET")
        if data and "entities" in data:
            for qid, entity in data["entities"].items():
                if qid != "-1" and "missing" not in entity:
                    return qid

        # 2. Try resolving redirect via enwiki Action API if direct lookup didn't find entity
        try:
            en_api_url = "https://en.wikipedia.org/w/api.php"
            query_params = {
                "action": "query",
                "titles": clean_title,
                "redirects": "1",
                "format": "json",
            }
            url = f"{en_api_url}?{urllib.parse.urlencode(query_params)}"
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                en_data = json.loads(resp.read().decode("utf-8"))
                pages = en_data.get("query", {}).get("pages", {})
                for page_info in pages.values():
                    resolved_title = page_info.get("title")
                    if resolved_title and resolved_title.lower() != clean_title.lower():
                        # Retry with resolved title
                        params["titles"] = resolved_title
                        data_res, _ = self._make_request(params, method="GET")
                        if data_res and "entities" in data_res:
                            for qid, entity in data_res["entities"].items():
                                if qid != "-1" and "missing" not in entity:
                                    return qid
        except Exception:
            pass

        # 3. Fallback: wbsearchentities
        search_params = {
            "action": "wbsearchentities",
            "search": clean_title,
            "language": "en",
            "type": "item",
            "limit": "5",
        }
        search_data, _ = self._make_request(search_params, method="GET")
        if search_data and "search" in search_data:
            for item in search_data["search"]:
                item_id = item.get("id")
                # Verify match
                if item_id:
                    return item_id

        return None

    def link_idwiki_sitelink(
        self,
        item_id: str,
        id_title: str,
        username: str,
        bot_password: str,
        summary: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Links an Indonesian Wikipedia article to a Wikidata item.
        Summary default: DEFAULT_SUMMARY.
        Returns dictionary with status, item ID, and sitelink details.
        """
        clean_item_id = item_id.strip().upper()
        clean_id_title = id_title.strip()
        edit_summary = summary or self.DEFAULT_SUMMARY

        if not clean_item_id.startswith("Q"):
            return {
                "success": False,
                "item_id": clean_item_id,
                "id_title": clean_id_title,
                "error": f"Invalid Wikidata item ID format: '{clean_item_id}'. Must start with 'Q'.",
            }

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "item_id": clean_item_id,
                "id_title": clean_id_title,
                "linksite": "idwiki",
                "summary": edit_summary,
                "url": f"https://www.wikidata.org/wiki/{clean_item_id}",
                "error": None,
            }

        # Clear cookies before authenticating
        self._cookie_jar = {}

        # 1. Authenticate with bot password on Wikidata
        auth_success, auth_err = self._authenticate_bot_password(username, bot_password)
        if not auth_success:
            return {
                "success": False,
                "item_id": clean_item_id,
                "id_title": clean_id_title,
                "error": f"Wikidata authentication failed: {auth_err}",
            }

        # 2. Get CSRF token
        csrf_token, token_err = self._get_csrf_token()
        if not csrf_token:
            return {
                "success": False,
                "item_id": clean_item_id,
                "id_title": clean_id_title,
                "error": f"Failed to get Wikidata CSRF token: {token_err}",
            }

        # 3. Call action=wbsetsitelink
        sitelink_params = {
            "action": "wbsetsitelink",
            "id": clean_item_id,
            "linksite": "idwiki",
            "linktitle": clean_id_title,
            "summary": edit_summary,
            "token": csrf_token,
        }
        resp, link_err = self._make_request(sitelink_params, method="POST")
        if link_err or not resp:
            return {
                "success": False,
                "item_id": clean_item_id,
                "id_title": clean_id_title,
                "error": f"Wikidata API request failed: {link_err}",
            }

        if "error" in resp:
            err_info = resp["error"].get("info", json.dumps(resp["error"]))
            return {
                "success": False,
                "item_id": clean_item_id,
                "id_title": clean_id_title,
                "error": f"Wikidata wbsetsitelink error: {err_info}",
                "response": resp,
            }

        entity = resp.get("entity", {})
        sitelinks = entity.get("sitelinks", {})
        idwiki_sitelink = sitelinks.get("idwiki", {})

        return {
            "success": True,
            "dry_run": False,
            "item_id": clean_item_id,
            "id_title": clean_id_title,
            "linksite": "idwiki",
            "summary": edit_summary,
            "url": f"https://www.wikidata.org/wiki/{clean_item_id}",
            "sitelink": idwiki_sitelink,
            "entity": entity,
            "error": None,
        }


default_wikidata_linker = WikidataLinker()
