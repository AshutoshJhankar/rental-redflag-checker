"""PDF -> pages -> clauses, plus PII masking and quote verification."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class DocumentError(ValueError):
    """A problem with the uploaded file that the user can fix."""


@dataclass
class Clause:
    id: str
    page: int
    text: str


# ---------- PDF ----------

def extract_pages(data: bytes, max_pages: int) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("This PDF is password-protected. Remove the password and try again.")
        n = len(reader.pages)
    except PdfReadError as e:
        raise DocumentError("This file doesn't look like a valid PDF.") from e
    if n == 0:
        raise DocumentError("The PDF has no pages.")
    if n > max_pages:
        raise DocumentError(f"The PDF has {n} pages; the limit is {max_pages}.")
    pages = [(p.extract_text() or "") for p in reader.pages]
    if sum(len(p.strip()) for p in pages) < 300:
        raise DocumentError(
            "No readable text found. This looks like a scanned or photographed agreement; "
            "please upload a text-based PDF (for example, the one you received by email)."
        )
    return pages


# ---------- clauses ----------

_CLAUSE_START = re.compile(
    r"^\s*(?:(?:clause|article|section)\s+\d+|\d{1,2}(?:\.\d{1,2})*\s*[.)]\s|\(?[a-h]\)\s|\(?(?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\)\s)",
    re.I,
)
MIN_CLAUSE, MAX_CLAUSE = 40, 1400


def segment_clauses(pages: list[str]) -> list[Clause]:
    raw: list[tuple[int, str]] = []
    buf: list[str] = []
    buf_page = 1

    def flush() -> None:
        nonlocal buf
        text = " ".join(buf).strip()
        if text:
            raw.append((buf_page, re.sub(r"\s+", " ", text)))
        buf = []

    for page_no, text in enumerate(pages, start=1):
        for line in text.splitlines():
            if not line.strip():
                if buf and sum(len(b) for b in buf) > 200:
                    flush()
                continue
            if _CLAUSE_START.match(line) and buf:
                flush()
            if not buf:
                buf_page = page_no
            buf.append(line.strip())
    flush()

    # Merge headings / fragments into the next clause, split very long clauses on sentences.
    merged: list[tuple[int, str]] = []
    carry = ""
    carry_page = None
    for page, text in raw:
        if len(text) < MIN_CLAUSE:
            carry = f"{carry} {text}".strip()
            carry_page = carry_page or page
            continue
        if carry:
            text, page, carry, carry_page = f"{carry} {text}", carry_page, "", None
        merged.extend((page, part) for part in _split_long(text))
    if carry:
        if merged:
            p, t = merged[-1]
            merged[-1] = (p, f"{t} {carry}")
        else:
            merged.append((carry_page or 1, carry))

    return [Clause(id=f"C{i}", page=p, text=t) for i, (p, t) in enumerate(merged, start=1)]


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CLAUSE:
        return [text]
    parts, cur = [], ""
    for sentence in re.split(r"(?<=[.;])\s+", text):
        if cur and len(cur) + len(sentence) > MAX_CLAUSE:
            parts.append(cur.strip())
            cur = ""
        cur += sentence + " "
    if cur.strip():
        parts.append(cur.strip())
    return parts


# ---------- PII masking (before anything leaves the server) ----------

_PII = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?<![\w,.])(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b")),
    ("ACCOUNT", re.compile(r"(?<![\w,.])\d{9,18}\b")),
]


def mask_pii(text: str) -> tuple[str, int]:
    count = 0
    for label, pattern in _PII:
        text, n = pattern.subn(f"[{label}]", text)
        count += n
    return text, count


# ---------- quote verification ----------

def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[‘’´`]", "'", s)
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"[^a-z0-9%₹]+", " ", s)
    return " ".join(s.split())


def locate_quote(quote: str | None, clauses: list[Clause], hint: str | None = None,
                 threshold: float = 0.88) -> Clause | None:
    """Return the clause that really contains `quote` (exact after normalisation, else fuzzy)."""
    if not quote:
        return None
    q = normalize(quote)
    if len(q) < 12:
        return None
    ordered = sorted(clauses, key=lambda c: c.id != hint)
    for c in ordered:
        if q in normalize(c.text):
            return c
    q_words = q.split()
    q_set = set(q_words)
    n = len(q_words)
    for c in ordered:
        words = normalize(c.text).split()
        if len(q_set & set(words)) < 0.6 * len(q_set):
            continue  # cheap pre-filter
        for i in range(0, max(1, len(words) - n + 1)):
            window = " ".join(words[i : i + n])
            m = SequenceMatcher(None, window, q)
            if m.quick_ratio() >= threshold and m.ratio() >= threshold:
                return c
    return None


# ---------- numbers inside quotes ----------

_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "thirty": 30,
}
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|k\b)?", re.I)


def numbers_in(text: str) -> set[float]:
    found: set[float] = set()
    for m in _NUM.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        if unit.startswith(("lakh", "lac")):
            v *= 100_000
        elif unit == "k":
            v *= 1_000
        found.add(v)
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in _WORD_NUM:
            found.add(float(_WORD_NUM[w]))
    return found
