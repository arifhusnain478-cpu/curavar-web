"""
PVS1 loss-of-function decision tree (Abou Tayoun et al. 2018, ClinGen SVI).

PVS1 is the only Very Strong pathogenic criterion, and applying it at full
strength when it isn't warranted is a well-documented source of false
"pathogenic" calls. The 2015 guideline said only "null variant in a LoF gene,
be cautious in the last exon"; the SVI decision tree refines this by variant
type, location, predicted nonsense-mediated decay (NMD), and how much of the
protein is affected, assigning PVS1 at Very Strong / Strong / Moderate /
Supporting, or not at all.

This module is deterministic: given the variant's structural features it returns
a strength and the exact decision path taken. Upstream, Claude's job is to read
the evidence and populate those features; the strength assignment itself is
transparent, reproducible code -- the same "model proposes, rules decide" split
used everywhere in CuraVar.

Reference: Abou Tayoun AN, et al. Hum Mutat. 2018;39(11):1517-1524. PMID 30192042.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .acmg import Strength


class PVS1Strength(str, Enum):
    VERY_STRONG = "PVS1 (Very Strong)"
    STRONG = "PVS1_Strong"
    MODERATE = "PVS1_Moderate"
    SUPPORTING = "PVS1_Supporting"
    NOT_APPLICABLE = "PVS1 not applicable"


_TO_ACMG_STRENGTH = {
    PVS1Strength.VERY_STRONG: Strength.VERY_STRONG,
    PVS1Strength.STRONG: Strength.STRONG,
    PVS1Strength.MODERATE: Strength.MODERATE,
    PVS1Strength.SUPPORTING: Strength.SUPPORTING,
    PVS1Strength.NOT_APPLICABLE: None,
}


def acmg_strength_for(pvs1: PVS1Strength) -> Optional[Strength]:
    return _TO_ACMG_STRENGTH[pvs1]


NULL_CONSEQUENCES = {
    "nonsense", "frameshift", "canonical_splice",
    "initiation_codon", "exon_deletion",
}


@dataclass
class PVS1Features:
    consequence: str                      # one of NULL_CONSEQUENCES
    lof_is_mechanism: bool                # LoF established for this gene/disease
    predicted_nmd: bool = True            # does the premature stop trigger NMD
    in_biologically_relevant_transcript: bool = True
    removes_critical_region: bool = False # affects a known critical domain
    fraction_protein_lost: float = 0.0    # 0..1
    region_enriched_for_lof: bool = False # truncated region tolerates LoF (non-essential)
    exon_skip_preserves_frame: bool = False  # splice: skipping is in-frame
    alternative_start_downstream: bool = False  # initiation codon: rescue start exists


@dataclass
class PVS1Result:
    strength: PVS1Strength
    path: list[str] = field(default_factory=list)

    @property
    def acmg_strength(self) -> Optional[Strength]:
        return acmg_strength_for(self.strength)


def _nonsense_frameshift(f: PVS1Features, p: list[str]) -> PVS1Strength:
    if f.predicted_nmd and f.in_biologically_relevant_transcript:
        p.append("Premature stop predicted to trigger NMD in a biologically "
                 "relevant transcript -> full strength.")
        return PVS1Strength.VERY_STRONG
    # escapes NMD (e.g. last exon / 3' end)
    p.append("Premature stop escapes NMD (3' region / last exon).")
    if f.removes_critical_region or f.fraction_protein_lost > 0.10:
        p.append("Truncation removes a critical region or >10% of the protein "
                 "-> downgrade to Strong.")
        return PVS1Strength.STRONG
    if f.region_enriched_for_lof:
        p.append("Truncated region tolerates LoF (enriched for high-frequency "
                 "LoF variants) -> PVS1 not applicable.")
        return PVS1Strength.NOT_APPLICABLE
    p.append("Truncation removes <=10% of a non-critical region -> downgrade "
             "to Moderate.")
    return PVS1Strength.MODERATE


def _canonical_splice(f: PVS1Features, p: list[str]) -> PVS1Strength:
    if f.exon_skip_preserves_frame:
        p.append("Canonical splice variant; predicted exon skipping preserves "
                 "reading frame.")
        if f.removes_critical_region or f.fraction_protein_lost > 0.10:
            p.append("In-frame skip removes a critical region / >10% -> Strong.")
            return PVS1Strength.STRONG
        p.append("In-frame skip of a non-critical region -> Moderate.")
        return PVS1Strength.MODERATE
    if f.predicted_nmd and f.in_biologically_relevant_transcript:
        p.append("Splice disruption predicted to cause frameshift + NMD -> full "
                 "strength.")
        return PVS1Strength.VERY_STRONG
    p.append("Splice disruption without NMD -> Strong.")
    return PVS1Strength.STRONG


def _initiation_codon(f: PVS1Features, p: list[str]) -> PVS1Strength:
    if f.alternative_start_downstream:
        p.append("Start-loss with a downstream in-frame start; assess N-terminal "
                 "region.")
        if f.removes_critical_region or f.fraction_protein_lost > 0.10:
            return PVS1Strength.MODERATE
        return PVS1Strength.SUPPORTING
    p.append("Start-loss with no rescue start codon -> Moderate (per SVI).")
    return PVS1Strength.MODERATE


def _exon_deletion(f: PVS1Features, p: list[str]) -> PVS1Strength:
    if not f.exon_skip_preserves_frame:
        p.append("Out-of-frame exon deletion -> full strength.")
        return PVS1Strength.VERY_STRONG
    if f.removes_critical_region or f.fraction_protein_lost > 0.10:
        p.append("In-frame deletion of a critical region / >10% -> Strong.")
        return PVS1Strength.STRONG
    p.append("In-frame deletion of a non-critical region -> Moderate.")
    return PVS1Strength.MODERATE


_DISPATCH = {
    "nonsense": _nonsense_frameshift,
    "frameshift": _nonsense_frameshift,
    "canonical_splice": _canonical_splice,
    "initiation_codon": _initiation_codon,
    "exon_deletion": _exon_deletion,
}


def evaluate_pvs1(f: PVS1Features) -> PVS1Result:
    path: list[str] = []
    if f.consequence not in NULL_CONSEQUENCES:
        path.append(f"Consequence '{f.consequence}' is not a null variant type "
                    "-> PVS1 not applicable.")
        return PVS1Result(PVS1Strength.NOT_APPLICABLE, path)
    if not f.lof_is_mechanism:
        path.append("Loss of function is not an established disease mechanism "
                    "for this gene -> PVS1 not applicable.")
        return PVS1Result(PVS1Strength.NOT_APPLICABLE, path)
    strength = _DISPATCH[f.consequence](f, path)
    return PVS1Result(strength, path)
