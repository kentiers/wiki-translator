"""
Unified HTTP client for MediaWiki API interactions with cookie persistence.

Consolidates MediaWiki API requests, user-agent configuration, URL/form encoding,
session cookie management, and safe response parsing across id.wikipedia.org
and wikidata.org publishers and linkers.
"""

import json
from typing import Any, Dict, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
    wait_none,
)


def _is_transient_network_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {429, 500, 502, 503, 504}
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError)):
        return True
    return False
DEFAULT_API_URL = "https://id.wikipedia.org/w/api.php"
DEFAULT_WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
DEFAULT_USER_AGENT = (
    "WikiTranslatorUserScript/1.0 "
    "(https://id.wikipedia.org/wiki/Pengguna:Baloo_Official; MediaWikiApiClient)"
)
DEFAULT_TIMEOUT = 15.0


class MediaWikiApiClient:
    """Unified HTTP client for MediaWiki Action API with session cookie management."""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        user_agent: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        retry_delay: float = 0.05,
    ):
        self.api_url = api_url
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._cookie_jar: Dict[str, str] = {}

    @property
    def cookie_jar(self) -> Dict[str, str]:
        """Returns the current session cookie jar."""
        return self._cookie_jar

    def clear_cookies(self) -> None:
        """Clears all stored session cookies."""
        self._cookie_jar.clear()

    def request(
        self, params: Dict[str, Any], method: str = "GET"
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Executes an HTTP request to the MediaWiki API with session cookie tracking.

        Guarantees format=json, encodes query params / POST body with UTF-8,
        maintains session cookies from Set-Cookie headers, and safely decodes
        JSON responses. Traps exceptions and returns (None, err) on failure.
        """
        try:
            params["format"] = "json"
        except (TypeError, KeyError):
            pass

        req_params = dict(params)
        req_params["format"] = "json"

        cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookie_jar.items())
        headers = {
            "User-Agent": self.user_agent,
        }
        if cookie_header:
            headers["Cookie"] = cookie_header

        data = None
        method_upper = method.upper()

        if method_upper == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(req_params).encode("utf-8")
            url = self.api_url
        else:
            query_str = urllib.parse.urlencode(req_params)
            url = f"{self.api_url}?{query_str}"

        req = urllib.request.Request(
            url, data=data, headers=headers, method=method_upper
        )

        def _execute_http_call() -> Dict[str, Any]:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                cookie_headers = resp.headers.get_all("Set-Cookie") or []
                for c in cookie_headers:
                    parts = c.split(";")[0].split("=", 1)
                    if len(parts) == 2:
                        self._cookie_jar[parts[0].strip()] = parts[1].strip()

                body = resp.read().decode("utf-8")
                return json.loads(body)

        try:
            if self.max_retries > 1:
                wait_strategy = (
                    wait_exponential_jitter(initial=self.retry_delay, max=2.0)
                    if self.retry_delay > 0
                    else wait_none()
                )
                for attempt in Retrying(
                    stop=stop_after_attempt(self.max_retries),
                    wait=wait_strategy,
                    retry=retry_if_exception(_is_transient_network_error),
                    reraise=True,
                ):
                    with attempt:
                        return _execute_http_call(), None
            return _execute_http_call(), None
        except Exception as e:
            return None, str(e)

    def get(
        self, params: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Convenience wrapper for GET requests."""
        return self.request(params, method="GET")

    def post(
        self, params: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Convenience wrapper for POST requests."""
        return self.request(params, method="POST")


default_idwiki_client = MediaWikiApiClient(api_url=DEFAULT_API_URL)
default_wikidata_client = MediaWikiApiClient(api_url=DEFAULT_WIKIDATA_API_URL)

__all__ = [
    "MediaWikiApiClient",
    "default_idwiki_client",
    "default_wikidata_client",
]
