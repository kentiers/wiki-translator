"""
Media Manager for Indonesian Wikipedia Translation Suite.

Purpose:
- Audits article media (images/posters in infobox e.g. `| image = ...`, or `[[File:...]]`).
- Detects Commons vs local en.wiki non-free files.
- Generates Indonesian Fair Use rationale wikitext.
- Supports downloading en.wiki media and uploading to id.wikipedia.org.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class MediaAuditItem:
    """Represents an audited media item in an article."""
    raw_filename: str
    cleaned_filename: str
    source_context: str  # "infobox" or "wikitext_link"
    is_commons: bool = False
    is_id_wiki: bool = False
    status: str = "unknown"  # "commons_shared", "id_wiki_exists", "local_non_free", "not_found"
    rationale: Optional[str] = None
    download_url: Optional[str] = None


class MediaManager:
    """Audits, validates, and manages media files between en.wiki, Commons, and id.wiki."""

    COMMONS_API = "https://commons.wikimedia.org/w/api.php"
    ID_WIKI_API = "https://id.wikipedia.org/w/api.php"
    EN_WIKI_API = "https://en.wikipedia.org/w/api.php"
    USER_AGENT = "MediaWikiUserScript/1.0 (MediaManager automated auditor; https://id.wikipedia.org)"

    def __init__(
        self,
        commons_api: str = COMMONS_API,
        id_wiki_api: str = ID_WIKI_API,
        en_wiki_api: str = EN_WIKI_API,
        user_agent: str = USER_AGENT,
    ):
        self.commons_api = commons_api
        self.id_wiki_api = id_wiki_api
        self.en_wiki_api = en_wiki_api
        self.user_agent = user_agent
        self._cookie_jar: Dict[str, str] = {}

    def clean_filename(self, filename: str) -> str:
        """Strips namespace prefixes, brackets, and extra whitespace from a filename."""
        name = filename.strip()
        # Strip [[...]] if present
        if name.startswith("[[") and name.endswith("]]"):
            name = name[2:-2].strip()
        # Handle piped links e.g. File:Foo.jpg|thumb|Caption
        if "|" in name:
            name = name.split("|", 1)[0].strip()
        # Strip prefix
        for prefix in ("file:", "berkas:", "image:", "gambar:"):
            if name.lower().startswith(prefix):
                name = name[len(prefix):].strip()
                break
        return name.replace(" ", "_")

    def _query_api(
        self,
        api_url: str,
        params: Dict[str, str],
        method: str = "GET",
        data_bytes: Optional[bytes] = None,
        content_type: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Makes an HTTP request to a MediaWiki API."""
        params["format"] = "json"
        cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookie_jar.items())
        headers = {"User-Agent": self.user_agent}
        if cookie_header:
            headers["Cookie"] = cookie_header

        data = data_bytes
        if method == "POST" and data is None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(params).encode("utf-8")
            url = api_url
        elif method == "POST" and content_type:
            headers["Content-Type"] = content_type
            url = api_url
        else:
            query_str = urllib.parse.urlencode(params)
            url = f"{api_url}?{query_str}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                cookie_headers = resp.headers.get_all("Set-Cookie") or []
                for c in cookie_headers:
                    parts = c.split(";")[0].split("=", 1)
                    if len(parts) == 2:
                        self._cookie_jar[parts[0].strip()] = parts[1].strip()

                body = resp.read().decode("utf-8")
                return json.loads(body), None
        except Exception as e:
            return None, str(e)

    def check_commons_existence(self, filename: str) -> bool:
        """
        Queries Commons API to check if a file exists globally:
        https://commons.wikimedia.org/w/api.php?action=query&titles=File:...
        """
        cleaned = self.clean_filename(filename)
        params = {
            "action": "query",
            "titles": f"File:{cleaned}",
            "prop": "imageinfo",
        }
        res, err = self._query_api(self.commons_api, params)
        if not res or err:
            return False

        pages = res.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if str(page_id) != "-1" and "missing" not in page_data:
                return True
        return False

    def check_id_wiki_existence(self, filename: str) -> bool:
        """
        Queries id.wikipedia.org API to check if file already exists locally or via Commons.
        """
        cleaned = self.clean_filename(filename)
        params = {
            "action": "query",
            "titles": f"File:{cleaned}",
            "prop": "imageinfo",
        }
        res, err = self._query_api(self.id_wiki_api, params)
        if not res or err:
            return False

        pages = res.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if str(page_id) != "-1" and "missing" not in page_data:
                return True
            if page_data.get("imagerepository") == "shared" or "imageinfo" in page_data:
                return True
        return False

    def check_en_wiki_existence(self, filename: str) -> Tuple[bool, Optional[str]]:
        """
        Queries en.wikipedia.org to check if file exists locally, and returns its download URL if available.
        """
        cleaned = self.clean_filename(filename)
        params = {
            "action": "query",
            "titles": f"File:{cleaned}",
            "prop": "imageinfo",
            "iiprop": "url",
        }
        res, err = self._query_api(self.en_wiki_api, params)
        if not res or err:
            return False, None

        pages = res.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if str(page_id) != "-1" and "missing" not in page_data:
                imageinfo = page_data.get("imageinfo", [])
                url = imageinfo[0].get("url") if imageinfo else None
                return True, url
        return False, None

    def extract_media_references(self, wikitext: str) -> List[Tuple[str, str]]:
        """
        Extracts all media file references from wikitext (infoboxes and [[File:...]] / [[Berkas:...]]).
        Returns list of tuples: (filename, context_type).
        """
        results: List[Tuple[str, str]] = []
        seen: Set[str] = set()

        # 1. Look for image parameters in infobox or templates
        # Matches: | image = Foo.jpg, | poster = Foo.png, | logo = Foo.svg, | cover = Foo.jpg
        param_pattern = re.compile(
            r"\|\s*(?:image|gambar|poster|cover|logo|sampul|foto)\s*=\s*([^|\n}]+)",
            re.IGNORECASE,
        )
        for m in param_pattern.finditer(wikitext):
            val = m.group(1).strip()
            # Clean comments and nested templates if any
            val = re.sub(r"<!--[\s\S]*?-->", "", val).strip()
            if not val:
                continue
            cleaned = self.clean_filename(val)
            if cleaned and cleaned not in seen:
                # Basic check if it has an image extension or looks like a file
                exts = (".jpg", ".jpeg", ".png", ".svg", ".gif", ".webp", ".tif", ".tiff", ".ogg", ".ogv")
                if any(cleaned.lower().endswith(ext) for ext in exts) or "file:" in val.lower() or "berkas:" in val.lower():
                    seen.add(cleaned)
                    results.append((cleaned, "infobox"))

        # 2. Look for [[File:...]] / [[Berkas:...]] / [[Image:...]] / [[Gambar:...]]
        link_pattern = re.compile(
            r"\[\[\s*(?:File|Berkas|Image|Gambar)\s*:\s*([^\]|]+)",
            re.IGNORECASE,
        )
        for m in link_pattern.finditer(wikitext):
            raw_name = m.group(1).strip()
            cleaned = self.clean_filename(raw_name)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                results.append((cleaned, "wikitext_link"))

        return results
    def reconcile_media_fidelity(
        self, en_wikitext: str, id_wikitext: str
    ) -> Dict[str, Any]:
        """
        Compares media references between English source and Indonesian translation.
        Identifies missing images, their Commons/en.wiki status, and whether they need upload.
        """
        en_refs = self.extract_media_references(en_wikitext)
        id_refs = self.extract_media_references(id_wikitext)

        id_filenames = {cleaned for cleaned, _ in id_refs}
        missing_from_id: List[Dict[str, Any]] = []

        for cleaned, ctx in en_refs:
            if cleaned not in id_filenames:
                is_commons = self.check_commons_existence(cleaned)
                is_id = self.check_id_wiki_existence(cleaned)
                en_exists, dl_url = self.check_en_wiki_existence(cleaned)

                status = "unknown"
                if is_commons:
                    status = "commons_shared"
                elif is_id:
                    status = "id_wiki_exists"
                elif en_exists:
                    status = "local_non_free"
                else:
                    status = "not_found"

                missing_from_id.append({
                    "filename": cleaned,
                    "context": ctx,
                    "status": status,
                    "is_commons": is_commons,
                    "is_id_wiki": is_id,
                    "download_url": dl_url,
                })

        return {
            "source_count": len(en_refs),
            "target_count": len(id_refs),
            "missing_count": len(missing_from_id),
            "missing_items": missing_from_id,
        }

    def generate_fair_use_rationale(
        self,
        title: str,
        id_title: str,
        filename: str,
        media_type: str = "film",
    ) -> str:
        """
        Generates Indonesian Fair-Use rationale wikitext:
        {{Dari|en|{cleaned_file}}}

        == Ringkasan ==
        {{Non-free use rationale
        | Article = {id_title}
        | Description = {desc_label}
        | Source = [[:en:File:{cleaned_file}]]
        | Portion = Seluruh poster
        | Low_resolution = Ya
        | Purpose = Kotak info
        | Replaceability = Tidak ada materi bebas yang setara
        }}

        == Lisensi ==
        {type_tag}
        """
        cleaned_file = self.clean_filename(filename)

        type_tag = "{{Poster film}}"
        desc_label = f"Poster resmi untuk film/karya {title}"
        if media_type in ("album", "music", "musik"):
            type_tag = "{{Sampul album}}"
            desc_label = f"Sampul album/lagu resmi untuk karya {title}"
        elif media_type in ("logo", "brand"):
            type_tag = "{{Logo nonbebas}}"
            desc_label = f"Logo resmi untuk {title}"

        rationale = (
            f"{{{{Dari|en|{cleaned_file}}}}}\n\n"
            "== Ringkasan ==\n"
            "{{Non-free use rationale\n"
            f"| Article = {id_title}\n"
            f"| Description = {desc_label}\n"
            f"| Source = [[:en:File:{cleaned_file}]]\n"
            "| Portion = Seluruh poster\n"
            "| Low_resolution = Ya\n"
            "| Purpose = Kotak info\n"
            "| Replaceability = Tidak ada materi bebas yang setara\n"
            "}}\n\n"
            "== Lisensi ==\n"
            f"{type_tag}"
        )
        return rationale

    def audit_article_media(
        self,
        arg1: str = "",
        arg2: str = "",
        wikitext: Optional[str] = None,
        en_title: Optional[str] = None,
        id_title: Optional[str] = None,
        default_media_type: str = "film",
    ) -> List[MediaAuditItem]:
        """
        Audits all media files referenced in an article wikitext.
        Supports both signatures:
        1. audit_article_media(wikitext, en_title="", id_title="", default_media_type="film")
        2. audit_article_media(title, wikitext)
        """
        # Determine whether first arg is title or wikitext
        # If arg2 is provided and wikitext is not, check if arg1 looks like a title or arg2 looks like wikitext
        resolved_wikitext = ""
        resolved_en_title = ""
        resolved_id_title = ""

        if wikitext is not None:
            resolved_wikitext = wikitext
            resolved_en_title = en_title or arg1 or "karya"
            resolved_id_title = id_title or resolved_en_title
        elif arg2:
            # Check if arg2 has newline or wikitext patterns like {{ or [[
            if "\n" in arg2 or "{{" in arg2 or "[[" in arg2 or len(arg2) > len(arg1):
                # signature: audit_article_media(title, wikitext)
                resolved_en_title = arg1
                resolved_id_title = id_title or arg1
                resolved_wikitext = arg2
            else:
                # signature: audit_article_media(wikitext, en_title)
                resolved_wikitext = arg1
                resolved_en_title = arg2
                resolved_id_title = id_title or arg2
        else:
            resolved_wikitext = arg1
            resolved_en_title = en_title or "karya"
            resolved_id_title = id_title or resolved_en_title

        refs = self.extract_media_references(resolved_wikitext)
        items: List[MediaAuditItem] = []
        for raw_name, ctx in refs:
            cleaned = self.clean_filename(raw_name)
            item = MediaAuditItem(
                raw_filename=raw_name,
                cleaned_filename=cleaned,
                source_context=ctx,
            )

            # 1. Check Commons
            if self.check_commons_existence(cleaned):
                item.is_commons = True
                item.status = "commons_shared"
            # 2. Check id.wiki
            elif self.check_id_wiki_existence(cleaned):
                item.is_id_wiki = True
                item.status = "id_wiki_exists"
            else:
                # 3. Check en.wiki
                en_exists, dl_url = self.check_en_wiki_existence(cleaned)
                if en_exists:
                    item.status = "local_non_free"
                    item.download_url = dl_url
                    # Detect media type from filename
                    lower = cleaned.lower()
                    m_type = default_media_type
                    if "logo" in lower:
                        m_type = "logo"
                    elif "album" in lower or "cover" in lower:
                        m_type = "album"

                    item.rationale = self.generate_fair_use_rationale(
                        title=resolved_en_title,
                        id_title=resolved_id_title,
                        filename=cleaned,
                        media_type=m_type,
                    )
                else:
                    item.status = "not_found"

            items.append(item)

        return items

    def download_en_media(self, filename: str, output_dir: Path) -> Optional[Path]:
        """
        Downloads a media file from en.wikipedia.org to output_dir.
        """
        cleaned = self.clean_filename(filename)
        en_exists, dl_url = self.check_en_wiki_existence(cleaned)
        if not en_exists or not dl_url:
            return None

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        dest_path = output_dir / cleaned

        headers = {"User-Agent": self.user_agent}
        req = urllib.request.Request(dl_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = resp.read()
                dest_path.write_bytes(data)
                return dest_path
        except Exception:
            return None

    def _authenticate_bot_password(
        self, username: str, bot_password: str
    ) -> Tuple[bool, Optional[str]]:
        """Authenticates using MediaWiki Bot Password on id.wikipedia.org."""
        # 1. Fetch login token
        token_payload, err = self._query_api(
            self.id_wiki_api,
            {"action": "query", "meta": "tokens", "type": "login"},
            method="GET",
        )
        if err or not token_payload:
            return False, f"Failed to get login token: {err}"

        login_token = (
            token_payload.get("query", {}).get("tokens", {}).get("logintoken")
        )
        if not login_token:
            return False, "Login token not found in API response"

        # 2. Post login
        login_params = {
            "action": "login",
            "lgname": username,
            "lgpassword": bot_password,
            "lgtoken": login_token,
        }
        resp, login_err = self._query_api(self.id_wiki_api, login_params, method="POST")
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
        """Fetches CSRF token for edit/upload actions."""
        payload, err = self._query_api(
            self.id_wiki_api,
            {"action": "query", "meta": "tokens", "type": "csrf"},
            method="GET",
        )
        if err or not payload:
            return None, err

        token = payload.get("query", {}).get("tokens", {}).get("csrftoken")
        if not token:
            return None, "CSRF token not present in query tokens"
        return token, None

    def upload_to_id_wiki(
        self,
        filename: str,
        file_path: Path,
        wikitext_description: str,
        username: str,
        bot_password: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Uploads a local file to id.wikipedia.org using action=upload with CSRF token and multipart form-data.
        """
        file_path = Path(file_path)
        if not file_path.is_file():
            return {"success": False, "error": f"File not found: {file_path}"}

        cleaned_filename = self.clean_filename(filename)

        # Authenticate
        login_ok, login_err = self._authenticate_bot_password(username, bot_password)
        if not login_ok:
            return {"success": False, "error": f"Authentication failed: {login_err}"}

        # Obtain CSRF token
        csrf_token, token_err = self._get_csrf_token()
        if not csrf_token:
            return {"success": False, "error": f"Failed to obtain CSRF token: {token_err}"}

        file_bytes = file_path.read_bytes()
        upload_comment = comment or f"Mengunggah berkas nonbebas untuk {cleaned_filename}"

        # Construct multipart/form-data
        boundary = "----WebKitFormBoundaryWikiTranslatorMediaManager"
        body = bytearray()

        fields = {
            "action": "upload",
            "filename": cleaned_filename,
            "comment": upload_comment,
            "text": wikitext_description,
            "token": csrf_token,
            "format": "json",
            "ignorewarnings": "1",
        }

        for k, v in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
            body.extend(f"{v}\r\n".encode("utf-8"))

        # Append file part
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="file"; filename="{cleaned_filename}"\r\n'.encode("utf-8")
        )
        body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
        body.extend(file_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        content_type = f"multipart/form-data; boundary={boundary}"
        res, err = self._query_api(
            self.id_wiki_api,
            params={},
            method="POST",
            data_bytes=bytes(body),
            content_type=content_type,
        )

        if err or not res:
            return {"success": False, "error": f"Upload request failed: {err}"}

        if "error" in res:
            return {"success": False, "error": res["error"].get("info", "MediaWiki API error"), "response": res}

        upload_result = res.get("upload", {})
        result_status = upload_result.get("result")
        if result_status == "Success":
            return {"success": True, "upload": upload_result}
        else:
            return {"success": False, "result": result_status, "response": upload_result}


default_media_manager = MediaManager()
