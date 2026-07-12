"""
Live-mode config + error-path tests.

The happy live path needs a real API key and network egress, so it isn't run
here; instead we cover the *plumbing*: the /config capability flip, and every
failure mode turning into a clean CaseError → HTTP status (never a stack trace).
The live upstreams (MyVariant.info + Anthropic) are stubbed so no real network
or key is touched.
"""

import pytest

from web.api import service
from web.api.evidence import (
    EvidenceNotFound,
    EvidenceParseError,
    EvidenceUpstreamError,
    summarize_clinvar,
)


# --------------------------- config flip ------------------------------------


def test_config_live_available_flips_with_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/config").json()["live_available"] is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert client.get("/config").json()["live_available"] is True


# --------------------------- auto-routing decision --------------------------
# The client never chooses offline vs. live — it just sends the variant. These
# assert the server-side routing: bundled -> offline, else key -> live, else a
# clean, distinguishable signal. None of these requests carry a `live` flag.


def test_bundled_hgvs_classifies_offline_even_with_a_key(client, monkeypatch):
    # A key is present, but a bundled variant must still be replayed offline
    # (instant, no upstream). Guard the live path so an accidental route errors
    # instead of hitting the real network.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _stub_fetch(monkeypatch, EvidenceUpstreamError("live path must not be taken"))

    r = client.post("/classify", json={"hgvs": "c.665C>T"})  # no live flag
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "replay"
    assert body["id"] == "mthfr_c665CtoT"


def test_nonbundled_hgvs_auto_routes_to_live_when_key_present(client, monkeypatch):
    # No `live` flag, but a key is set and the variant isn't bundled -> the
    # server must take the live path on its own. We prove it did by stubbing the
    # live evidence fetch to fail: a 404 here can only come from the live route
    # (the old behavior returned 422 "bundled" without an explicit live flag).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _stub_fetch(monkeypatch, EvidenceNotFound("No record for 'X' in MyVariant.info."))

    r = client.post("/classify", json={"hgvs": "chr17:g.999A>T"})  # no live flag
    assert r.status_code == 404
    assert "no record" in r.json()["detail"].lower()


def test_nonbundled_hgvs_without_key_is_clean_and_mode_free(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/classify", json={"hgvs": "rs1801133"})  # no live flag, no key
    assert r.status_code == 422
    detail = r.json()["detail"].lower()
    assert "bundled" in detail          # points the user back to the always-works path
    assert "live mode" not in detail    # the offline/live "mode" concept is gone
    assert "Traceback" not in r.text


# --------------------------- live error paths -------------------------------
# The corrected adapter (web/api/evidence.py) raises three DISTINCT error types;
# we stub its fetch() to prove each maps to a distinguishable status + message,
# with no real network or key touched (fetch fails before any LLM call).


def _stub_fetch(monkeypatch, exc: Exception):
    def _fetch(self):
        raise exc

    monkeypatch.setattr(service.MyVariantEvidence, "fetch", _fetch, raising=True)


def test_live_without_key_is_400(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/classify", json={"hgvs": "chr17:g.999A>T", "live": True})
    assert r.status_code == 400
    assert "api key" in r.json()["detail"].lower()


def test_live_variant_not_found_is_404(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _stub_fetch(monkeypatch, EvidenceNotFound("No record for 'X' in MyVariant.info (assembly hg38)."))
    r = client.post("/classify", json={"hgvs": "chr17:g.999A>T", "live": True})
    assert r.status_code == 404
    assert "no record" in r.json()["detail"].lower()


def test_live_source_unreachable_is_502(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _stub_fetch(monkeypatch, EvidenceUpstreamError("Couldn't reach MyVariant.info: dns."))
    r = client.post("/classify", json={"hgvs": "chr17:g.999A>T", "live": True})
    assert r.status_code == 502
    assert "unavailable" in r.json()["detail"].lower()
    assert "Traceback" not in r.text  # never a stack trace


def test_live_timeout_is_504(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _stub_fetch(monkeypatch, EvidenceUpstreamError("MyVariant.info timed out.", timeout=True))
    r = client.post("/classify", json={"hgvs": "chr17:g.999A>T", "live": True})
    assert r.status_code == 504
    assert "timed out" in r.json()["detail"].lower()


def test_live_parse_failure_is_502_and_distinct(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _stub_fetch(monkeypatch, EvidenceParseError("not valid JSON"))
    r = client.post("/classify", json={"hgvs": "chr17:g.999A>T", "live": True})
    assert r.status_code == 502
    assert "parsed" in r.json()["detail"].lower()


def test_invalid_assembly_is_422(client):
    r = client.post("/classify", json={"case_id": "brca1_c5266dupC", "assembly": "hg99"})
    assert r.status_code == 422


# --------------------------- input / VCF robustness -------------------------


def test_classify_empty_body_is_422(client):
    r = client.post("/classify", json={"hgvs": "", "case_id": ""})
    assert r.status_code == 422


def test_triage_vcf_empty_file_reports_no_records(client):
    r = client.post(
        "/triage/vcf",
        files={"file": ("empty.vcf", b"##fileformat=VCFv4.2\n", "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["matched"] == 0
    assert "no variant records" in (body["note"] or "").lower()


def test_triage_vcf_garbage_does_not_crash(client):
    r = client.post(
        "/triage/vcf",
        files={"file": ("junk.txt", b"this is not,a;vcf\nrandom text\n", "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_unhandled_error_is_clean_json(monkeypatch):
    # Force an unexpected error inside a route and assert it's a friendly 500.
    # A non-raising client so the transport returns the handler's response
    # instead of re-surfacing the exception into the test.
    from fastapi.testclient import TestClient

    from web.api.main import app

    def _boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(service, "classify", _boom)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/classify", json={"case_id": "brca1_c5266dupC"})
    assert r.status_code == 500
    assert "went wrong" in r.json()["detail"].lower()
    assert "kaboom" not in r.text  # internal detail not leaked


@pytest.mark.parametrize("cid", ["", "  ", "nope/../etc"])
def test_ledger_bad_id_is_handled(client, cid):
    r = client.get(f"/ledger/{cid}")
    # 404 (unknown/absent case) or 200 empty — never a 500 crash
    assert r.status_code in (200, 404, 422)


# --------------------------- ClinVar assertion summary ----------------------
# Clean, single-classification ClinVar line instead of a raw concatenation.


def test_clinvar_single_value():
    r = summarize_clinvar(
        {"clinical_significance": "Benign",
         "review_status": "criteria provided, multiple submitters, no conflicts",
         "number_submitters": 4}
    )
    assert r["headline"] == "Benign"
    assert r["conflicting"] is False
    assert ";" not in r["snippet"]  # not a concatenation
    assert r["snippet"] == "ClinVar: Benign (multiple submitters, no conflicts)."


def test_clinvar_duplicate_list_dedupes_to_one():
    r = summarize_clinvar(
        [
            {"clinical_significance": "Benign", "review_status": "criteria provided, single submitter"},
            {"clinical_significance": "Benign", "review_status": "reviewed by expert panel"},
            {"clinical_significance": "Benign", "review_status": "criteria provided, single submitter"},
        ]
    )
    assert r["headline"] == "Benign"
    assert r["conflicting"] is False
    assert r["raw_significances"] == ["Benign"]  # deduped, not "Benign; Benign; Benign"
    assert "expert-panel" in r["snippet"]  # weighted by the highest review status


def test_clinvar_explicit_conflict():
    r = summarize_clinvar(
        {"clinical_significance": "Conflicting interpretations of pathogenicity",
         "review_status": "criteria provided, conflicting interpretations"}
    )
    assert r["conflicting"] is True
    assert r["headline"] == "Conflicting interpretations"
    assert "conflicting" in r["snippet"].lower()


def test_clinvar_opposed_values_are_conflicting():
    r = summarize_clinvar(
        [
            {"clinical_significance": "Benign", "review_status": "criteria provided, single submitter"},
            {"clinical_significance": "Pathogenic", "review_status": "criteria provided, single submitter"},
        ]
    )
    assert r["conflicting"] is True
    assert r["headline"] == "Conflicting interpretations"


def test_clinvar_expert_panel_dominates_mixed_conditions():
    # rs1799950-shaped: many Benign (incl. an expert panel) + one low-confidence Uncertain.
    rcv = [{"clinical_significance": "Benign", "review_status": "criteria provided, multiple submitters, no conflicts"}] * 3
    rcv.append({"clinical_significance": "Benign", "review_status": "reviewed by expert panel"})
    rcv.append({"clinical_significance": "Uncertain significance", "review_status": "no assertion criteria provided"})
    r = summarize_clinvar(rcv)
    assert r["headline"] == "Benign"          # not "Benign; Uncertain significance"
    assert r["conflicting"] is False          # Benign vs VUS is not a conflict
    assert "Uncertain" not in r["snippet"]
    assert "Uncertain significance" in r["raw_significances"]  # still in provenance


def test_clinvar_empty_is_none():
    assert summarize_clinvar([]) is None
    assert summarize_clinvar(None) is None
