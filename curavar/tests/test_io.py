"""Regression tests for the Windows/cp1252 report-writing crash."""
import os, tempfile
from curavar.io_utils import write_text, read_text, write_json, read_json
from curavar.sources import BundledSourceProvider
from curavar.llm import LLMClient
from curavar.pipeline import CuraVarPipeline
from curavar.report import render_report

DATA = os.path.join(os.path.dirname(__file__), "..", "curavar", "data")

def test_write_text_handles_non_cp1252_chars():
    # These chars appear in every report and are absent from cp1252.
    payload = "em—dash arrow→ check✓ ge≥ minus−"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.html")
        write_text(p, payload)                 # must not raise on any OS
        assert read_text(p) == payload         # round-trips intact
        with open(p, "rb") as f:               # stored as UTF-8 bytes
            assert "−".encode("utf-8") in f.read()

def test_report_write_roundtrip():
    prov = BundledSourceProvider(os.path.join(DATA, "brca1_c5266dupC.json"))
    result = CuraVarPipeline(source=prov,
        llm=LLMClient(mode="replay", cassettes=prov.cassettes)).run(
        prov.variant, pvs1_features=prov.pvs1_features)
    html = render_report(result)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "report.html")
        write_text(p, html)
        assert "CuraVar" in read_text(p)

def test_json_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.json")
        write_json(p, {"note": "conflict — diverge", "n": 3})
        assert read_json(p)["n"] == 3
