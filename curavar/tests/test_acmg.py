from curavar.acmg import ActivatedCriterion, classify, Classification

def _c(code): return ActivatedCriterion(code=code, justification="", evidence_ids=["E0001"])

def test_pathogenic_pvs1_plus_moderate_supporting():
    r = classify([_c("PVS1"), _c("PM2"), _c("PP5")])
    assert r.classification == Classification.PATHOGENIC

def test_two_strong_is_pathogenic():
    assert classify([_c("PS3"), _c("PS4")]).classification == Classification.PATHOGENIC

def test_three_moderate_is_likely_pathogenic():
    r = classify([_c("PM1"), _c("PM2"), _c("PM5")])
    assert r.classification == Classification.LIKELY_PATHOGENIC

def test_ba1_standalone_is_benign():
    assert classify([_c("BA1")]).classification == Classification.BENIGN

def test_two_supporting_benign_is_likely_benign():
    assert classify([_c("BP4"), _c("BP7")]).classification == Classification.LIKELY_BENIGN

def test_insufficient_is_vus():
    assert classify([_c("PM2"), _c("PP3")]).classification == Classification.VUS

def test_conflict_resolves_to_vus_with_flag():
    r = classify([_c("PS3"), _c("PM2"), _c("BS2"), _c("BS3")])
    assert r.classification == Classification.VUS
    assert r.contradiction is True


# --- points-based (Tavtigian 2018/2020) ---
from curavar.acmg import classify_points, reconcile

def test_points_pathogenic_threshold():
    r = classify_points([_c("PVS1"), _c("PM2"), _c("PP5")])  # 8+2+1
    assert r.score == 11 and r.classification == Classification.PATHOGENIC

def test_points_benign_standalone():
    r = classify_points([_c("BA1"), _c("BP4")])  # -8-1
    assert r.score == -9 and r.classification == Classification.BENIGN

def test_points_conflict_flagged_and_reconciled_to_vus():
    crits = [_c("PS3"), _c("PM2"), _c("BS3"), _c("BS2")]  # +4+2-4-4 = -2
    p = classify_points(crits)
    assert p.score == -2 and p.conflict is True
    rec = reconcile(classify(crits), p)
    assert rec.headline == Classification.VUS   # safe reconciliation
    assert rec.agree is False

def test_points_and_rules_agree_on_clear_cases():
    for crits, tier in [(["PVS1","PM2","PP5"], Classification.PATHOGENIC),
                        (["BA1","BP4"], Classification.BENIGN)]:
        cs = [_c(x) for x in crits]
        assert reconcile(classify(cs), classify_points(cs)).agree is True


# --- benchmark + strict mode ---
from curavar.acmg import apply_strict_mode

def test_strict_mode_removes_circular_criteria():
    kept, removed = apply_strict_mode([_c("PVS1"), _c("PM2"), _c("PP5"), _c("BP6")])
    codes = [c.code for c in kept]
    assert "PP5" not in codes and "BP6" not in codes
    assert set(removed) == {"PP5", "BP6"}

def test_benchmark_engine_is_100pct():
    import os
    from curavar.benchmark import run_benchmark
    truth = os.path.join(os.path.dirname(__file__), "..", "curavar", "data", "truth_set.json")
    r = run_benchmark(truth)
    assert r.correct == r.total   # engine must reproduce every guideline-defined label


# --- PVS1 decision tree ---
from curavar.pvs1 import PVS1Features, evaluate_pvs1, PVS1Strength

def test_pvs1_full_strength_when_nmd():
    r = evaluate_pvs1(PVS1Features(consequence="nonsense", lof_is_mechanism=True,
                                   predicted_nmd=True))
    assert r.strength == PVS1Strength.VERY_STRONG

def test_pvs1_downgraded_last_exon_noncritical():
    r = evaluate_pvs1(PVS1Features(consequence="nonsense", lof_is_mechanism=True,
                                   predicted_nmd=False, removes_critical_region=False,
                                   fraction_protein_lost=0.04))
    assert r.strength == PVS1Strength.MODERATE

def test_pvs1_not_applicable_without_lof_mechanism():
    r = evaluate_pvs1(PVS1Features(consequence="frameshift", lof_is_mechanism=False))
    assert r.strength == PVS1Strength.NOT_APPLICABLE

def test_pvs1_strong_when_removes_critical_region():
    r = evaluate_pvs1(PVS1Features(consequence="nonsense", lof_is_mechanism=True,
                                   predicted_nmd=False, removes_critical_region=True))
    assert r.strength == PVS1Strength.STRONG


# --- triage worklist ---
def test_triage_buckets_and_ordering():
    import os, glob
    from curavar.triage import triage_cases
    data = os.path.join(os.path.dirname(__file__), "..", "curavar", "data")
    paths = [p for p in sorted(glob.glob(os.path.join(data, "*.json")))
             if os.path.basename(p) != "truth_set.json"]
    items = triage_cases(paths)
    assert len(items) >= 3
    buckets = {it.bucket for it in items}
    assert buckets <= {"ACT", "REVIEW", "CLEAR"}
    # review items (priority 0-3) must sort before clear (priority 4)
    prios = [it.priority for it in items]
    assert prios == sorted(prios)
