"""Persistence for analyses: Supabase (PostgREST over HTTPS) or in-memory for local dev.

Only the analysis is stored (terms, flags, short quotes, already PII-masked). The PDF itself is never stored.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from .schemas import Analysis

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class StoreError(RuntimeError):
    pass


class Store(Protocol):
    name: str

    def save(self, a: Analysis) -> Analysis: ...
    def get(self, analysis_id: str) -> Analysis | None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(a: Analysis, retention_days: int) -> dict:
    body = a.model_dump(mode="json", exclude={"id", "created_at"})
    return {
        "file_name": a.file_name,
        "risk_score": a.risk_score,
        "risk_level": a.risk_level,
        "result": body,
        "expires_at": (_now() + timedelta(days=retention_days)).isoformat(),
    }


def _from_row(row: dict) -> Analysis:
    return Analysis.model_validate({**row["result"], "id": row["id"], "created_at": row["created_at"]})


class MemoryStore:
    name = "memory"

    def __init__(self, retention_days: int = 30):
        self._rows: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.retention_days = retention_days

    def save(self, a: Analysis) -> Analysis:
        row = {**_row(a, self.retention_days), "id": str(uuid.uuid4()), "created_at": _now().isoformat()}
        with self._lock:
            self._rows[row["id"]] = row
            while len(self._rows) > 500:
                self._rows.pop(next(iter(self._rows)))
        return _from_row(row)

    def get(self, analysis_id: str) -> Analysis | None:
        with self._lock:
            row = self._rows.get(analysis_id)
        if not row or datetime.fromisoformat(row["expires_at"]) < _now():
            return None
        return _from_row(row)


class SupabaseStore:
    name = "supabase"
    TABLE = "analyses"

    def __init__(self, url: str, service_key: str, retention_days: int = 30,
                 opener: Callable = urllib.request.urlopen, timeout_s: float = 10.0):
        self.base = f"{url.rstrip('/')}/rest/v1/{self.TABLE}"
        self.retention_days = retention_days
        self._open, self._timeout = opener, timeout_s
        self._headers = {"apikey": service_key, "Content-Type": "application/json"}
        if service_key.startswith("eyJ"):  # legacy JWT keys also go in Authorization
            self._headers["Authorization"] = f"Bearer {service_key}"

    def _request(self, method: str, url: str, body: dict | None = None, prefer: str | None = None) -> list:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
        try:
            with self._open(req, timeout=self._timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as e:
            raise StoreError(f"Supabase {method} failed: HTTP {e.code} {e.read()[:200]!r}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise StoreError(f"Supabase unreachable: {e}") from e

    def save(self, a: Analysis) -> Analysis:
        rows = self._request("POST", self.base, _row(a, self.retention_days), prefer="return=representation")
        if not rows:
            raise StoreError("Supabase returned no row")
        return _from_row(rows[0])

    def get(self, analysis_id: str) -> Analysis | None:
        if not _UUID.match(analysis_id):
            return None
        q = urllib.parse.urlencode({"id": f"eq.{analysis_id}", "expires_at": f"gt.{_now().isoformat()}",
                                    "select": "*"})
        rows = self._request("GET", f"{self.base}?{q}")
        return _from_row(rows[0]) if rows else None


def build_store(url: str, key: str, retention_days: int) -> Store:
    if url and key:
        return SupabaseStore(url, key, retention_days)
    return MemoryStore(retention_days)
