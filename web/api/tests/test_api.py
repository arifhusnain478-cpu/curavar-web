"""
Endpoint tests — every route exercised in offline replay mode (no API key, no
network). These assert the web layer faithfully surfaces the engine's output;
the engine's own correctness is covered by curavar's test suite.
"""

import os

SAMPLE_VCF = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample.vcf")


# --------------------------- meta -------------------------------------------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config_reports_capabilities(client):
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert body["case_count"] >= 4
    assert isinstance(body["live_available"], bool)


def test_cases_lists_bundled_variants(client):
    r = client.get("/cases")
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()["cases"]}
    assert {"brca1_c5266dupC", "mthfr_c665CtoT", "demo2_pvs1_lastexon"} <= ids


# --------------------------- classify ---------------------------------------


def test_classify_pathogenic_by_case_id(client):
    r = client.post("/classify", json={"case_id": "brca1_c5266dupC"})
    assert r.status_code == 200
    body = r.json()
    assert body["classification"]["headline"] == "Pathogenic"
    assert body["classification"]["methods_agree"] is True
    assert body["points"]["score"] == 11
    assert body["ledger_verified"] is True
    # every activated criterion carries at least one traced evidence entry
    assert body["activated_criteria"]
    for c in body["activated_criteria"]:
        assert c["evidence_ids"]
        assert len(c["evidence"]) == len(c["evidence_ids"])
        assert all(ev["entry_hash"] for ev in c["evidence"])


def test_classify_benign_by_hgvs_match(client):
    r = client.post("/classify", json={"hgvs": "c.665C>T"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "mthfr_c665CtoT"
    assert body["classification"]["headline"] == "Benign"


def test_classify_pvs1_lastexon_is_downgraded_to_vus(client):
    r = client.post("/classify", json={"case_id": "demo2_pvs1_lastexon"})
    assert r.status_code == 200
    body = r.json()
    # a naive full-strength PVS1 would over-call this Pathogenic; the tree downgrades
    assert body["classification"]["headline"] == "Uncertain significance"
    assert body["pvs1"] is not None
    assert body["pvs1"]["strength"] == "PVS1_Moderate"
    assert body["pvs1"]["path"]


def test_strict_mode_drops_circular_pp5(client):
    base = client.post("/classify", json={"case_id": "brca1_c5266dupC"}).json()
    strict = client.post("/classify", json={"case_id": "brca1_c5266dupC", "strict": True}).json()
    base_codes = {c["code"] for c in base["activated_criteria"]}
    strict_codes = {c["code"] for c in strict["activated_criteria"]}
    assert "PP5" in base_codes
    assert "PP5" not in strict_codes
    assert strict["strict"] is True


def test_classify_requires_a_selector(client):
    r = client.post("/classify", json={})
    assert r.status_code == 422  # pydantic model validator


def test_classify_unknown_case_id_404(client):
    r = client.post("/classify", json={"case_id": "does_not_exist"})
    assert r.status_code == 404


def test_classify_unmatched_hgvs_is_422_offline(client):
    r = client.post("/classify", json={"hgvs": "c.9999Z>Q"})
    assert r.status_code == 422
    assert "bundled" in r.json()["detail"].lower()


# --------------------------- report -----------------------------------------


def test_variant_report_is_html(client):
    r = client.get("/variants/brca1_c5266dupC/report")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "CuraVar" in r.text
    assert "Pathogenic" in r.text
    assert "Provenance ledger" in r.text


# --------------------------- triage -----------------------------------------


def test_triage_all_cases_worklist(client):
    r = client.post("/triage", json={})
    assert r.status_code == 200
    body = r.json()
    counts = body["counts"]
    assert counts["ACT"] + counts["REVIEW"] + counts["CLEAR"] == body["total"]
    # sorted by review priority (ascending)
    prios = [it["priority"] for it in body["items"]]
    assert prios == sorted(prios)
    # each row references a bundled case id for drill-down
    for it in body["items"]:
        assert it["id"]


def test_triage_subset(client):
    r = client.post("/triage", json={"case_ids": ["brca1_c5266dupC"]})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_triage_vcf_upload_matches_and_reports_unmatched(client):
    with open(SAMPLE_VCF, "rb") as fh:
        r = client.post("/triage/vcf", files={"file": ("sample.vcf", fh, "text/plain")})
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] >= 4
    # the CFTR record has no bundled snapshot -> reported, not silently dropped
    assert any(u["info"] if "info" in u else True for u in body["unmatched"])
    assert body["unmatched"]  # at least the CFTR record


def test_triage_report_is_html(client):
    r = client.get("/triage/report")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "triage" in r.text.lower()


# --------------------------- audit / ledger ---------------------------------


def test_ledger_json_is_verifiable(client):
    r = client.get("/ledger/brca1_c5266dupC")
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["entry_count"] == len(body["entries"])
    assert body["entry_count"] > 0
    # hash chain present on every entry
    for e in body["entries"]:
        assert e["entry_hash"]
