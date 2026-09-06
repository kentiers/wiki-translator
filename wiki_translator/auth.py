"""
Authentication module for Wiki Translator.

Reads Google Antigravity credentials directly from ~/.omp/agent/agent.db (provider 'google-antigravity'),
extracts access and refresh tokens, and provides automatic token refresh via https://oauth2.googleapis.com/token.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from email.utils import parsedate_to_datetime
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

ANTIGRAVITY_CLIENT_ID = os.environ.get("ANTIGRAVITY_CLIENT_ID", "")
ANTIGRAVITY_CLIENT_SECRET = os.environ.get("ANTIGRAVITY_CLIENT_SECRET", "")
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


@dataclass
class AntigravityCredential:
    id: int
    email: str
    project_id: str
    access_token: str
    refresh_token: str
    expires_at: float  # epoch timestamp in seconds
    is_exhausted: bool = False

    def is_expired(self, buffer_seconds: float = 120.0) -> bool:
        """Check if the access token is expired or about to expire."""
        return time.time() + buffer_seconds >= self.expires_at


class AuthManager:
    """Manages credentials from agent.db and handles automatic token refresh."""

    def _find_default_db(self) -> Optional[Path]:
        """Find agent.db across possible home and appdata locations."""
        if os.environ.get("PI_CODING_AGENT_DIR"):
            return Path(os.environ["PI_CODING_AGENT_DIR"]) / "agent.db"
        candidates = [
            Path.home() / ".omp" / "agent" / "agent.db",
            Path.home() / ".config" / "omp" / "agent" / "agent.db",
        ]
        if "USERPROFILE" in os.environ:
            candidates.append(Path(os.environ["USERPROFILE"]) / ".omp" / "agent" / "agent.db")
        if "APPDATA" in os.environ:
            candidates.append(Path(os.environ["APPDATA"]) / "omp" / "agent" / "agent.db")
        if "LOCALAPPDATA" in os.environ:
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "omp" / "agent" / "agent.db")

        for p in candidates:
            if p.exists():
                return p
        return candidates[0]

    def __init__(self, db_path: Optional[Path] = None):
        self.use_omp_refresh = db_path is None
        self._cooldowns: Dict[int, float] = {}
        if db_path is None:
            self.db_path = self._find_default_db() or (Path.home() / ".omp" / "agent" / "agent.db")
        else:
            self.db_path = Path(db_path)

    def load_credentials(self) -> List[AntigravityCredential]:
        """Load all google-antigravity credentials from SQLite database."""
        if not self.db_path.exists():
            return []

        credentials = []
        try:
            conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, data FROM auth_credentials WHERE provider = 'google-antigravity' ORDER BY id ASC"
            )
            rows = cursor.fetchall()
            conn.close()

            for row_id, data_raw in rows:
                try:
                    data = json.loads(data_raw)
                    access = data.get("access") or data.get("access_token") or data.get("token") or ""
                    refresh = data.get("refresh") or data.get("refresh_token") or ""
                    expires_ms = data.get("expires") or data.get("expires_at") or data.get("expiry") or 0
                    project_id = data.get("projectId") or data.get("project_id") or ""
                    email = data.get("email", f"account_{row_id}@google")

                    try:
                        expires_val = float(expires_ms)
                    except (TypeError, ValueError):
                        expires_val = 0.0

                    # Convert milliseconds to seconds if needed (e.g. 13-digit epoch timestamp)
                    expires_sec = (
                        expires_val / 1000.0 if expires_val > 10000000000 else expires_val
                    )

                    cred = AntigravityCredential(
                        id=row_id,
                        email=email,
                        project_id=project_id,
                        access_token=access,
                        refresh_token=refresh,
                        expires_at=expires_sec,
                    )
                    credentials.append(cred)
                except Exception:
                    continue
        except Exception:
            return []

        for credential in credentials:
            credential.is_exhausted = self._cooldowns.get(credential.id, 0) > time.time()
        return credentials

    def mark_unavailable(self, credential: AntigravityCredential, status: int, retry_after: Optional[str] = None) -> None:
        """Keep cooldowns across pool reloads; permission errors are not quota errors."""
        delay = 60.0 if status == 429 else 300.0
        if retry_after:
            try:
                delay = max(1.0, float(retry_after))
            except ValueError:
                try:
                    delay = max(1.0, parsedate_to_datetime(retry_after).timestamp() - time.time())
                except (ValueError, TypeError, OverflowError):
                    pass
        self._cooldowns[credential.id] = time.time() + delay
        credential.is_exhausted = True

    def _refresh_with_omp(self, credential: AntigravityCredential) -> Optional[str]:
        """Let OMP refresh its own account. Never expose token stdout/stderr."""
        accounts = self.load_credentials()
        index = next((i for i, c in enumerate(accounts, 1) if c.id == credential.id), None)
        if index is None:
            return None
        try:
            result = subprocess.run(
                ["rtk", "omp", "token", "google-antigravity", "--account", str(index), "--force-refresh"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                return None
        except (OSError, subprocess.SubprocessError):
            return None
        for updated in self.load_credentials():
            if updated.id == credential.id and not updated.is_expired():
                credential.access_token = updated.access_token
                credential.refresh_token = updated.refresh_token
                credential.expires_at = updated.expires_at
                return credential.access_token
        return None

    def refresh_access_token(self, credential: AntigravityCredential) -> Optional[str]:
        """
        Refresh access token using refresh_token and client ID/secret.
        Updates internal credential state and optionally writes back to SQLite if writable.
        """
        if self.use_omp_refresh:
            return self._refresh_with_omp(credential)
        if not credential.refresh_token:
            return None

        payload = {
            "client_id": ANTIGRAVITY_CLIENT_ID,
            "client_secret": ANTIGRAVITY_CLIENT_SECRET,
            "refresh_token": credential.refresh_token,
            "grant_type": "refresh_token",
        }

        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            TOKEN_ENDPOINT,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "antigravity/hub/2.8.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                new_access_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                # Refresh token might optionally be rotated
                if "refresh_token" in data and data["refresh_token"]:
                    credential.refresh_token = data["refresh_token"]

                if new_access_token:
                    credential.access_token = new_access_token
                    credential.expires_at = time.time() + float(expires_in)
                    credential.is_exhausted = False
                    self._persist_token_update(credential)
                    return new_access_token
        except Exception:
            return None

        return None

    def _persist_token_update(self, credential: AntigravityCredential) -> None:
        """Best-effort persist refreshed token back to agent.db."""
        if not self.db_path.exists():
            return
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM auth_credentials WHERE id = ?", (credential.id,)
            )
            row = cursor.fetchone()
            if row:
                data = json.loads(row[0])
                data["access"] = credential.access_token
                data["refresh"] = credential.refresh_token
                if "refresh_token" in data:
                    data["refresh_token"] = credential.refresh_token
                data["expires"] = int(credential.expires_at * 1000)
                cursor.execute(
                    "UPDATE auth_credentials SET data = ?, updated_at = CAST(strftime('%s','now') AS INTEGER) WHERE id = ?",
                    (json.dumps(data), credential.id),
                )
                conn.commit()
            conn.close()
        except Exception:
            pass

    def get_active_credential(
        self, prefer_fresh: bool = True
    ) -> Optional[AntigravityCredential]:
        """
        Returns a valid, non-exhausted credential.
        Automatically refreshes if expired.
        """
        credentials = self.load_credentials()
        if not credentials:
            return None

        for cred in credentials:
            if cred.is_exhausted:
                continue

            if cred.is_expired():
                new_tok = self.refresh_access_token(cred)
                if not new_tok:
                    continue

            return cred

        return None

    def get_credential_pool(self) -> List[AntigravityCredential]:
        """Return the OMP pool in database order; callers rotate on quota errors."""
        return [c for c in self.load_credentials() if not c.is_exhausted]
