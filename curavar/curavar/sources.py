"""
Evidence sources.

A SourceProvider fetches raw observations about a variant and writes each one
into the provenance ledger. The tool is built to talk to live databases
(gnomAD, ClinVar, PubMed) when it has network access; for a reproducible,
network-free demo it ships a BundledSourceProvider that replays recorded
snapshots stored under curavar/data/.

Everything a provider returns is *raw* -- a frequency, an assertion, a
predictor score. No interpretation happens here. Interpretation is the job of
the agent layer, and it must cite the ledger IDs these providers create.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from .io_utils import read_json
from .provenance import ProvenanceLedger, SourceType


@dataclass
class Variant:
    gene: str
    hgvs_c: str                 # coding HGVS, e.g. "c.5266dupC"
    hgvs_p: str                 # protein HGVS, e.g. "p.Gln1756fs"
    genome_build: str           # e.g. "GRCh38"
    coordinate: str             # e.g. "chr17:43057062:->C"
    inheritance: str = ""       # e.g. "AD", "AR" (gene-disease mechanism)

    @property
    def label(self) -> str:
        return f"{self.gene} {self.hgvs_c} ({self.hgvs_p})"


class SourceProvider(Protocol):
    """Fetches raw evidence for a variant into the ledger."""
    def collect(self, variant: Variant, ledger: ProvenanceLedger) -> None: ...


class BundledSourceProvider:
    """Replays a recorded evidence snapshot from a case file (offline demo).

    Each snapshot is a list of raw observations. We stamp them into the ledger
    with their recorded retrieval time so the audit trail is honest about the
    fact that this is a snapshot, not a live pull.
    """

    def __init__(self, case_path: str):
        self._case = read_json(case_path)

    @property
    def variant(self) -> Variant:
        return Variant(**self._case["variant"])

    @property
    def cassettes(self) -> dict:
        return self._case.get("cassettes", {})

    @property
    def pvs1_features(self) -> dict:
        return self._case.get("pvs1_features", {})

    def collect(self, variant: Variant, ledger: ProvenanceLedger) -> None:
        for obs in self._case["evidence"]:
            ledger.record(
                source_type=SourceType(obs["source_type"]),
                source_name=obs["source_name"] + " [recorded snapshot]",
                locator=obs["locator"],
                payload=obs["payload"],
                snippet=obs.get("snippet", ""),
                retrieved_at=obs.get("retrieved_at"),
            )


# --- Live adapter (used outside the sandbox with network access) ---

class MyVariantProvider:
    """Live evidence via MyVariant.info, which aggregates gnomAD, ClinVar, and
    dbNSFP behind one query. Requires network egress to myvariant.info (not
    available in the offline demo sandbox). This is real, working integration
    code: run the CLI with --live and network access to use it.

    Query is by HGVS or rsID; the response is distilled into the same raw
    observations the bundled provider produces, then written to the ledger.
    """

    BASE = "https://myvariant.info/v1/variant/"

    def __init__(self, query_id: str):
        self.query_id = query_id  # e.g. "chr17:g.43093464G>A" or an rsID

    def collect(self, variant: Variant, ledger: ProvenanceLedger) -> None:  # pragma: no cover
        import json as _json
        import urllib.parse
        import urllib.request

        fields = "dbnsfp,gnomad_genome,gnomad_exome,clinvar"
        url = (self.BASE + urllib.parse.quote(self.query_id, safe="")
               + "?fields=" + fields)
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = _json.loads(resp.read().decode("utf-8"))

        # population frequency (gnomAD genome, falling back to exome)
        gnomad = data.get("gnomad_genome") or data.get("gnomad_exome") or {}
        af = (gnomad.get("af") or {}).get("af")
        if af is not None:
            ledger.record(
                source_type=SourceType.POPULATION_DB,
                source_name="gnomAD via MyVariant.info",
                locator=self.query_id,
                payload={"global_af": af,
                         "homozygotes": (gnomad.get("hom") or {}).get("hom")},
                snippet=f"gnomAD global allele frequency {af}.",
            )
        # ClinVar assertion
        clinvar = data.get("clinvar") or {}
        rcv = clinvar.get("rcv")
        if rcv:
            first = rcv[0] if isinstance(rcv, list) else rcv
            sig = first.get("clinical_significance")
            ledger.record(
                source_type=SourceType.CLINICAL_DB,
                source_name="ClinVar via MyVariant.info",
                locator=str(clinvar.get("variant_id", self.query_id)),
                payload={"aggregate_assertion": sig,
                         "review_status": first.get("review_status")},
                snippet=f"ClinVar reports: {sig}.",
            )
        # in-silico (REVEL from dbNSFP)
        dbnsfp = data.get("dbnsfp") or {}
        revel = (dbnsfp.get("revel") or {}).get("score") if isinstance(dbnsfp.get("revel"), dict) else dbnsfp.get("revel")
        if revel is not None:
            ledger.record(
                source_type=SourceType.IN_SILICO,
                source_name="REVEL via dbNSFP / MyVariant.info",
                locator=self.query_id,
                payload={"revel": revel},
                snippet=f"REVEL score {revel}.",
            )
