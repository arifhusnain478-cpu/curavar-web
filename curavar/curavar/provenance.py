"""
Provenance ledger: the auditable backbone of CuraVar.

Every fact the system uses to classify a variant is recorded here as an
append-only Evidence entry. Every classification decision references the
evidence IDs it relied on. The ledger is hash-chained (each entry commits
to the previous one) so that a reviewer can verify nothing was silently
altered or reordered after the fact.

Design principle: the ledger contains *no* interpretation. It only records
"here is a raw observation, here is where it came from, here is when we
pulled it." Interpretation happens downstream and always points back here.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class SourceType(str, Enum):
    POPULATION_DB = "population_db"      # e.g. gnomAD allele frequencies
    CLINICAL_DB = "clinical_db"          # e.g. ClinVar submissions
    LITERATURE = "literature"            # e.g. PubMed abstracts / full text
    IN_SILICO = "in_silico"              # e.g. computational predictors
    FUNCTIONAL = "functional"            # e.g. reported functional assays
    GENE_CONTEXT = "gene_context"        # e.g. gene-disease mechanism facts
    SYNTHETIC = "synthetic"              # bundled demo data, clearly marked


@dataclass(frozen=True)
class Evidence:
    """A single raw observation with full traceability."""
    id: str
    source_type: SourceType
    source_name: str                     # human-readable source, e.g. "gnomAD v4.1"
    locator: str                         # stable pointer: accession, URL, PMID, coord
    retrieved_at: float                  # unix timestamp
    payload: dict[str, Any]              # the raw structured observation
    snippet: str = ""                    # verbatim excerpt supporting the payload
    prev_hash: str = ""                  # hash of the previous ledger entry
    entry_hash: str = ""                 # hash of THIS entry (computed on append)

    def _digest_basis(self) -> str:
        # Everything except entry_hash itself participates in the digest.
        basis = {
            "id": self.id,
            "source_type": self.source_type.value,
            "source_name": self.source_name,
            "locator": self.locator,
            "retrieved_at": round(self.retrieved_at, 6),
            "payload": self.payload,
            "snippet": self.snippet,
            "prev_hash": self.prev_hash,
        }
        return json.dumps(basis, sort_keys=True, separators=(",", ":"))

    def compute_hash(self) -> str:
        return hashlib.sha256(self._digest_basis().encode("utf-8")).hexdigest()


class ProvenanceLedger:
    """Append-only, hash-chained list of Evidence entries."""

    def __init__(self) -> None:
        self._entries: list[Evidence] = []
        self._by_id: dict[str, Evidence] = {}
        self._counter: int = 0

    def record(
        self,
        source_type: SourceType,
        source_name: str,
        locator: str,
        payload: dict[str, Any],
        snippet: str = "",
        retrieved_at: Optional[float] = None,
    ) -> Evidence:
        self._counter += 1
        eid = f"E{self._counter:04d}"
        prev_hash = self._entries[-1].entry_hash if self._entries else ""
        draft = Evidence(
            id=eid,
            source_type=source_type,
            source_name=source_name,
            locator=locator,
            retrieved_at=retrieved_at if retrieved_at is not None else time.time(),
            payload=payload,
            snippet=snippet,
            prev_hash=prev_hash,
        )
        entry_hash = draft.compute_hash()
        # dataclass is frozen, so rebuild with the hash filled in
        sealed = Evidence(**{**asdict(draft), "source_type": draft.source_type,
                             "entry_hash": entry_hash})
        self._entries.append(sealed)
        self._by_id[eid] = sealed
        return sealed

    def get(self, eid: str) -> Evidence:
        return self._by_id[eid]

    def all(self) -> list[Evidence]:
        return list(self._entries)

    def verify(self) -> tuple[bool, list[str]]:
        """Re-walk the chain and confirm no entry was altered or reordered."""
        problems: list[str] = []
        prev = ""
        for e in self._entries:
            if e.prev_hash != prev:
                problems.append(f"{e.id}: prev_hash mismatch (chain broken)")
            recomputed = e.compute_hash()
            if recomputed != e.entry_hash:
                problems.append(f"{e.id}: content hash mismatch (entry altered)")
            prev = e.entry_hash
        return (len(problems) == 0, problems)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ledger_version": 1,
            "entry_count": len(self._entries),
            "entries": [
                {**asdict(e), "source_type": e.source_type.value}
                for e in self._entries
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
