"""
Benchmark / validation harness.

Runs the classification engine over a labeled truth set and reports:
  * per-tier and overall accuracy of the 2015 combining-rule engine,
  * a confusion matrix,
  * where the 2018/2020 points system diverges from the rules (documented),
  * throughput (classifications per second).

Because the 2015 combining rules are deterministic given a set of criteria, a
correct implementation must reproduce every expected label exactly. This is a
regression test of guideline fidelity, and the harness is structured so the same
metrics (sensitivity/specificity) can be computed against real labeled variant
sets such as ClinGen's eRepo when run with live evidence.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from .io_utils import read_json
from .acmg import (ActivatedCriterion, Classification, classify,
                   classify_points, reconcile)

TIERS = [
    Classification.PATHOGENIC, Classification.LIKELY_PATHOGENIC,
    Classification.VUS, Classification.LIKELY_BENIGN, Classification.BENIGN,
]
_ABBR = {Classification.PATHOGENIC: "P", Classification.LIKELY_PATHOGENIC: "LP",
         Classification.VUS: "VUS", Classification.LIKELY_BENIGN: "LB",
         Classification.BENIGN: "B"}


@dataclass
class BenchmarkResult:
    total: int
    correct: int
    per_tier: dict          # tier -> (correct, n)
    confusion: dict         # (expected, got) -> count
    divergences: list       # cases where points != rules
    seconds: float

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def per_sec(self) -> float:
        return self.total / self.seconds if self.seconds else float("inf")


def _mk(codes):
    return [ActivatedCriterion(code=c, justification="", evidence_ids=["E0000"])
            for c in codes]


def run_benchmark(truth_path: str) -> BenchmarkResult:
    data = read_json(truth_path)
    cases = data["cases"]

    per_tier = {t: [0, 0] for t in TIERS}
    confusion = {}
    divergences = []
    correct = 0

    start = time.perf_counter()
    for case in cases:
        crits = _mk(case["criteria"])
        expected = Classification(case["expected"])
        rule_res = classify(crits)
        pts_res = classify_points(crits)
        got = rule_res.classification

        per_tier[expected][1] += 1
        if got == expected:
            per_tier[expected][0] += 1
            correct += 1
        confusion[(expected, got)] = confusion.get((expected, got), 0) + 1

        if pts_res.classification != got:
            divergences.append((case["id"], _ABBR[got], _ABBR[pts_res.classification],
                                pts_res.score))
    seconds = time.perf_counter() - start

    return BenchmarkResult(
        total=len(cases), correct=correct,
        per_tier={t: tuple(v) for t, v in per_tier.items()},
        confusion=confusion, divergences=divergences, seconds=seconds,
    )


def format_report(r: BenchmarkResult) -> str:
    lines = []
    lines.append("CuraVar engine validation")
    lines.append("=" * 46)
    lines.append(f"Overall rule-engine accuracy: {r.correct}/{r.total} "
                 f"({r.accuracy*100:.1f}%)")
    lines.append(f"Throughput: {r.per_sec:,.0f} classifications/sec")
    lines.append("")
    lines.append("Per-tier (rule engine vs expected):")
    for t in TIERS:
        c, n = r.per_tier[t]
        if n:
            lines.append(f"  {_ABBR[t]:4s} {c}/{n}")
    lines.append("")
    lines.append("Rules-vs-points divergences (documented, expected):")
    if r.divergences:
        for cid, rule_t, pts_t, score in r.divergences:
            lines.append(f"  {cid:7s} rules={rule_t:4s} points={pts_t:4s} ({score:+d})")
    else:
        lines.append("  none")
    return "\n".join(lines)
