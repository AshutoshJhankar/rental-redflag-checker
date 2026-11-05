"""Tests with a scripted LLM: no network or API key needed."""
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.analyzer import Analyzer  # noqa: E402
from app.config import Settings  # noqa: E402
from app.document import (DocumentError, extract_pages, locate_quote, mask_pii, numbers_in,  # noqa: E402
                          segment_clauses)
from app.llm import LLMError, parse_json_reply  # noqa: E402
from app.store import MemoryStore, SupabaseStore  # noqa: E402
from evals.run_eval import score  # noqa: E402

SETTINGS = Settings(llm_api_key="test")
RISKY = (ROOT / "samples/risky-agreement.pdf").read_bytes()
FAIR = (ROOT / "samples/fair-agreement.pdf").read_bytes()


class ScriptedLLM:
    name = "scripted"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete_json(self, messages):
        self.calls.append(messages)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def term(value, quote, cid):
    return {"value": value, "quote": quote, "clause_id": cid}


RISKY_REPLY = {
    "key_terms": {
        "monthly_rent": term(40000, "The monthly rent is Rs. 40,000 (Rupees Forty Thousand only)", "C4"),
        "security_deposit": term(400000, "a security deposit of Rs. 4,00,000 (Rupees Four Lakh only)", "C5"),
        "lock_in_months": term(11, "shall not vacate the premises before the expiry of eleven (11) months", "C6"),
        "notice_tenant_months": term(3, "The Tenant shall give three (3) months' written notice", "C7"),
        "notice_landlord_months": term(0.5, "vacate by giving fifteen (15) days' notice", "C7"),
        "rent_escalation_percent": term(15, "The monthly rent shall be increased by 15% on renewal", "C8"),
        "maintenance_monthly": term(4000, "monthly maintenance of Rs. 4,000", "C12"),
        "agreement_months": term(11, "for a period of eleven (11) months", "C3"),
    },
    "flags": [
        {"category": "penalties", "severity": "high", "title": "Deposit forfeited if you leave early",
         "explanation": "Leaving even one month early means losing the whole deposit.",
         "quote": "the entire security deposit shall be forfeited", "clause_id": "C6",
         "suggestion": "Replace forfeiture with rent for the notice period."},
        {"category": "entry_privacy", "severity": "medium", "title": "Owner can enter any time",
         "explanation": "The owner can walk in without telling you.",
         "quote": "may enter the premises at any time for inspection without prior notice", "clause_id": "C10",
         "suggestion": "Ask for 24 hours' notice."},
        {"category": "deposit", "severity": "low", "title": "Deposit is high",
         "explanation": "Ten months is a lot.", "quote": "a security deposit of Rs. 4,00,000", "clause_id": "C5",
         "suggestion": "Negotiate."},
        {"category": "termination", "severity": "high", "title": "Invented clause",
         "explanation": "This quote does not exist in the document at all.",
         "quote": "the landlord may change the locks whenever he wishes", "clause_id": "C9",
         "suggestion": "Ask to remove it."},
        {"category": "missing_protection", "severity": "high", "title": "No refund deadline",
         "explanation": "Nothing says when the deposit comes back.", "quote": None, "clause_id": None,
         "suggestion": "Add a 15-day refund deadline."},
    ],
}


def analyze(reply, pdf=RISKY):
    llm = ScriptedLLM(reply if isinstance(reply, list) else [reply])
    return Analyzer(llm, SETTINGS).analyze_pdf(pdf, "risky.pdf"), llm


# ---------- document handling ----------

def test_segments_numbered_clauses():
    clauses = segment_clauses(extract_pages(RISKY, 25))
    assert len(clauses) == 13
    assert clauses[3].text.startswith("3. Rent")


def test_rejects_non_pdf_and_scans():
    with pytest.raises(DocumentError):
        extract_pages(b"not a pdf", 25)
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(10, 10, 100, 100)  # a page with no text, like a scan
    c.save()
    with pytest.raises(DocumentError, match="scanned"):
        extract_pages(buf.getvalue(), 25)


def test_masks_pii():
    text, n = mask_pii("PAN ABCDE1234F, call +91 98450 12345 or 9876543210, mail a.b@x.com, "
                       "Aadhaar 1234 5678 9012, rent Rs. 25,000 and deposit Rs. 1,50,000")
    assert n == 5
    assert "ABCDE1234F" not in text and "98450" not in text and "a.b@x.com" not in text
    assert "25,000" in text and "1,50,000" in text  # money survives


def test_quote_location_exact_fuzzy_and_missing():
    clauses = segment_clauses(extract_pages(RISKY, 25))
    assert locate_quote("may enter the premises at any time", clauses).id == "C10"
    # small differences (quotes, punctuation, one changed word) still match
    assert locate_quote("The Tenant shall bear the cost of all repairs to the premise, including plumbing",
                        clauses).id == "C9"
    assert locate_quote("the landlord may change the locks whenever he wishes", clauses) is None
    assert locate_quote("short", clauses) is None


def test_indian_money_format():
    from app.analyzer import inr, months_text
    assert inr(150000) == "₹1,50,000" and inr(25000) == "₹25,000" and inr(999) == "₹999" and inr(12345678) == "₹1,23,45,678"
    assert months_text(0.5) == "15 days" and months_text(1) == "1 month" and months_text(3) == "3 months"


def test_numbers_in_handles_indian_formats():
    assert 150000 in numbers_in("Rs. 1,50,000/-")
    assert 150000 in numbers_in("1.5 lakh")
    assert 3 in numbers_in("three (3) months")
    assert 15 in numbers_in("fifteen days")


# ---------- analysis ----------

def test_full_analysis_verifies_scores_and_discards_hallucinations():
    a, _ = analyze(RISKY_REPLY)
    assert a.discarded_flags == 1  # the invented "change the locks" clause
    assert all(f.title != "Invented clause" for f in a.flags)
    assert a.key_terms["security_deposit"].verified and a.deposit_months == 10.0
    assert a.key_terms["notice_landlord_months"].verified  # 15 days -> 0.5 months
    cats = {f.category for f in a.flags}
    assert {"deposit", "lock_in", "notice_period", "rent_escalation", "penalties", "entry_privacy"} <= cats
    dep = next(f for f in a.flags if f.category == "deposit")
    assert dep.source == "rule" and dep.severity == "high" and dep.title == "Deposit is 10 months of rent" and "₹4,00,000" in dep.explanation  # rule replaced AI flag
    missing = next(f for f in a.flags if f.category == "missing_protection")
    assert missing.severity == "medium" and missing.quote is None
    assert a.risk_level == "high" and a.risk_score == 100
    assert a.masked_items == 4
    assert [f.severity for f in a.flags] == sorted([f.severity for f in a.flags],
                                                   key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])


def test_wrong_value_is_not_verified():
    reply = json.loads(json.dumps(RISKY_REPLY))
    reply["key_terms"]["security_deposit"]["value"] = 200000  # doesn't match the quoted Rs. 4,00,000
    a, _ = analyze(reply)
    assert not a.key_terms["security_deposit"].verified
    assert a.deposit_months is None


def test_fair_agreement_scores_low():
    reply = {"key_terms": {
        "monthly_rent": term(30000, "The monthly rent is Rs. 30,000", "C4"),
        "security_deposit": term(60000, "security deposit of Rs. 60,000", "C5"),
        "lock_in_months": term(2, "lock-in period of two (2) months", "C7"),
        "notice_tenant_months": term(1, "giving one (1) month's written notice", "C8"),
        "notice_landlord_months": term(1, "giving one (1) month's written notice", "C8"),
        "rent_escalation_percent": term(5, "with an increase of 5% on the monthly rent", "C10"),
    }, "flags": []}
    a, _ = analyze(reply, pdf=FAIR)
    assert a.flags == [] and a.risk_level == "low" and a.deposit_months == 2.0


def test_malformed_flag_is_dropped_not_fatal():
    reply = json.loads(json.dumps(RISKY_REPLY))
    reply["flags"].append({"category": "nonsense", "severity": "extreme"})
    reply["key_terms"]["agreement_months"] = "eleven"  # malformed term -> treated as unknown
    a, llm = analyze(reply)
    assert len(llm.calls) == 1 and a.discarded_flags == 2  # invented quote + malformed item
    assert a.key_terms["agreement_months"].value is None


def test_invalid_output_gets_one_repair():
    bad = {"key_terms": [], "flags": "oops"}
    a, llm = analyze([bad, RISKY_REPLY])
    assert len(llm.calls) == 2 and "failed validation" in llm.calls[1][-1]["content"]
    assert a.flags


def test_gives_up_after_second_invalid_output():
    bad = {"flags": "not a list"}
    with pytest.raises(LLMError):
        analyze([bad, bad])


def test_provider_error_is_not_retried():
    with pytest.raises(LLMError):
        analyze([LLMError("HTTP 401: bad key"), RISKY_REPLY])


def test_parse_json_reply_tolerates_fences():
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('Here you go: {"a": 2} hope it helps') == {"a": 2}
    with pytest.raises(LLMError):
        parse_json_reply("no json here")


def test_rejects_oversized_upload():
    with pytest.raises(DocumentError, match="larger"):
        Analyzer(ScriptedLLM([]), Settings(max_pdf_mb=0.001)).analyze_pdf(RISKY, "x.pdf")


# ---------- storage ----------

def test_memory_store_roundtrip():
    a, _ = analyze(RISKY_REPLY)
    s = MemoryStore()
    saved = s.save(a)
    assert saved.id and s.get(saved.id).risk_score == a.risk_score
    assert s.get("missing") is None


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_supabase_store_requests():
    a, _ = analyze(RISKY_REPLY)
    sent = []

    def opener(req, timeout):
        sent.append(req)
        body = json.loads(req.data) if req.data else None
        row = {**(body or {"result": a.model_dump(mode="json")}),
               "id": "0b6c2a3e-1f2d-4c5b-9a8e-7d6c5b4a3f21", "created_at": "2026-11-05T10:00:00+00:00"}
        return _Resp(json.dumps([row]).encode())

    s = SupabaseStore("https://proj.supabase.co", "sb_secret_abc", opener=opener)
    saved = s.save(a)
    assert saved.id == "0b6c2a3e-1f2d-4c5b-9a8e-7d6c5b4a3f21"
    req = sent[0]
    assert req.get_method() == "POST" and req.full_url == "https://proj.supabase.co/rest/v1/analyses"
    assert req.get_header("Apikey") == "sb_secret_abc" and req.get_header("Authorization") is None
    assert req.get_header("Prefer") == "return=representation"
    assert s.get(saved.id).risk_score == a.risk_score
    assert "id=eq.0b6c2a3e" in sent[1].full_url and "expires_at=gt." in sent[1].full_url
    assert s.get("1 or 1=1") is None and len(sent) == 2  # non-UUID ids never reach the database


def test_eval_scoring():
    labels = {"x": {"expected": ["deposit", "lock_in"], "must_not": ["entry_privacy"], "expected_level": "high"}}
    results = {"x": {"flags": [{"category": "deposit", "source": "rule"}, {"category": "entry_privacy", "source": "ai"}],
                     "risk_level": "high", "discarded_flags": 1}}
    m = score(results, labels)
    assert m["category_recall"] == 0.5 and m["false_alarms"] == 1 and m["grounded_ai_flag_rate"] == 0.5
