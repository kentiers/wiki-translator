"""
Mainspace Publisher and Page Mover System for Indonesian Wikipedia (id.wikipedia.org).

Promotes user sandbox drafts to the Main Namespace (Ruang Nama Utama) or publishes
directly to mainspace with safety and collision checks.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple
from wiki_translator.http_client import MediaWikiApiClient
from wiki_translator.sandbox_publisher import (
    DEFAULT_PROJECT_SLUG,
    SandboxPublisher,
    default_sandbox_publisher,
    sanitize_edit_summary,
)
from wiki_translator.wikidata_linker import (
    WikidataLinker,
    default_wikidata_linker,
)


class MainspacePublisher:
    """Manages publishing and moving drafts to the Main Namespace on id.wikipedia.org."""

    API_URL = "https://id.wikipedia.org/w/api.php"
    BASE_WEB_URL = "https://id.wikipedia.org/wiki"
    DEFAULT_MOVE_REASON = "pemindahan draf ke ruang utama"
    DEFAULT_PUBLISH_SUMMARY = "kembangkan artikel dari enwiki"
    DEFAULT_TALK_SUMMARY = "atribusi terjemahan"
    USER_AGENT = "WikiTranslatorUserScript/1.0 (https://id.wikipedia.org/wiki/Pengguna:Baloo_Official; Mainspace publisher & mover helper)"

    def __init__(
        self,
        api_url: str = API_URL,
        user_agent: str = USER_AGENT,
        sandbox_publisher: Optional[SandboxPublisher] = None,
        wikidata_linker: Optional[WikidataLinker] = None,
        http_client: Optional[MediaWikiApiClient] = None,
    ):
        self.api_url = api_url
        self.user_agent = user_agent
        self.http_client = http_client or MediaWikiApiClient(
            api_url=self.api_url, user_agent=self.user_agent
        )
        self.sandbox_publisher = sandbox_publisher or default_sandbox_publisher
        self.wikidata_linker = wikidata_linker or default_wikidata_linker
        from .wiki_client import WikipediaClient
        self.en_client = WikipediaClient(lang="en")
    @property
    def _cookie_jar(self) -> Dict[str, str]:
        return self.http_client._cookie_jar

    @_cookie_jar.setter
    def _cookie_jar(self, value: Dict[str, str]) -> None:
        self.http_client._cookie_jar = value
    def _make_request(
        self, params: Dict[str, Any], method: str = "GET"
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Executes an HTTP request to MediaWiki API with session cookie management."""
        self.http_client.api_url = self.api_url
        self.http_client.user_agent = self.user_agent
        return self.http_client.request(params, method=method)
    def _authenticate_bot_password(
        self, username: str, bot_password: str
    ) -> Tuple[bool, Optional[str]]:
        """Authenticates using MediaWiki Bot Password flow."""
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
        """Fetches CSRF token for move/edit actions: action=query&meta=tokens&type=csrf."""
        payload, err = self._make_request(
            {"action": "query", "meta": "tokens", "type": "csrf"}, method="GET"
        )
        if err or not payload:
            return None, err

        token = payload.get("query", {}).get("tokens", {}).get("csrftoken")
        if not token:
            return None, "CSRF token not present in query tokens"
        return token, None

    def check_mainspace_collision(self, title: str) -> Tuple[bool, Optional[str]]:
        """
        Checks if `title` already exists on id.wikipedia.org via Action API action=query&titles=...
        Returns (exists, page_url_if_exists).
        """
        clean_title = title.strip()
        params = {
            "action": "query",
            "titles": clean_title,
        }
        payload, err = self._make_request(params, method="GET")
        if err or not payload:
            return False, None

        pages = payload.get("query", {}).get("pages", {})
        for page_id_str, page_info in pages.items():
            # If page_id is negative or page has "missing" field, it does not exist
            if int(page_id_str) < 0 or "missing" in page_info:
                return False, None
            # Page exists
            canonical_title = page_info.get("title", clean_title).replace(" ", "_")
            url = f"{self.BASE_WEB_URL}/{urllib.parse.quote(canonical_title, safe='/:()')}"
            return True, url

        return False, None

    def move_draft_to_mainspace(
        self,
        username: str,
        bot_password: str,
        sandbox_source: str,
        mainspace_target: str,
        reason: Optional[str] = None,
        move_talk: bool = True,
        dry_run: bool = False,
        topic: Optional[str] = None,
        update_dashboard: bool = True,
        en_title: Optional[str] = None,
        link_wikidata: bool = True,
        wikidata_item_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Moves a sandbox draft to mainspace via action=move.
        Summary: reason or 'Memindahkan draf rintisan ke ruang nama utama'.
        Optionally links to Wikidata item (QID) if link_wikidata is True.
        Returns: {"success": bool, "from": str, "to": str, "talk_moved": bool, "url": str, "error": Optional[str]}
        """
        clean_source = sandbox_source.strip()
        clean_target = mainspace_target.strip()
        canonical_target = clean_target.replace(" ", "_")
        target_url = f"{self.BASE_WEB_URL}/{urllib.parse.quote(canonical_target, safe='/:()')}"
        move_reason = sanitize_edit_summary(reason or self.DEFAULT_MOVE_REASON, default_fallback=self.DEFAULT_MOVE_REASON)

        if dry_run:
            res = {
                "success": True,
                "dry_run": True,
                "from": clean_source,
                "to": clean_target,
                "talk_moved": move_talk,
                "url": target_url,
                "error": None,
            }
            if update_dashboard:
                # Extract article title from target or source
                source_parts = clean_source.split("/")
                article_title = source_parts[-1].replace("_", " ")
                # Extract slug if present in source
                slug_val = None
                if len(source_parts) >= 4:
                    # e.g. Pengguna:X/Bak_pasir/Draf/2026-09/Title
                    slug_val = "/".join(source_parts[2:-1])
                dash_res = self.sandbox_publisher.update_monthly_dashboard(
                    username=username,
                    article_title=article_title,
                    topic=topic,
                    status="Tayang resmi",
                    mainspace_link=f"[[{clean_target}]]",
                    slug=slug_val,
                    dry_run=True,
                )
                res["dashboard"] = dash_res
            if link_wikidata:
                target_qid = wikidata_item_id or (self.wikidata_linker.get_item_id_from_enwiki(en_title) if en_title else None) or self.wikidata_linker.get_item_id_from_enwiki(clean_target)
                if target_qid:
                    res["wikidata"] = self.wikidata_linker.link_idwiki_sitelink(
                        item_id=target_qid,
                        id_title=clean_target,
                        username=username,
                        bot_password=bot_password,
                        dry_run=True,
                    )
            return res
        # Reset session cookies for fresh login
        self._cookie_jar = {}

        # 1. Authenticate
        login_success, login_err = self._authenticate_bot_password(username, bot_password)
        if not login_success:
            return {
                "success": False,
                "from": clean_source,
                "to": clean_target,
                "talk_moved": False,
                "url": target_url,
                "error": f"Authentication failed: {login_err}",
            }

        # 2. Get CSRF token
        csrf_token, token_err = self._get_csrf_token()
        if not csrf_token:
            return {
                "success": False,
                "from": clean_source,
                "to": clean_target,
                "talk_moved": False,
                "url": target_url,
                "error": f"Failed to obtain CSRF token: {token_err}",
            }

        # 3. Execute action=move
        move_params = {
            "action": "move",
            "from": clean_source,
            "to": clean_target,
            "reason": move_reason,
            "token": csrf_token,
        }
        if move_talk:
            move_params["movetalk"] = "1"

        resp, move_err = self._make_request(move_params, method="POST")
        if move_err or not resp:
            return {
                "success": False,
                "from": clean_source,
                "to": clean_target,
                "talk_moved": False,
                "url": target_url,
                "error": f"Network/HTTP error: {move_err}",
            }

        if "error" in resp:
            err_info = resp["error"].get("info", str(resp["error"]))
            return {
                "success": False,
                "from": clean_source,
                "to": clean_target,
                "talk_moved": False,
                "url": target_url,
                "error": err_info,
            }

        move_data = resp.get("move", {})
        talk_moved = "talkmove" in move_data or move_data.get("talkmove") is not None

        result = {
            "success": True,
            "from": move_data.get("from", clean_source),
            "to": move_data.get("to", clean_target),
            "talk_moved": talk_moved,
            "url": target_url,
            "error": None,
        }

        if update_dashboard:
            try:
                source_parts = clean_source.split("/")
                article_title = source_parts[-1].replace("_", " ")
                slug_val = None
                if len(source_parts) >= 4:
                    slug_val = "/".join(source_parts[2:-1])
                dash_res = self.sandbox_publisher.update_monthly_dashboard(
                    username=username,
                    article_title=article_title,
                    topic=topic,
                    status="Tayang resmi",
                    mainspace_link=f"[[{clean_target}]]",
                    slug=slug_val,
                    bot_password=bot_password,
                    dry_run=False,
                )
                result["dashboard"] = dash_res
            except Exception as e:
                result["dashboard"] = {"success": False, "error": str(e)}
        if link_wikidata:
            try:
                target_qid = wikidata_item_id or (self.wikidata_linker.get_item_id_from_enwiki(en_title) if en_title else None) or self.wikidata_linker.get_item_id_from_enwiki(clean_target)
                if target_qid:
                    wiki_res = self.wikidata_linker.link_idwiki_sitelink(
                        item_id=target_qid,
                        id_title=clean_target,
                        username=username,
                        bot_password=bot_password,
                        dry_run=False,
                    )
                    result["wikidata"] = wiki_res
                else:
                    result["wikidata"] = {
                        "success": False,
                        "error": f"Could not find Wikidata item ID for '{en_title or clean_target}'",
                    }
            except Exception as e:
                result["wikidata"] = {"success": False, "error": str(e)}

        return result

    def _edit_page(
        self, title: str, text: str, summary: str, csrf_token: str
    ) -> Dict[str, Any]:
        """Edits/creates a page using action=edit."""
        params = {
            "action": "edit",
            "title": title,
            "text": text,
            "summary": summary,
            "token": csrf_token,
        }
        payload, err = self._make_request(params, method="POST")
        if err or not payload:
            return {"success": False, "error": f"Network/HTTP error: {err}"}

        if "error" in payload:
            err_info = payload["error"].get("info", str(payload["error"]))
            return {"success": False, "error": err_info}

        edit_result = payload.get("edit", {})
        if edit_result.get("result") == "Success":
            return {"success": True, "edit": edit_result}
        else:
            return {
                "success": False,
                "error": f"Edit failed with status: {edit_result.get('result')}",
                "edit": edit_result,
            }

    def publish_directly_to_mainspace(
        self,
        username: str,
        bot_password: str,
        mainspace_title: str,
        wikitext: str,
        talk_wikitext: Optional[str] = None,
        summary: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False,
        en_title: Optional[str] = None,
        link_wikidata: bool = True,
        wikidata_item_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publishes wikitext and optional talk attribution directly to Main Namespace.
        - Checks collision: if target exists and not force, returns error.
        - Authenticates and fetches CSRF token.
        - Edits main page and optional talk page.
        - Optionally links to Wikidata item (QID) if link_wikidata is True.
        """
        clean_title = mainspace_title.strip()
        canonical_title = clean_title.replace(" ", "_")
        main_url = f"{self.BASE_WEB_URL}/{urllib.parse.quote(canonical_title, safe='/:()')}"
        talk_title = f"Pembicaraan:{clean_title}"
        talk_url = f"{self.BASE_WEB_URL}/{urllib.parse.quote(talk_title.replace(' ', '_'), safe='/:()')}"

        # Strip draft/review banners and sandbox notices from mainspace content
        import re
        wikitext = re.sub(
            r"^\s*\{\|[^\n]*\n\|[^\n]*(?:'''Draf perbaikan'''|ℹ️|draf\s+perbaikan)[^\n]*\n\|\}\s*",
            "",
            wikitext or "",
            flags=re.IGNORECASE,
        )
        wikitext = re.sub(r"\{\{Kotak pemberitahuan[\s\S]*?\}\}\s*", "", wikitext, flags=re.IGNORECASE).strip()
        edit_summary = sanitize_edit_summary(summary or self.DEFAULT_PUBLISH_SUMMARY, default_fallback=self.DEFAULT_PUBLISH_SUMMARY)
        # Automated Link Fidelity Guard:
        # Automatically scan and safeguard all bare redlinks into {{ill|...|en|...}}
        # so that every uncreated page gets an interlanguage reference badge [en] automatically!
        from .link_fidelity_validator import default_fidelity_validator
        try:
            wikitext, _, _ = default_fidelity_validator.safeguard_redlinks_with_ill(
                draft_wikitext=wikitext,
                source_wikitext=None,
            )
            wikitext, _ = default_fidelity_validator.prune_ill_to_single_language(wikitext)
        except Exception:
            pass
        # Source of Truth Verification for Templates:
        # Never publish a template unless its source is confirmed to exist on en.wikipedia.org!
        if clean_title.startswith(("Templat:", "Template:")) and not force:
            en_tmpl = en_title or clean_title.replace("Templat:", "Template:")
            try:
                en_exists = self.en_client.page_exists(en_tmpl)
            except Exception:
                en_exists = False
            if not en_exists:
                return {
                    "success": False,
                    "error": f"Verifikasi Source of Truth Gagal: Templat sumber '{en_tmpl}' tidak ditemukan di en.wikipedia.org! Pembuatan templat tanpa jangkar sumber diblokir sistem.",
                }

        # Collision check
        if not dry_run or not force:
            exists, existing_url = self.check_mainspace_collision(clean_title)
            if exists and not force:
                return {
                    "success": False,
                    "error": f"Target article '{clean_title}' already exists at {existing_url}. Use force=True to overwrite.",
                    "main_page": {"title": clean_title, "url": existing_url or main_url},
                }

        if dry_run:
            result: Dict[str, Any] = {
                "success": True,
                "dry_run": True,
                "main_page": {
                    "title": clean_title,
                    "url": main_url,
                    "status": "simulated",
                    "bytes": len(wikitext),
                    "summary": edit_summary,
                },
            }
            if talk_wikitext:
                result["talk_page"] = {
                    "title": talk_title,
                    "url": talk_url,
                    "status": "simulated",
                    "bytes": len(talk_wikitext),
                    "summary": sanitize_edit_summary(self.DEFAULT_TALK_SUMMARY, default_fallback=self.DEFAULT_TALK_SUMMARY),
                }
            if link_wikidata:
                target_qid = wikidata_item_id or (self.wikidata_linker.get_item_id_from_enwiki(en_title) if en_title else None) or self.wikidata_linker.get_item_id_from_enwiki(clean_title)
                if target_qid:
                    result["wikidata"] = self.wikidata_linker.link_idwiki_sitelink(
                        item_id=target_qid,
                        id_title=clean_title,
                        username=username,
                        bot_password=bot_password,
                        dry_run=True,
                    )
            return result

        # Reset session cookies
        self._cookie_jar = {}

        # 1. Authenticate
        login_success, login_err = self._authenticate_bot_password(username, bot_password)
        if not login_success:
            return {
                "success": False,
                "error": f"Authentication failed: {login_err}",
                "main_page": {"title": clean_title, "url": main_url},
            }

        # 2. CSRF Token
        csrf_token, token_err = self._get_csrf_token()
        if not csrf_token:
            return {
                "success": False,
                "error": f"Failed to obtain CSRF token: {token_err}",
                "main_page": {"title": clean_title, "url": main_url},
            }

        # 3. Edit main page
        main_resp = self._edit_page(
            title=clean_title,
            text=wikitext,
            summary=edit_summary,
            csrf_token=csrf_token,
        )
        if not main_resp.get("success"):
            return {
                "success": False,
                "error": main_resp.get("error", "Unknown edit error on main page"),
                "main_page": {
                    "title": clean_title,
                    "url": main_url,
                    "response": main_resp,
                },
            }

        result = {
            "success": True,
            "dry_run": False,
            "main_page": {
                "title": clean_title,
                "url": main_url,
                "status": "published",
                "pageid": main_resp.get("edit", {}).get("pageid"),
                "newrevid": main_resp.get("edit", {}).get("newrevid"),
                "bytes": len(wikitext),
            },
        }

        # 4. Edit talk page if requested
        if talk_wikitext:
            talk_resp = self._edit_page(
                title=talk_title,
                text=talk_wikitext,
                summary=sanitize_edit_summary(self.DEFAULT_TALK_SUMMARY, default_fallback=self.DEFAULT_TALK_SUMMARY),
                csrf_token=csrf_token,
            )
            result["talk_page"] = {
                "title": talk_title,
                "url": talk_url,
                "status": "published" if talk_resp.get("success") else "failed",
                "pageid": talk_resp.get("edit", {}).get("pageid"),
                "newrevid": talk_resp.get("edit", {}).get("newrevid"),
                "error": talk_resp.get("error"),
                "bytes": len(talk_wikitext),
            }
        # 5. Link to Wikidata if requested
        if link_wikidata:
            try:
                target_qid = wikidata_item_id or (self.wikidata_linker.get_item_id_from_enwiki(en_title) if en_title else None) or self.wikidata_linker.get_item_id_from_enwiki(clean_title)
                if target_qid:
                    wiki_res = self.wikidata_linker.link_idwiki_sitelink(
                        item_id=target_qid,
                        id_title=clean_title,
                        username=username,
                        bot_password=bot_password,
                        dry_run=False,
                    )
                    result["wikidata"] = wiki_res
                else:
                    result["wikidata"] = {
                        "success": False,
                        "error": f"Could not find Wikidata item ID for '{en_title or clean_title}'",
                    }
            except Exception as e:
                result["wikidata"] = {"success": False, "error": str(e)}

        return result


default_mainspace_publisher = MainspacePublisher()
