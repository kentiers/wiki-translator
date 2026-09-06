"""
Automated Interlanguage Link ({{ill}}) Delinker for Indonesian Wikipedia.

When a red link is turned blue (a new article is created on id.wikipedia.org),
this module:
1. Queries id.wikipedia.org backlinks (action=query&list=backlinks) to find all
   articles referencing the newly created page.
2. Scans and converts obsolete {{ill|Target|...}} templates into direct [[Target]]
   (or [[Target|Label]]) internal wikilinks across all referring articles.
3. Saves the cleaned articles with clear, humanized edit summaries, eliminating
   expensive parser function (#ifexist) overhead across the encyclopedia.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .http_client import MediaWikiApiClient, DEFAULT_API_URL
from .link_fidelity_validator import LinkFidelityValidator, default_fidelity_validator

logger = logging.getLogger(__name__)


class IllDelinker:
    """
    Finds and converts obsolete {{ill|...}} templates across Wikipedia articles
    pointing to an article that now exists.
    """

    DEFAULT_SUMMARY = "merapikan pranala: ubah {{ill}} menjadi [[...]] karena artikel telah dibuat"

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        user_agent: Optional[str] = None,
        http_client: Optional[MediaWikiApiClient] = None,
        fidelity_validator: Optional[LinkFidelityValidator] = None,
    ):
        self.api_url = api_url
        self.user_agent = (
            user_agent
            or "WikiTranslatorIllDelinker/1.0 (https://id.wikipedia.org; automated {{ill}} delinker)"
        )
        self.http_client = http_client or MediaWikiApiClient(
            api_url=self.api_url, user_agent=self.user_agent
        )
        self.fidelity_validator = fidelity_validator or default_fidelity_validator

    def find_referring_articles(self, target_title: str, limit: int = 50) -> List[str]:
        """
        Finds all Mainspace (ns=0) articles linking to or transcluding `target_title`.
        """
        clean_target = target_title.strip()
        params = {
            "action": "query",
            "list": "backlinks",
            "bltitle": clean_target,
            "blnamespace": "0",
            "bllimit": str(min(limit, 500)),
        }
        res, err = self.http_client.request(params, method="GET")
        if err or not res:
            logger.warning("Failed to query backlinks for '%s': %s", clean_target, err)
            return []

        backlinks = res.get("query", {}).get("backlinks", [])
        return [b["title"] for b in backlinks if "title" in b]

    def delink_article_wikitext(
        self, wikitext: str, target_title: Optional[str] = None
    ) -> Tuple[str, int]:
        """
        Converts {{ill|Target|...}} into [[Target]] (or [[Target|Label]]).
        If target_title is provided, only targets matching target_title are converted.
        If target_title is None, all {{ill}} whose parameter 1 exists on idwiki are converted.
        """
        if target_title:
            norm_target = target_title.strip().replace("_", " ").lower()
            pattern = self.fidelity_validator.ILL_PATTERN
            converted_count = 0

            def repl(m: re.Match) -> str:
                nonlocal converted_count
                raw = m.group(0)
                parsed = self.fidelity_validator.parse_ill(raw)
                if not parsed:
                    return raw
                id_title, lang, foreign_target, label = parsed
                if id_title.strip().replace("_", " ").lower() == norm_target:
                    converted_count += 1
                    if label and label.strip().lower() != id_title.strip().lower():
                        return f"[[{id_title}|{label}]]"
                    return f"[[{id_title}]]"
                return raw

            updated_text = pattern.sub(repl, wikitext)
            return updated_text, converted_count
        else:
            return self.fidelity_validator.auto_convert_existing_links(wikitext)

    def fetch_page_wikitext(self, title: str) -> Optional[str]:
        """Fetches the latest wikitext of an article."""
        params = {
            "action": "query",
            "titles": title.strip(),
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
        }
        res, err = self.http_client.request(params, method="GET")
        if err or not res:
            return None
        pages = res.get("query", {}).get("pages", {})
        for p in pages.values():
            if "missing" in p or "revisions" not in p:
                return None
            return p["revisions"][0]["slots"]["main"].get("*", "")
        return None

    def delink_target_across_wikipedia(
        self,
        target_title: str,
        username: str,
        bot_password: str,
        summary: Optional[str] = None,
        limit: int = 50,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Finds all articles in idwiki linking to target_title via {{ill}},
        converts {{ill}} to direct [[...]] wikilinks, and edits each article.
        """
        clean_target = target_title.strip()
        referring_articles = self.find_referring_articles(clean_target, limit=limit)
        edit_summary = summary or f"merapikan pranala: ubah {{{{ill}}}} menjadi [[{clean_target}]] karena artikel telah dibuat"

        results: List[Dict[str, Any]] = []

        if not referring_articles:
            return {
                "target_title": clean_target,
                "referring_articles_count": 0,
                "modified_articles_count": 0,
                "results": [],
            }

        if dry_run:
            for art in referring_articles:
                wikitext = self.fetch_page_wikitext(art)
                if wikitext:
                    new_text, count = self.delink_article_wikitext(wikitext, target_title=clean_target)
                    if count > 0:
                        results.append({
                            "title": art,
                            "modified": True,
                            "converted_links": count,
                            "status": "simulated",
                        })
            return {
                "target_title": clean_target,
                "dry_run": True,
                "referring_articles_count": len(referring_articles),
                "modified_articles_count": len(results),
                "results": results,
            }

        # 1. Authenticate with MediaWiki Bot Password
        login_ok, login_err = self._authenticate(username, bot_password)
        if not login_ok:
            return {
                "target_title": clean_target,
                "success": False,
                "error": f"Authentication failed: {login_err}",
                "results": [],
            }

        # 2. Get CSRF token
        csrf_token, token_err = self._get_csrf_token()
        if not csrf_token:
            return {
                "target_title": clean_target,
                "success": False,
                "error": f"Failed to get CSRF token: {token_err}",
                "results": [],
            }

        # 3. Process each referring article
        for art in referring_articles:
            wikitext = self.fetch_page_wikitext(art)
            if not wikitext:
                continue

            new_text, count = self.delink_article_wikitext(wikitext, target_title=clean_target)
            if count == 0:
                continue

            # Save the updated article
            edit_params = {
                "action": "edit",
                "title": art,
                "text": new_text,
                "summary": edit_summary,
                "token": csrf_token,
            }
            resp, edit_err = self.http_client.request(edit_params, method="POST")
            success = bool(resp and resp.get("edit", {}).get("result") == "Success")
            results.append({
                "title": art,
                "modified": True,
                "converted_links": count,
                "success": success,
                "error": edit_err or (None if success else str(resp)),
            })

        return {
            "target_title": clean_target,
            "referring_articles_count": len(referring_articles),
            "modified_articles_count": len([r for r in results if r.get("modified")]),
            "results": results,
        }

    def _authenticate(self, username: str, bot_password: str) -> Tuple[bool, Optional[str]]:
        """MediaWiki Bot Password login."""
        token_payload, err = self.http_client.request(
            {"action": "query", "meta": "tokens", "type": "login"}, method="GET"
        )
        if err or not token_payload:
            return False, f"Failed to get login token: {err}"
        login_token = token_payload.get("query", {}).get("tokens", {}).get("logintoken")
        if not login_token:
            return False, "Login token not found"

        login_res, lerr = self.http_client.request(
            {
                "action": "login",
                "lgname": username,
                "lgpassword": bot_password,
                "lgtoken": login_token,
            },
            method="POST",
        )
        if lerr or not login_res:
            return False, f"Login request failed: {lerr}"
        result_status = login_res.get("login", {}).get("result")
        if result_status == "Success":
            return True, None
        return False, login_res.get("login", {}).get("reason", "Unknown rejection")

    def _get_csrf_token(self) -> Tuple[Optional[str], Optional[str]]:
        """Retrieves CSRF edit token."""
        token_res, terr = self.http_client.request(
            {"action": "query", "meta": "tokens", "type": "csrf"}, method="GET"
        )
        if terr or not token_res:
            return None, f"Failed to fetch CSRF token: {terr}"
        token = token_res.get("query", {}).get("tokens", {}).get("csrftoken")
        return token, None


default_ill_delinker = IllDelinker()
