"""
Pydantic request/response models.

These give the API typed contracts and drive the auto-generated OpenAPI docs at
``/docs``. The response models mirror the dicts produced by ``service.py``; a
few deeply-nested, free-form pieces (raw evidence payloads, the full ledger
dump) are typed as ``dict``/``Any`` on purpose — they are provenance data we
pass through verbatim, not fields the API interprets.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# --------------------------- requests ---------------------------------------


class ClassifyRequest(BaseModel):
    """Classify one variant.

    Provide exactly one of ``case_id`` / ``case_path`` / ``hgvs`` / ``variant``.
    Routing is automatic: an ``hgvs`` that matches a bundled snapshot is
    classified offline; otherwise, if the server has an API key, it is looked up
    live. The caller never has to choose offline vs. live.
    """

    case_id: Optional[str] = Field(None, description="Bundled case id, e.g. 'brca1_c5266dupC'.")
    case_path: Optional[str] = Field(None, description="Path to a bundled case file (confined to the data dir).")
    hgvs: Optional[str] = Field(None, description="Free-text HGVS, e.g. 'c.5266dupC' or 'BRCA1 c.5266dupC'. Auto-routed offline/live by the server.")
    variant: Optional[dict[str, Any]] = Field(None, description="Full variant object (looked up live).")
    live: bool = Field(False, description="Force the live path (normally the server auto-routes). Errors clearly if no ANTHROPIC_API_KEY is set.")
    strict: bool = Field(False, description="Exclude circular criteria (PP5/BP6).")
    assembly: str = Field(
        "hg38",
        description="Genome build for live MyVariant.info lookups: 'hg38' (GRCh38, default) or 'hg19' (GRCh37).",
    )

    @model_validator(mode="after")
    def _one_selector(self) -> "ClassifyRequest":
        if not any([self.case_id, self.case_path, self.hgvs, self.variant]):
            raise ValueError("Provide one of: case_id, case_path, hgvs, variant.")
        if self.assembly.lower() not in ("hg38", "hg19"):
            raise ValueError("assembly must be 'hg38' or 'hg19'.")
        return self


class TriageRequest(BaseModel):
    """Triage a set of bundled cases. Empty ``case_ids`` triages all of them."""

    case_ids: Optional[list[str]] = Field(None, description="Bundled case ids; omit or empty for all.")


# --------------------------- shared response pieces -------------------------


class VariantView(BaseModel):
    gene: str
    hgvs_c: str
    hgvs_p: str
    genome_build: str
    coordinate: str
    inheritance: str
    label: str


class EvidenceView(BaseModel):
    id: str
    source_type: str
    source_name: str
    locator: str
    snippet: str
    retrieved_at: float
    entry_hash: str
    prev_hash: str
    payload: dict[str, Any]


class CriterionView(BaseModel):
    code: str
    direction: str
    strength: str
    description: str
    justification: str
    points: int
    evidence_ids: list[str]
    evidence: list[EvidenceView]


class RemovedCriterion(BaseModel):
    code: Optional[str] = None
    reason: Optional[str] = None


class ClassificationView(BaseModel):
    headline: str
    rule_based: str
    rule_fired: str
    points_based: str
    methods_agree: bool
    diverges_across_vus: bool
    contradiction: bool
    note: str


class PointsBreakdownItem(BaseModel):
    code: str
    points: int


class PointsView(BaseModel):
    score: int
    pathogenic_points: int
    benign_points: int
    classification: str
    conflict: bool
    distance_to_next: str
    breakdown: list[PointsBreakdownItem]


class Pvs1View(BaseModel):
    strength: str
    path: list[str]


# --------------------------- endpoint responses -----------------------------


class ClassifyResponse(BaseModel):
    id: str
    mode: str
    strict: bool
    variant: VariantView
    classification: ClassificationView
    points: PointsView
    activated_criteria: list[CriterionView]
    removed_criteria: list[RemovedCriterion]
    pvs1: Optional[Pvs1View]
    ledger: dict[str, Any]
    ledger_verified: bool
    ledger_problems: list[str]


class CaseSummary(BaseModel):
    id: str
    gene: str
    hgvs_c: str
    hgvs_p: str
    label: str
    synthetic: bool


class CasesResponse(BaseModel):
    cases: list[CaseSummary]


class ConfigResponse(BaseModel):
    version: str
    live_available: bool
    case_count: int


class TriageItemView(BaseModel):
    id: str
    variant: str
    gene: str
    headline: str
    points: int
    bucket: str
    reason: str
    priority: int
    methods_agree: bool
    ledger_verified: bool


class TriageCounts(BaseModel):
    ACT: int
    REVIEW: int
    CLEAR: int


class TriageResponse(BaseModel):
    counts: TriageCounts
    total: int
    items: list[TriageItemView]
    # present only for VCF uploads
    matched: Optional[int] = None
    unmatched: Optional[list[dict[str, str]]] = None
    note: Optional[str] = None


class LedgerResponse(BaseModel):
    id: str
    variant: str
    verified: bool
    problems: list[str]
    ledger_version: int
    entry_count: int
    entries: list[dict[str, Any]]


class ErrorResponse(BaseModel):
    detail: str
