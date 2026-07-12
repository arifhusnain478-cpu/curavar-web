"""
CuraVar pipeline: the end-to-end orchestration.

  variant
    -> SourceProvider writes raw evidence into the ledger
    -> AgentLayer.gather   : Claude proposes evidence-backed ACMG criteria
    -> AgentLayer.adjudicate: Claude prunes / resolves conflicts (logged)
    -> acmg.classify        : deterministic combining rules (no LLM)
    -> ClassificationResult + full ledger

The result object carries everything a reviewer needs to audit the decision:
the classification, the rule that fired, each activated criterion with its
justification and evidence pointers, and the complete provenance ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .acmg import (ActivatedCriterion, ClassificationResult, PointsResult,
                   ReconciledResult, classify, classify_points, reconcile)
from .agents import AgentLayer
from .llm import LLMClient
from .provenance import ProvenanceLedger, SourceType
from .pvs1 import PVS1Features, evaluate_pvs1
from .sources import SourceProvider, Variant


@dataclass
class CuraVarResult:
    variant: Variant
    proposals: list[ActivatedCriterion]
    activated: list[ActivatedCriterion]
    classification: ClassificationResult
    points: PointsResult
    reconciled: ReconciledResult
    ledger: ProvenanceLedger

    def summary(self) -> dict[str, Any]:
        ledger_ok, ledger_problems = self.ledger.verify()
        return {
            "variant": self.variant.label,
            "classification": self.reconciled.headline.value,
            "rule_based": self.classification.classification.value,
            "points_based": self.points.classification.value,
            "points_score": self.points.score,
            "methods_agree": self.reconciled.agree,
            "reconciliation": self.reconciled.note,
            "contradiction": self.classification.contradiction or self.points.conflict,
            "activated_criteria": [
                {"code": c.code, "justification": c.justification,
                 "evidence": c.evidence_ids}
                for c in self.activated
            ],
            "ledger_entries": self.ledger.to_dict()["entry_count"],
            "ledger_verified": ledger_ok,
            "ledger_problems": ledger_problems,
        }


class CuraVarPipeline:
    def __init__(self, source: SourceProvider, llm: LLMClient):
        self.source = source
        self.agents = AgentLayer(llm=llm)

    def _apply_pvs1(self, activated, ledger, pvs1_features):
        """Run the PVS1 decision tree and override any PVS1 the agents proposed
        with the strength the tree computes (logging the decision path)."""
        if not pvs1_features:
            return activated
        result = evaluate_pvs1(PVS1Features(**pvs1_features))
        ledger.record(
            source_type=SourceType.GENE_CONTEXT,
            source_name="CuraVar PVS1 decision tree",
            locator="Abou Tayoun et al. 2018",
            payload={"strength": result.strength.value, "path": result.path},
            snippet=" ".join(result.path),
        )
        pvs1_ev = [e.id for e in ledger.all()
                   if e.source_name == "CuraVar PVS1 decision tree"]
        out = [c for c in activated if c.code != "PVS1"]
        strength = result.acmg_strength
        if strength is not None:
            out.append(ActivatedCriterion(
                code="PVS1",
                justification=f"{result.strength.value} via SVI decision tree: "
                              + result.path[-1],
                evidence_ids=pvs1_ev,
                strength_override=strength,
            ))
        return out

    def run(self, variant: Variant, pvs1_features: dict = None,
            strict: bool = False) -> CuraVarResult:
        ledger = ProvenanceLedger()
        # 1. raw evidence -> ledger
        self.source.collect(variant, ledger)
        # 2. Claude proposes evidence-backed criteria
        proposals = self.agents.gather(variant, ledger)
        # 3. Claude adjudicates conflicts / weak proposals (reasoning logged)
        activated = self.agents.adjudicate(proposals, ledger)
        # 3b. refine PVS1 strength via the SVI decision tree (deterministic)
        activated = self._apply_pvs1(activated, ledger, pvs1_features)
        # 3c. optional strict mode: drop circular criteria (PP5/BP6)
        if strict:
            from .acmg import apply_strict_mode
            activated, removed = apply_strict_mode(activated)
            if removed:
                ledger.record(
                    source_type=SourceType.GENE_CONTEXT,
                    source_name="CuraVar strict mode",
                    locator="PP5/BP6 excluded",
                    payload={"removed": removed},
                    snippet=f"Strict mode excluded circular criteria: {', '.join(removed)}.",
                )
        # 4. deterministic combining rules (2015) + points system (2018/2020)
        result = classify(activated)
        points = classify_points(activated)
        reconciled = reconcile(result, points)
        return CuraVarResult(
            variant=variant, proposals=proposals, activated=activated,
            classification=result, points=points, reconciled=reconciled,
            ledger=ledger,
        )
