"""
ACMG/AMP variant classification engine (Richards et al., 2015).

This module is deliberately LLM-free. The language model's job upstream is to
*gather evidence* and *propose* which criteria are activated, each with a
justification and pointers into the provenance ledger. This engine takes those
activated criteria and applies the published combining rules to reach one of
five classifications. Because the combining logic is deterministic, the same
set of activated criteria always yields the same classification -- a reviewer
can re-run it and get a bit-identical result.

Reference: Richards S, et al. "Standards and guidelines for the interpretation
of sequence variants." Genet Med. 2015;17(5):405-424.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Strength(str, Enum):
    VERY_STRONG = "very_strong"    # PVS1
    STRONG = "strong"              # PS1-4 / BS1-4
    MODERATE = "moderate"          # PM1-6
    SUPPORTING = "supporting"      # PP1-5 / BP1-7
    STANDALONE = "standalone"      # BA1


class Direction(str, Enum):
    PATHOGENIC = "pathogenic"
    BENIGN = "benign"


# The canonical criterion catalog: code -> (direction, default strength, description)
CRITERIA: dict[str, tuple[Direction, Strength, str]] = {
    # Pathogenic
    "PVS1": (Direction.PATHOGENIC, Strength.VERY_STRONG,
             "Null variant in a gene where loss of function is a known mechanism of disease"),
    "PS1":  (Direction.PATHOGENIC, Strength.STRONG,
             "Same amino acid change as an established pathogenic variant"),
    "PS2":  (Direction.PATHOGENIC, Strength.STRONG,
             "De novo (confirmed maternity and paternity) in a patient with the disease"),
    "PS3":  (Direction.PATHOGENIC, Strength.STRONG,
             "Well-established functional studies show a damaging effect"),
    "PS4":  (Direction.PATHOGENIC, Strength.STRONG,
             "Prevalence in affecteds significantly increased vs controls"),
    "PM1":  (Direction.PATHOGENIC, Strength.MODERATE,
             "Located in a mutational hot spot / critical functional domain"),
    "PM2":  (Direction.PATHOGENIC, Strength.MODERATE,
             "Absent or extremely low frequency in population databases"),
    "PM3":  (Direction.PATHOGENIC, Strength.MODERATE,
             "For recessive disorders, detected in trans with a pathogenic variant"),
    "PM4":  (Direction.PATHOGENIC, Strength.MODERATE,
             "Protein length change from in-frame indel / stop-loss"),
    "PM5":  (Direction.PATHOGENIC, Strength.MODERATE,
             "Novel missense at a residue where another pathogenic missense is known"),
    "PM6":  (Direction.PATHOGENIC, Strength.MODERATE,
             "Assumed de novo without confirmation of maternity and paternity"),
    "PP1":  (Direction.PATHOGENIC, Strength.SUPPORTING,
             "Cosegregation with disease in multiple affected family members"),
    "PP2":  (Direction.PATHOGENIC, Strength.SUPPORTING,
             "Missense in a gene with low benign-missense rate and known missense mechanism"),
    "PP3":  (Direction.PATHOGENIC, Strength.SUPPORTING,
             "Multiple computational lines of evidence support a deleterious effect"),
    "PP4":  (Direction.PATHOGENIC, Strength.SUPPORTING,
             "Patient phenotype highly specific for a single-gene disease"),
    "PP5":  (Direction.PATHOGENIC, Strength.SUPPORTING,
             "Reputable source reports pathogenic without accessible supporting data"),
    # Benign
    "BA1":  (Direction.BENIGN, Strength.STANDALONE,
             "Allele frequency above a benign threshold in population databases"),
    "BS1":  (Direction.BENIGN, Strength.STRONG,
             "Allele frequency greater than expected for the disorder"),
    "BS2":  (Direction.BENIGN, Strength.STRONG,
             "Observed in healthy adults where full penetrance is expected"),
    "BS3":  (Direction.BENIGN, Strength.STRONG,
             "Well-established functional studies show no damaging effect"),
    "BS4":  (Direction.BENIGN, Strength.STRONG,
             "Lack of segregation in affected family members"),
    "BP1":  (Direction.BENIGN, Strength.SUPPORTING,
             "Missense in a gene where only truncating variants cause disease"),
    "BP2":  (Direction.BENIGN, Strength.SUPPORTING,
             "Observed in trans/cis inconsistent with pathogenic role"),
    "BP3":  (Direction.BENIGN, Strength.SUPPORTING,
             "In-frame indel in a repetitive region without known function"),
    "BP4":  (Direction.BENIGN, Strength.SUPPORTING,
             "Multiple computational lines of evidence suggest no impact"),
    "BP5":  (Direction.BENIGN, Strength.SUPPORTING,
             "Found in a case with an alternate molecular cause"),
    "BP6":  (Direction.BENIGN, Strength.SUPPORTING,
             "Reputable source reports benign without accessible supporting data"),
    "BP7":  (Direction.BENIGN, Strength.SUPPORTING,
             "Synonymous with no predicted splice impact and no conservation"),
}


class Classification(str, Enum):
    PATHOGENIC = "Pathogenic"
    LIKELY_PATHOGENIC = "Likely pathogenic"
    VUS = "Uncertain significance"
    LIKELY_BENIGN = "Likely benign"
    BENIGN = "Benign"


@dataclass
class ActivatedCriterion:
    """A criterion the evidence-gathering layer proposes as met."""
    code: str
    justification: str
    evidence_ids: list[str] = field(default_factory=list)
    # allow strength override (e.g. PM2_Supporting per ClinGen); default from catalog
    strength_override: Optional[Strength] = None

    @property
    def direction(self) -> Direction:
        return CRITERIA[self.code][0]

    @property
    def strength(self) -> Strength:
        return self.strength_override or CRITERIA[self.code][1]


def _count_by_strength(crits: list[ActivatedCriterion], direction: Direction):
    subset = [c for c in crits if c.direction == direction]
    counts = {s: 0 for s in Strength}
    for c in subset:
        counts[c.strength] += 1
    return counts


@dataclass
class ClassificationResult:
    classification: Classification
    rule_fired: str
    activated: list[ActivatedCriterion]
    contradiction: bool = False
    notes: str = ""


def classify(activated: list[ActivatedCriterion]) -> ClassificationResult:
    """Apply the ACMG/AMP 2015 combining rules to activated criteria."""
    p = _count_by_strength(activated, Direction.PATHOGENIC)
    b = _count_by_strength(activated, Direction.BENIGN)

    PVS = p[Strength.VERY_STRONG]
    PS = p[Strength.STRONG]
    PM = p[Strength.MODERATE]
    PP = p[Strength.SUPPORTING]

    BA = b[Strength.STANDALONE]
    BS = b[Strength.STRONG]
    BP = b[Strength.SUPPORTING]

    # --- Pathogenic combinations ---
    path_rule = None
    if PVS >= 1 and (PS >= 1 or PM >= 2 or (PM >= 1 and PP >= 1) or PP >= 2):
        path_rule = "Pathogenic (i): 1 PVS1 + supporting pathogenic evidence"
    elif PS >= 2:
        path_rule = "Pathogenic (ii): >=2 Strong"
    elif PS >= 1 and (PM >= 3 or (PM >= 2 and PP >= 2) or (PM >= 1 and PP >= 4)):
        path_rule = "Pathogenic (iii): 1 Strong + Moderate/Supporting"

    lp_rule = None
    if (PVS >= 1 and PM >= 1) \
       or (PS >= 1 and 1 <= PM <= 2) \
       or (PS >= 1 and PP >= 2) \
       or (PM >= 3) \
       or (PM >= 2 and PP >= 2) \
       or (PM >= 1 and PP >= 4):
        lp_rule = "Likely pathogenic: Moderate/Strong/Supporting combination"

    # --- Benign combinations ---
    ben_rule = None
    if BA >= 1:
        ben_rule = "Benign (i): BA1 standalone"
    elif BS >= 2:
        ben_rule = "Benign (ii): >=2 Strong benign"

    lb_rule = None
    if (BS >= 1 and BP >= 1) or (BP >= 2):
        lb_rule = "Likely benign: Strong+Supporting or >=2 Supporting"

    pathogenic_side = path_rule or lp_rule
    benign_side = ben_rule or lb_rule

    # --- Contradiction handling: strong evidence in both directions -> VUS ---
    if pathogenic_side and benign_side:
        return ClassificationResult(
            classification=Classification.VUS,
            rule_fired="Conflicting: pathogenic and benign criteria both met",
            activated=activated,
            contradiction=True,
            notes=f"Pathogenic branch: {pathogenic_side}; Benign branch: {benign_side}. "
                  "Per guideline, contradictory evidence defaults to Uncertain significance.",
        )

    if path_rule:
        return ClassificationResult(Classification.PATHOGENIC, path_rule, activated)
    if lp_rule:
        return ClassificationResult(Classification.LIKELY_PATHOGENIC, lp_rule, activated)
    if ben_rule:
        return ClassificationResult(Classification.BENIGN, ben_rule, activated)
    if lb_rule:
        return ClassificationResult(Classification.LIKELY_BENIGN, lb_rule, activated)

    return ClassificationResult(
        classification=Classification.VUS,
        rule_fired="No combining rule satisfied",
        activated=activated,
        notes="Insufficient criteria to reach a benign or pathogenic threshold.",
    )


# ---------------------------------------------------------------------------
# Points-based Bayesian classification (Tavtigian et al. 2018, 2020)
#
# The ACMG/AMP strength categories map to additive points proportional to
# log(odds of pathogenicity). Pathogenic evidence is positive, benign negative.
# Point values and thresholds follow the ACGS 2023 best-practice guideline.
# This runs alongside the 2015 combining rules; CuraVar reports both and flags
# where they disagree -- exactly the mixed-evidence cases that need human review.
# ---------------------------------------------------------------------------

_POINTS_PATHOGENIC = {
    Strength.VERY_STRONG: 8, Strength.STRONG: 4,
    Strength.MODERATE: 2, Strength.SUPPORTING: 1,
}
_POINTS_BENIGN = {
    Strength.STANDALONE: -8, Strength.STRONG: -4,
    Strength.MODERATE: -2, Strength.SUPPORTING: -1,
}


def points_for(crit: "ActivatedCriterion") -> int:
    if crit.direction == Direction.PATHOGENIC:
        return _POINTS_PATHOGENIC[crit.strength]
    return _POINTS_BENIGN[crit.strength]


def tier_from_points(pts: int) -> Classification:
    if pts >= 10:
        return Classification.PATHOGENIC
    if pts >= 6:
        return Classification.LIKELY_PATHOGENIC
    if pts >= 0:
        return Classification.VUS
    if pts >= -5:
        return Classification.LIKELY_BENIGN
    return Classification.BENIGN


# lower boundary of each tier, for "distance to next tier" reporting
_TIER_BOUNDS = [
    (Classification.PATHOGENIC, 10, None),
    (Classification.LIKELY_PATHOGENIC, 6, 9),
    (Classification.VUS, 0, 5),
    (Classification.LIKELY_BENIGN, -5, -1),
    (Classification.BENIGN, None, -6),
]


@dataclass
class PointsResult:
    score: int
    classification: Classification
    pathogenic_points: int
    benign_points: int
    breakdown: list[tuple[str, int]]         # (code, points)
    conflict: bool
    distance_to_next: str                    # human-readable


def classify_points(activated: list["ActivatedCriterion"]) -> PointsResult:
    breakdown = [(c.code, points_for(c)) for c in activated]
    path_pts = sum(p for _, p in breakdown if p > 0)
    ben_pts = sum(p for _, p in breakdown if p < 0)
    total = path_pts + ben_pts
    tier = tier_from_points(total)

    # conflict: meaningful evidence (>= strong) exists on BOTH sides
    conflict = (path_pts >= 4 and ben_pts <= -4)

    # distance to nearest adjacent boundary
    dist = ""
    if tier == Classification.PATHOGENIC:
        dist = "at or above the pathogenic threshold (>=10)"
    elif tier == Classification.BENIGN:
        dist = "at or below the benign threshold (<=-6)"
    else:
        up_targets = {Classification.LIKELY_PATHOGENIC: 10,
                      Classification.VUS: 6,
                      Classification.LIKELY_BENIGN: 0}
        if tier in up_targets:
            need = up_targets[tier] - total
            dist = f"{need} point(s) from the next tier up"
    return PointsResult(
        score=total, classification=tier,
        pathogenic_points=path_pts, benign_points=ben_pts,
        breakdown=breakdown, conflict=conflict, distance_to_next=dist,
    )


# --- ordering of tiers for "which side of VUS" comparisons ---
_TIER_RANK = {
    Classification.BENIGN: -2, Classification.LIKELY_BENIGN: -1,
    Classification.VUS: 0,
    Classification.LIKELY_PATHOGENIC: 1, Classification.PATHOGENIC: 2,
}


@dataclass
class ReconciledResult:
    headline: Classification
    rule_result: "ClassificationResult"
    points_result: PointsResult
    agree: bool
    diverges_across_vus: bool
    note: str


def reconcile(rule_result: "ClassificationResult",
              points_result: PointsResult) -> ReconciledResult:
    """Combine the 2015 rule outcome and the points outcome into one headline.

    Clinical caution: if either method flags a conflict, or the two methods land
    on opposite sides of VUS (one pathogenic-leaning, one benign-leaning), we do
    NOT assert a confident tier -- we report Uncertain and flag for expert review.
    """
    r_tier = rule_result.classification
    p_tier = points_result.classification
    agree = (r_tier == p_tier)

    r_rank, p_rank = _TIER_RANK[r_tier], _TIER_RANK[p_tier]
    diverges_across_vus = (r_rank * p_rank < 0)  # opposite signs

    if rule_result.contradiction or points_result.conflict or diverges_across_vus:
        note = ("Conflicting evidence and/or the two classification methods "
                "diverge. Reported as Uncertain pending expert review.")
        return ReconciledResult(Classification.VUS, rule_result, points_result,
                                agree, diverges_across_vus, note)
    if agree:
        return ReconciledResult(r_tier, rule_result, points_result, True,
                                False, "Both methods agree.")
    # adjacent disagreement (e.g. VUS vs Likely benign): take the more
    # conservative tier (closer to VUS).
    conservative = r_tier if abs(r_rank) < abs(p_rank) else p_tier
    note = (f"Methods differ by one tier (rules: {r_tier.value}; "
            f"points: {p_tier.value}). Reporting the more conservative call.")
    return ReconciledResult(conservative, rule_result, points_result, False,
                            False, note)


# ---------------------------------------------------------------------------
# Strict mode: exclude circular / discouraged criteria (PP5, BP6).
#
# PP5 ("reputable source reports pathogenic") and BP6 (benign equivalent) let a
# tool inherit a database's conclusion without independent evidence. ClinGen SVI
# retired them, and best-practice pipelines (e.g. AutoGVP) remove them because
# leaving them in lets a classifier "borrow" ClinVar's answer and look better
# than its own evidence supports. CuraVar can exclude them so a classification
# rests only on primary evidence.
# ---------------------------------------------------------------------------

DISCOURAGED_CRITERIA = {"PP5", "BP6"}


def apply_strict_mode(activated: list["ActivatedCriterion"]):
    """Return (kept, removed) with circular criteria (PP5/BP6) filtered out."""
    kept = [c for c in activated if c.code not in DISCOURAGED_CRITERIA]
    removed = [c.code for c in activated if c.code in DISCOURAGED_CRITERIA]
    return kept, removed
