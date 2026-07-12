"""
The agent layer.

Two roles:

  1. EvidenceGatherer -- given the variant and the raw evidence in the ledger,
     Claude proposes which ACMG criteria are activated, each with a written
     justification and the specific ledger evidence IDs that support it. Every
     proposal MUST cite at least one ledger ID; proposals that cite nothing are
     dropped (no evidence, no criterion).

  2. Adjudicator -- Claude reviews the union of proposals, removes weakly
     supported ones, and explicitly surfaces any pathogenic/benign conflict.
     Its reasoning is written back into the ledger so the final decision is
     traceable to a stated rationale, not a black box.

The language model never computes the final classification -- that is done
deterministically in acmg.classify(). The model only proposes evidence-backed
criteria; the guideline math is separate and reproducible.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .acmg import CRITERIA, ActivatedCriterion, Strength
from .llm import LLMClient, parse_json_block
from .provenance import ProvenanceLedger, SourceType
from .sources import Variant

_CRITERIA_CATALOG = "\n".join(
    f"  {code}: {desc}" for code, (_, _, desc) in CRITERIA.items()
)

GATHERER_SYSTEM = f"""You are a clinical variant-curation assistant applying the \
ACMG/AMP 2015 sequence-variant interpretation guidelines. You propose which \
criteria are met, but you never make the final classification.

Rules you must follow:
- Only propose a criterion if the provided evidence directly supports it.
- Every proposed criterion MUST cite one or more evidence IDs (e.g. "E0003").
- If evidence is insufficient or ambiguous, propose fewer criteria. Do not guess.
- You may propose both pathogenic and benign criteria if the evidence conflicts;
  do not hide a conflict to force a cleaner answer.

The ACMG/AMP criteria catalog:
{_CRITERIA_CATALOG}

Return STRICT JSON only, no prose, in this shape:
{{"proposals": [
  {{"code": "PM2", "justification": "<one sentence>", "evidence_ids": ["E0001"]}}
]}}"""

ADJUDICATOR_SYSTEM = """You are a senior variant-curation reviewer. You are given \
a list of ACMG criteria proposed by evidence-gathering assistants, each with a \
justification and cited evidence IDs. Your job:
- Keep only criteria whose justification and cited evidence genuinely support them.
- Remove duplicates and any criterion with no real evidentiary basis.
- If pathogenic and benign criteria are both present, state the conflict plainly.
You do NOT compute the final classification. Return STRICT JSON only:
{"kept": [{"code": "PM2", "justification": "...", "evidence_ids": ["E0001"]}],
 "removed": [{"code": "PP3", "reason": "..."}],
 "conflict_note": "<empty string if no conflict>"}"""


def _ledger_digest(ledger: ProvenanceLedger) -> str:
    lines = []
    for e in ledger.all():
        lines.append(
            f"{e.id} [{e.source_type.value}] {e.source_name} @ {e.locator}\n"
            f"    payload: {e.payload}\n"
            f"    snippet: {e.snippet}"
        )
    return "\n".join(lines)


@dataclass
class AgentLayer:
    llm: LLMClient

    def gather(self, variant: Variant, ledger: ProvenanceLedger) -> list[ActivatedCriterion]:
        user = (
            f"Variant: {variant.label}\n"
            f"Gene inheritance / mechanism: {variant.inheritance or 'unspecified'}\n"
            f"Genome build: {variant.genome_build}, coordinate: {variant.coordinate}\n\n"
            f"Evidence in the ledger:\n{_ledger_digest(ledger)}\n\n"
            f"Propose the activated ACMG/AMP criteria as strict JSON."
        )
        raw = self.llm.complete(GATHERER_SYSTEM, user)
        data = parse_json_block(raw)
        proposals = []
        for p in data.get("proposals", []):
            code = p.get("code", "").strip()
            ev = [str(x) for x in p.get("evidence_ids", [])]
            if code not in CRITERIA or not ev:
                continue  # no evidence, or unknown code -> drop
            proposals.append(ActivatedCriterion(
                code=code, justification=p.get("justification", "").strip(),
                evidence_ids=ev))
        return proposals

    def adjudicate(
        self, proposals: list[ActivatedCriterion], ledger: ProvenanceLedger
    ) -> list[ActivatedCriterion]:
        listing = "\n".join(
            f"- {c.code}: {c.justification}  [evidence: {', '.join(c.evidence_ids)}]"
            for c in proposals
        )
        user = f"Proposed criteria:\n{listing}\n\nReview and return strict JSON."
        raw = self.llm.complete(ADJUDICATOR_SYSTEM, user)
        data = parse_json_block(raw)

        # Log the adjudicator's reasoning into the ledger for traceability.
        ledger.record(
            source_type=SourceType.GENE_CONTEXT,
            source_name="CuraVar adjudicator",
            locator="adjudication",
            payload={
                "kept": [k.get("code") for k in data.get("kept", [])],
                "removed": data.get("removed", []),
                "conflict_note": data.get("conflict_note", ""),
            },
            snippet=data.get("conflict_note", "") or "No conflict noted.",
            retrieved_at=time.time(),
        )

        kept = []
        for k in data.get("kept", []):
            code = k.get("code", "").strip()
            ev = [str(x) for x in k.get("evidence_ids", [])]
            if code in CRITERIA and ev:
                kept.append(ActivatedCriterion(
                    code=code, justification=k.get("justification", "").strip(),
                    evidence_ids=ev))
        return kept
