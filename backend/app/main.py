"""FastAPI app for the Rental Agreement Red-Flag Checker."""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from .analyzer import Analyzer
from .config import Settings
from .document import DocumentError
from .llm import LLMError, OpenAICompatibleLLM
from .schemas import Analysis
from .store import StoreError, build_store

log = logging.getLogger("uvicorn.error")
ERROR_LOG = os.getenv("LLM_ERROR_LOG", "llm_errors.log")  # relative to where uvicorn runs (backend/)


def record_llm_error(e: Exception) -> None:
    """Print the provider's real error to the server log and append it to a local file for debugging."""
    log.warning("LLM call failed: %s", e)
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {e}\n")
    except OSError:
        pass

settings = Settings.from_env()
fallback_models = [x.strip() for x in settings.llm_fallback_models.split(",") if x.strip()]
store = build_store(settings.supabase_url, settings.supabase_service_key, settings.retention_days)
analyzer = (
    Analyzer(OpenAICompatibleLLM(settings.llm_api_key, settings.llm_base_url, settings.llm_model,
                                 settings.llm_timeout_s, fallback_models), settings)
    if settings.llm_api_key else None
)

app = FastAPI(title="Rental Agreement Red-Flag Checker", version="1.0.0")
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_methods=["GET", "POST"],
                   allow_headers=["*"])


class RateLimiter:
    def __init__(self, limit: int, window_s: int):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


limiter = RateLimiter(settings.rate_limit_per_10min, 600)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")



def parser_or_analyzer_models() -> list[str]:
    return analyzer.llm.models if analyzer is not None else []

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "models": parser_or_analyzer_models(), "llm_configured": analyzer is not None, "store": store.name}


@app.post("/api/analyze", response_model=Analysis)
async def analyze(request: Request, file: UploadFile = File(...)) -> Analysis:
    if not limiter.allow(_client_ip(request)):
        raise HTTPException(429, "Too many analyses from your network. Please try again in a few minutes.")
    if analyzer is None:
        raise HTTPException(503, "The AI model is not configured on the server.")
    name = file.filename or "agreement.pdf"
    if not name.lower().endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(400, "Please upload a PDF file.")
    data = await file.read(int(settings.max_pdf_mb * 1024 * 1024) + 1)
    try:
        # PDF parsing and the LLM call are blocking; keep them off the event loop.
        result = await run_in_threadpool(analyzer.analyze_pdf, data, name)
    except DocumentError as e:
        raise HTTPException(400, str(e)) from e
    except LLMError as e:
        record_llm_error(e)
        if "HTTP 429" in str(e):  # every model we tried was busy or rate-limited
            raise HTTPException(503, "The free AI model is busy or today's request limit is used up. "
                                     "Please try again in a minute.") from e
        raise HTTPException(502, "The AI model didn't return a usable analysis. Please try again.") from e
    try:
        return await run_in_threadpool(store.save, result)
    except StoreError:
        return result  # still show the analysis; it just won't have a share link


@app.get("/api/analyses/{analysis_id}", response_model=Analysis)
def get_analysis(analysis_id: str) -> Analysis:
    try:
        a = store.get(analysis_id)
    except StoreError as e:
        raise HTTPException(502, "Storage is unavailable right now.") from e
    if a is None:
        raise HTTPException(404, "This analysis doesn't exist or has expired.")
    return a
