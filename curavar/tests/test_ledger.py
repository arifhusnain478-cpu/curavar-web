import dataclasses
from curavar.provenance import ProvenanceLedger, SourceType

def _fill():
    L = ProvenanceLedger()
    L.record(SourceType.POPULATION_DB, "gnomAD", "chr1:1:A>T", {"af": 0.0}, "absent")
    L.record(SourceType.CLINICAL_DB, "ClinVar", "VCV1", {"assertion": "Pathogenic"}, "3-star")
    return L

def test_clean_chain_verifies():
    ok, problems = _fill().verify()
    assert ok and problems == []

def test_tamper_is_detected():
    L = _fill()
    L._entries[0] = dataclasses.replace(L._entries[0], payload={"af": 0.9})
    ok, problems = L.verify()
    assert not ok and any("altered" in p for p in problems)

def test_reorder_is_detected():
    L = _fill()
    L._entries[0], L._entries[1] = L._entries[1], L._entries[0]
    ok, _ = L.verify()
    assert not ok
