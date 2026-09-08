"""
Wikidata Linker System.

Connects newly published id.wikipedia.org articles to their corresponding
Wikidata items (QID) using the Wikidata Action API (https://www.wikidata.org/w/api.php).
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from wiki_translator.http_client import MediaWikiApiClient

logger = logging.getLogger(__name__)

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
        http_client: Optional[MediaWikiApiClient] = None,
    ):
        self.api_url = api_url
        self.user_agent = user_agent
        self.http_client = http_client or MediaWikiApiClient(
            api_url=self.api_url, user_agent=self.user_agent
        )
        self._auth_failed: bool = False
        self._auth_fail_reason: Optional[str] = None
        self._auth_successful: bool = False

    @property
    def _cookie_jar(self) -> Dict[str, str]:
        return self.http_client._cookie_jar

    @_cookie_jar.setter
    def _cookie_jar(self, value: Dict[str, str]) -> None:
        self.http_client._cookie_jar = value
    def _make_request(
        self, params: Dict[str, Any], method: str = "GET"
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Executes an HTTP request to Wikidata MediaWiki API with session cookie management."""
        self.http_client.api_url = self.api_url
        self.http_client.user_agent = self.user_agent
        return self.http_client.request(params, method=method)
    def _resolve_credentials(
        self, username: Optional[str] = None, bot_password: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Resolves Wikidata bot username and password from params or environment variables.

        Supports WIKIDATA_BOT_USERNAME and WIKIDATA_BOT_PASSWORD,
        falling back to WIKI_BOT_USERNAME / WIKI_USERNAME and WIKI_BOT_PASSWORD / MEDIAWIKI_BOT_PASSWORD.
        Ensures that bare usernames lacking a bot suffix ('@bot') are rejected to prevent
        failed login alerts on the main user account.
        """
        raw_u = (
            username
            or os.environ.get("WIKIDATA_BOT_USERNAME")
            or os.environ.get("WIKI_BOT_USERNAME")
            or os.environ.get("WIKI_USERNAME")
            or os.environ.get("MEDIAWIKI_USERNAME")
        )
        p = (
            bot_password
            or os.environ.get("WIKIDATA_BOT_PASSWORD")
            or os.environ.get("WIKI_BOT_PASSWORD")
            or os.environ.get("MEDIAWIKI_BOT_PASSWORD")
        )
        if not raw_u:
            return None, p

        u = raw_u.strip()
        if "@" not in u:
            # Check if known bot suffix exists in bot username env vars
            known_bot = (
                os.environ.get("WIKIDATA_BOT_USERNAME")
                or os.environ.get("WIKI_BOT_USERNAME")
            )
            if known_bot and "@" in known_bot:
                suffix = known_bot.split("@", 1)[1].strip()
                if suffix:
                    u = f"{u}@{suffix}"
                else:
                    u = None
            elif u.lower() == "baloo official":
                u = f"{u}@asisten_draf"
            else:
                u = None
        return u, p

    def _authenticate_bot_password(
        self, username: str, bot_password: str
    ) -> Tuple[bool, Optional[str]]:
        """Authenticates on Wikidata using MediaWiki Bot Password flow.

        Implements a circuit breaker: if authentication previously failed or fails here,
        caches the failure and never retries repeatedly.
        """
        if not username or "@" not in username:
            logger.warning(
                "Bot username '%s' lacks @botname suffix. Aborting login to prevent failed login alerts on main user account.",
                username,
            )
            return False, "Bot username must contain @botname suffix (e.g. User@botname)"

        if self._auth_failed:
            logger.warning(
                "Wikidata bot password not configured or invalid on wikidata.org; skipping write action (circuit open)"
            )
            return False, self._auth_fail_reason or "Cached authentication failure"

        if self._auth_successful and self._cookie_jar:
            return True, None

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
            self._auth_successful = True
            self._auth_failed = False
            self._auth_fail_reason = None
            return True, None
        else:
            reason = login_res.get("reason", status)
            err_msg = f"Login rejected: {reason}"
            # Trip circuit breaker on authentication rejection
            self._auth_failed = True
            self._auth_fail_reason = err_msg
            self._auth_successful = False
            logger.warning(
                "Wikidata bot password not configured or invalid on wikidata.org; skipping write action (%s)",
                reason,
            )
            return False, err_msg
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
        raw_title = en_title.strip()
        if not raw_title:
            return None

        # Normalize Indonesian namespace prefixes if passed accidentally
        import re
        clean_title = re.sub(r"^(?:Templat|Template)\s*:\s*", "Template:", raw_title, flags=re.IGNORECASE)
        clean_title = re.sub(r"^(?:Kategori|Category)\s*:\s*", "Category:", clean_title, flags=re.IGNORECASE)
        clean_title = clean_title.strip()

        # Check if raw_title already starts with Kategori: or Templat: and also check idwiki directly first
        if raw_title.lower().startswith(("kategori:", "templat:", "category:", "template:")):
            # Try idwiki sitelink lookup directly if it's already an id title
            try:
                id_params = {
                    "action": "wbgetentities",
                    "sites": "idwiki",
                    "titles": raw_title,
                    "props": "info",
                }
                id_data, _ = self._make_request(id_params, method="GET")
                if id_data and "entities" in id_data:
                    for qid, entity in id_data["entities"].items():
                        if qid != "-1" and "missing" not in entity:
                            return qid
            except Exception:
                pass
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

    def get_idwiki_sitelinks_batch(self, en_titles: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Batch queries Wikidata API (wbgetentities) for up to 50 titles per chunk.
        Returns a mapping of {lowercase_en_title: {"qid": str, "canonical_en": str, "id_title": Optional[str], "exists_on_id": bool}}.
        """
        if not en_titles:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        batch_size = 50

        # Filter and clean unique titles
        clean_titles = []
        seen = set()
        for t in en_titles:
            ct = t.strip()
            if ct and ct.lower() not in seen:
                seen.add(ct.lower())
                clean_titles.append(ct)

        for i in range(0, len(clean_titles), batch_size):
            chunk = clean_titles[i : i + batch_size]
            params = {
                "action": "wbgetentities",
                "sites": "enwiki",
                "titles": "|".join(chunk),
                "props": "sitelinks",
                "format": "json",
            }
            res, _ = self._make_request(params, method="GET")
            if not res or "entities" not in res:
                continue

            for qid, edata in res["entities"].items():
                if qid == "-1" or "missing" in edata:
                    continue
                sitelinks = edata.get("sitelinks", {})
                en_t = sitelinks.get("enwiki", {}).get("title")
                id_t = sitelinks.get("idwiki", {}).get("title")

                item_info = {
                    "qid": qid,
                    "canonical_en": en_t or "",
                    "id_title": id_t,
                    "exists_on_id": id_t is not None,
                }
                if en_t:
                    results[en_t.lower()] = item_info
                for req_t in chunk:
                    if en_t and req_t.lower() == en_t.lower():
                        results[req_t.lower()] = item_info

        return results

    def link_idwiki_sitelink(
        self,
        item_id: str,
        id_title: str,
        username: Optional[str] = None,
        bot_password: Optional[str] = None,
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

        # Check circuit breaker before attempting authentication
        if self._auth_failed:
            logger.warning(
                "Wikidata bot password not configured or invalid on wikidata.org; skipping write action"
            )
            return {
                "success": False,
                "reason": "auth_failed",
                "item_id": clean_item_id,
                "id_title": clean_id_title,
                "error": f"Wikidata authentication failed: {self._auth_fail_reason or 'circuit open'}",
            }

        # Resolve credentials (support WIKIDATA_BOT_* falling back to WIKI_BOT_*)
        resolved_user, resolved_pass = self._resolve_credentials(username, bot_password)
        if not resolved_user or not resolved_pass:
            logger.warning(
                "Wikidata bot password not configured or invalid on wikidata.org; skipping write action"
            )
            return {
                "success": False,
                "reason": "auth_failed",
                "item_id": clean_item_id,
                "id_title": clean_id_title,
                "error": "Wikidata credentials not configured (missing username or bot password)",
            }

        # 1. Authenticate with bot password on Wikidata (if not already authenticated)
        if not self._auth_successful or not self._cookie_jar:
            self._cookie_jar = {}
            auth_success, auth_err = self._authenticate_bot_password(resolved_user, resolved_pass)
            if not auth_success:
                logger.warning(
                    "Wikidata bot password not configured or invalid on wikidata.org; skipping write action"
                )
                return {
                    "success": False,
                    "reason": "auth_failed",
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

    def create_item_with_sitelink(
        self,
        id_title: str,
        label_id: Optional[str] = None,
        label_en: Optional[str] = None,
        description_id: Optional[str] = None,
        description_en: Optional[str] = None,
        instance_of_qid: Optional[str] = None,
        username: Optional[str] = None,
        bot_password: Optional[str] = None,
        summary: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Creates a brand-new Wikidata item (action=wbeditentity&new=item) and attaches the idwiki sitelink.
        Dynamically infers namespace metadata (Templat, Kategori, Modul, Mainspace) when parameters are omitted.
        """
        clean_id_title = id_title.strip()
        clean_label_id = (label_id or clean_id_title).strip()
        clean_label_en = (label_en or clean_label_id).strip()

        # Dynamic namespace-aware metadata inference
        if description_id is None or description_en is None or instance_of_qid is None:
            if clean_id_title.startswith(("Templat:", "Template:")):
                inferred_desc_id = "templat navigasi Wikimedia"
                inferred_desc_en = "Wikimedia navigation template"
                inferred_qid = "Q639864"
            elif clean_id_title.startswith(("Kategori:", "Category:")):
                inferred_desc_id = "kategori Wikimedia"
                inferred_desc_en = "Wikimedia category"
                inferred_qid = "Q4167836"
            elif clean_id_title.startswith(("Modul:", "Module:")):
                inferred_desc_id = "modul Lua Wikimedia"
                inferred_desc_en = "Wikimedia Lua module"
                inferred_qid = "Q15155490"
            else:
                inferred_desc_id = ""
                inferred_desc_en = ""
                inferred_qid = None

            description_id = description_id if description_id is not None else inferred_desc_id
            description_en = description_en if description_en is not None else inferred_desc_en
            instance_of_qid = instance_of_qid if instance_of_qid is not None else inferred_qid

        edit_summary = summary or f"buat entitas Wikidata baru untuk {clean_id_title}"

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "item_id": "Q_SIMULATED",
                "id_title": clean_id_title,
                "url": "https://www.wikidata.org/wiki/Q_SIMULATED",
                "error": None,
            }

        if self._auth_failed:
            return {
                "success": False,
                "reason": "auth_failed",
                "id_title": clean_id_title,
                "error": self._auth_fail_reason or "Wikidata authentication not available",
            }

        user, pwd = self._resolve_credentials(username, bot_password)
        if not user or not pwd:
            return {
                "success": False,
                "id_title": clean_id_title,
                "error": "Missing Wikidata credentials",
            }

        if not self._auth_successful:
            login_ok, login_err = self._authenticate_bot_password(user, pwd)
            if not login_ok:
                return {
                    "success": False,
                    "id_title": clean_id_title,
                    "error": f"Wikidata login failed: {login_err}",
                }

        csrf_token, token_err = self._get_csrf_token()
        if not csrf_token:
            return {
                "success": False,
                "id_title": clean_id_title,
                "error": f"Failed to get Wikidata CSRF token: {token_err}",
            }

        data: Dict[str, Any] = {
            "labels": {
                "id": {"language": "id", "value": clean_label_id},
                "en": {"language": "en", "value": clean_label_en},
            },
            "descriptions": {
                "id": {"language": "id", "value": description_id},
                "en": {"language": "en", "value": description_en},
            },
            "sitelinks": {
                "idwiki": {"site": "idwiki", "title": clean_id_title}
            }
        }

        if instance_of_qid and instance_of_qid.upper().startswith("Q"):
            try:
                numeric_qid = int(instance_of_qid.upper().replace("Q", ""))
                data["claims"] = [
                    {
                        "mainsnak": {
                            "snaktype": "value",
                            "property": "P31",
                            "datavalue": {
                                "value": {
                                    "entity-type": "item",
                                    "numeric-id": numeric_qid,
                                    "id": instance_of_qid.upper(),
                                },
                                "type": "wikibase-entityid",
                            },
                            "datatype": "wikibase-item",
                        },
                        "type": "statement",
                        "rank": "normal",
                    }
                ]
            except Exception:
                pass

        params = {
            "action": "wbeditentity",
            "new": "item",
            "data": json.dumps(data),
            "summary": edit_summary,
            "token": csrf_token,
            "formatversion": "2",
            "format": "json",
        }

        resp, err = self._make_request(params, method="POST")
        if err or not resp:
            return {
                "success": False,
                "id_title": clean_id_title,
                "error": f"Wikidata wbeditentity failed: {err}",
            }

        if "error" in resp:
            err_info = resp["error"].get("info", json.dumps(resp["error"]))
            return {
                "success": False,
                "id_title": clean_id_title,
                "error": f"Wikidata wbeditentity error: {err_info}",
            }

        created_qid = resp.get("entity", {}).get("id")
        return {
            "success": True,
            "item_id": created_qid,
            "id_title": clean_id_title,
            "url": f"https://www.wikidata.org/wiki/{created_qid}" if created_qid else None,
            "entity": resp.get("entity"),
            "error": None,
        }


default_wikidata_linker = WikidataLinker()
