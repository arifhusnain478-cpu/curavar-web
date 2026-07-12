"""
Batch triage.

A curator's real workflow is not one variant at a time -- it is a worklist of
hundreds, where the scarce resource is expert attention. Triage runs the whole
pipeline over a set of variants and returns a prioritized worklist:

  ACT      pathogenic / likely pathogenic  -> report out
  REVIEW   conflicts, method divergence, or VUS near a boundary -> needs a human
  CLEAR    benign / likely benign          -> low priority

The ordering puts the variants that most need a human first. This is where a
tool earns its place in a lab: not by auto-deciding, but by pointing limited
expert time at the cases that actually need it.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

from .acmg import Classification
from .llm import LLMClient
from .pipeline import CuraVarPipeline, CuraVarResult
from .sources import BundledSourceProvider

_ACT = {Classification.PATHOGENIC, Classification.LIKELY_PATHOGENIC}
_CLEAR = {Classification.BENIGN, Classification.LIKELY_BENIGN}


@dataclass
class TriageItem:
    variant: str
    gene: str
    headline: Classification
    points: int
    bucket: str            # ACT | REVIEW | CLEAR
    reason: str
    priority: int          # lower sorts first
    result: CuraVarResult


def _bucket(result: CuraVarResult) -> tuple[str, str, int]:
    rec = result.reconciled
    headline = rec.headline
    # highest attention: methods disagree or evidence conflicts
    if not rec.agree or result.points.conflict or result.classification.contradiction:
        return ("REVIEW", "Conflicting evidence / methods diverge", 0)
    if headline in _ACT:
        return ("ACT", "Reaches a (likely) pathogenic call", 1)
    if headline == Classification.VUS:
        # VUS near a decision boundary is worth a closer look
        near = abs(result.points.score) <= 4
        return ("REVIEW",
                "Uncertain" + (" (near a boundary)" if near else ""),
                2 if near else 3)
    if headline in _CLEAR:
        return ("CLEAR", "(Likely) benign", 4)
    return ("REVIEW", "Uncategorized", 3)


def triage_cases(case_paths: list[str], mode: str = "replay") -> list[TriageItem]:
    items: list[TriageItem] = []
    for path in case_paths:
        prov = BundledSourceProvider(path)
        cassettes = prov.cassettes if mode == "replay" else None
        llm = LLMClient(mode=mode, cassettes=cassettes)
        result = CuraVarPipeline(source=prov, llm=llm).run(
            prov.variant, pvs1_features=prov.pvs1_features)
        bucket, reason, pr = _bucket(result)
        items.append(TriageItem(
            variant=prov.variant.label, gene=prov.variant.gene,
            headline=result.reconciled.headline, points=result.points.score,
            bucket=bucket, reason=reason, priority=pr, result=result,
        ))
    items.sort(key=lambda it: (it.priority, -abs(it.points)))
    return items


def summary_counts(items: list[TriageItem]) -> dict:
    out = {"ACT": 0, "REVIEW": 0, "CLEAR": 0}
    for it in items:
        out[it.bucket] += 1
    return out
