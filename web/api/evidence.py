"""
Corrected live-evidence adapter for MyVariant.info.

This supersedes curavar's stubbed ``MyVariantProvider`` for the web app. The
curavar ACMG engine is left completely untouched — this provider implements the
same ``collect(variant, ledger)`` protocol and writes the same kinds of raw
observations, so the pipeline, agents, and report consume it unchanged.

Why a rewrite was needed (all confirmed against the live API):

  1. rsIDs (and any variant that maps to >1 allele/position) come back as a JSON
     *array*, not an object. The old adapter did ``data.get(...)`` on it and
     crashed → the generic "Failed to fetch". We normalize to a list of records
     and merge fields across them.
  2. ``GET /v1/variant/{hgvs}`` defaults to **hg19/GRCh37**. Our coordinates are
     **GRCh38**, so hg38 HGVS 404'd. We send ``assembly=hg38`` (configurable) and
     fall back to the ``/query`` route.
  3. The data-bearing record isn't always the first hit; we scan all hits.
  4. ``dbnsfp.revel.score`` is a per-transcript *list*; we collapse it to a
     single number.

Failure modes are raised as three *distinct* exception types so the API can tell
the user apart: genuinely-not-in-database, upstream/network error, and
adapter/parse failure.
"""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from curavar.provenance import ProvenanceLedger, SourceType
from curavar.sources import Variant

VARIANT_URL = "https://myvariant.info/v1/variant/"
QUERY_URL = "https://myvariant.info/v1/query"
FIELDS = "dbnsfp.revel,gnomad_genome,gnomad_exome,clinvar"
DEFAULT_ASSEMBLY = "hg38"  # our bundled coordinates are GRCh38
_TIMEOUT = 30

_RSID_RE = re.compile(r"^rs\d+$", re.IGNORECASE)


# --- distinct failure types -------------------------------------------------


class EvidenceError(Exception):
    """Base for adapter failures. ``kind`` distinguishes the three modes."""

    kind = "error"


class EvidenceNotFound(EvidenceError):
    """The variant is genuinely not in MyVariant.info (for the given build)."""

    kind = "not_found"


class EvidenceUpstreamError(EvidenceError):
    """MyVariant.info was unreachable, timed out, or returned an HTTP error."""

    kind = "upstream"

    def __init__(self, message: str, timeout: bool = False):
        super().__init__(message)
        self.timeout = timeout


class EvidenceParseError(EvidenceError):
    """MyVariant.info responded, but the payload couldn't be parsed/extracted."""

    kind = "parse"


# --- small helpers ----------------------------------------------------------


def _as_records(data: Any) -> list[dict]:
    """Normalize a MyVariant response (dict | list | {hits:[...]}) to a list."""
    if data is None:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        if "hits" in data and isinstance(data["hits"], list):
            return [r for r in data["hits"] if isinstance(r, dict)]
        if data.get("error") or data.get("notfound"):
            return []
        return [data]
    return []


def _has_evidence_fields(rec: dict) -> bool:
    return any(k in rec for k in ("gnomad_genome", "gnomad_exome", "clinvar", "dbnsfp"))


def _first(records: list[dict], key: str) -> Optional[dict]:
    for r in records:
        v = r.get(key)
        if isinstance(v, dict) and v:
            return v
    return None


def _revel_scalar(dbnsfp: dict) -> Optional[float]:
    revel = dbnsfp.get("revel")
    score = revel.get("score") if isinstance(revel, dict) else revel
    if isinstance(score, list):
        nums = [s for s in score if isinstance(s, (int, float))]
        return max(nums) if nums else None
    return score if isinstance(score, (int, float)) else None


def _hgvs_part(entries, prefix: str) -> str:
    """Pull the ``c.``/``p.`` part from a ClinVar hgvs list, preferring NM_/NP_."""
    if isinstance(entries, str):
        entries = [entries]
    if not isinstance(entries, list):
        return ""
    picked = ""
    for e in entries:
        tail = e.split(":", 1)[1] if ":" in e else e
        if not tail.startswith(prefix):
            continue
        if e.startswith(("NM_", "NP_")):
            return tail
        picked = picked or tail
    return picked


# --- ClinVar assertion summary ---------------------------------------------
# MyVariant's ClinVar object has NO single aggregate significance field — only a
# per-condition ``rcv`` list, each with its own clinical_significance and review
# status. Concatenating every entry ("Benign; Uncertain significance; …") is
# noise. We derive ONE clean headline classification, weighted by ClinVar's
# review-status "star" level, and flag genuine conflict honestly. Raw values are
# preserved in the ledger payload for provenance.

_TIER_DISPLAY = {
    "benign": "Benign",
    "likely benign": "Likely benign",
    "benign/likely benign": "Benign/Likely benign",
    "uncertain significance": "Uncertain significance",
    "likely pathogenic": "Likely pathogenic",
    "pathogenic": "Pathogenic",
    "pathogenic/likely pathogenic": "Pathogenic/Likely pathogenic",
}
_BENIGN_SET = {"benign", "likely benign", "benign/likely benign"}
_PATH_SET = {"pathogenic", "likely pathogenic", "pathogenic/likely pathogenic"}
_CONFLICT_SET = {
    "conflicting interpretations of pathogenicity",
    "conflicting interpretations",
    "conflicting classifications of pathogenicity",
    "conflicting data from submitters",
}


def _review_weight(review_status: Optional[str]) -> int:
    """ClinVar review status -> star level (higher = more authoritative)."""
    rs = (review_status or "").lower()
    if "practice guideline" in rs:
        return 4
    if "expert panel" in rs:
        return 3
    if "multiple submitters" in rs and "no conflict" in rs:
        return 2
    if "single submitter" in rs or "criteria provided" in rs or "conflicting" in rs:
        return 1
    return 0


def _review_phrase(weight: int) -> str:
    return {
        4: "practice guideline",
        3: "expert-panel reviewed",
        2: "multiple submitters, no conflicts",
        1: "criteria provided",
        0: "no assertion criteria",
    }.get(weight, "criteria provided")


def summarize_clinvar(rcv: Any) -> Optional[dict]:
    """Summarize a ClinVar ``rcv`` (single object or list) into one clean call.

    Returns a dict with a single ``headline`` classification, a brief
    ``review_summary``, a ``conflicting`` flag, a clean ``snippet``, and the
    deduped raw values for provenance — or None if there is no assertion.
    """
    rcvs = rcv if isinstance(rcv, list) else ([rcv] if isinstance(rcv, dict) else [])
    tiers: dict[str, dict] = {}  # display tier -> {w, n, rs, cond}
    raw: list[str] = []
    other: list[str] = []
    explicit_conflict = False
    total_submitters = 0

    for item in rcvs:
        if not isinstance(item, dict):
            continue
        sig = item.get("clinical_significance")
        if not sig:
            continue
        review_status = item.get("review_status")
        weight = _review_weight(review_status)
        cond = item.get("conditions")
        cond_name = cond.get("name") if isinstance(cond, dict) else None
        try:
            total_submitters += int(item.get("number_submitters") or 0)
        except (TypeError, ValueError):
            pass
        # a single rcv significance can itself be compound ("X; association; other")
        for part in str(sig).split(";"):
            term = part.strip()
            if not term:
                continue
            low = term.lower()
            if low not in {r.lower() for r in raw}:
                raw.append(term)
            if low in _CONFLICT_SET:
                explicit_conflict = True
            elif low in _TIER_DISPLAY:
                disp = _TIER_DISPLAY[low]
                cur = tiers.get(disp)
                if cur is None:
                    tiers[disp] = {"w": weight, "n": 1, "rs": review_status, "cond": cond_name}
                else:
                    cur["n"] += 1
                    if weight > cur["w"]:
                        cur.update({"w": weight, "rs": review_status, "cond": cond_name})
            elif term not in other:
                other.append(term)

    if not tiers and not explicit_conflict and not other:
        return None

    benign_present = any(t.lower() in _BENIGN_SET for t in tiers)
    path_present = any(t.lower() in _PATH_SET for t in tiers)
    # genuine conflict: ClinVar says so, or benign-side AND pathogenic-side coexist
    conflicting = explicit_conflict or (benign_present and path_present)

    if conflicting:
        best = max(tiers.values(), key=lambda d: d["w"]) if tiers else {}
        return {
            "headline": "Conflicting interpretations",
            "review_summary": "conflicting submitter interpretations",
            "conflicting": True,
            "review_status": best.get("rs"),
            "condition": None,
            "raw_significances": raw,
            "other_assertions": other,
            "total_submitters": total_submitters or None,
            "snippet": "ClinVar: Conflicting interpretations across submitters.",
        }

    if tiers:
        # dominant = highest review weight, then most conditions asserting it
        dominant = max(tiers, key=lambda t: (tiers[t]["w"], tiers[t]["n"]))
        info = tiers[dominant]
        return {
            "headline": dominant,
            "review_summary": _review_phrase(info["w"]),
            "conflicting": False,
            "review_status": info["rs"],
            "condition": info["cond"],
            "raw_significances": raw,
            "other_assertions": other,
            "total_submitters": total_submitters or None,
            "snippet": f"ClinVar: {dominant} ({_review_phrase(info['w'])}).",
        }

    # only non-germline assertion types (e.g. "drug response", "association")
    label = ", ".join(other[:2])
    return {
        "headline": label,
        "review_summary": "not a germline pathogenicity assertion",
        "conflicting": False,
        "review_status": None,
        "condition": None,
        "raw_significances": raw,
        "other_assertions": other,
        "total_submitters": total_submitters or None,
        "snippet": f"ClinVar: {label} (not a germline pathogenicity assertion).",
    }


# --- the provider -----------------------------------------------------------


class MyVariantEvidence:
    """Live evidence provider implementing curavar's SourceProvider protocol.

    Construct with an rsID or a genomic HGVS and an assembly (default hg38).
    ``fetch()`` performs one network round-trip (cached), classifying failures.
    ``collect()`` replays the cached records into the pipeline's ledger.
    """

    def __init__(self, query_id: str, assembly: str = DEFAULT_ASSEMBLY):
        self.query_id = (query_id or "").strip()
        self.assembly = (assembly or DEFAULT_ASSEMBLY).lower()
        if self.assembly not in ("hg38", "hg19"):
            self.assembly = DEFAULT_ASSEMBLY
        self._records: Optional[list[dict]] = None

    # -- HTTP ---------------------------------------------------------------

    def _get(self, url: str) -> Any:
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"__http404__": True}
            raise EvidenceUpstreamError(
                f"MyVariant.info returned HTTP {exc.code}."
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise EvidenceUpstreamError(
                "MyVariant.info timed out.", timeout=True
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise EvidenceUpstreamError(
                    "MyVariant.info timed out.", timeout=True
                ) from exc
            raise EvidenceUpstreamError(
                f"Couldn't reach MyVariant.info: {exc.reason}."
            ) from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EvidenceParseError(
                "MyVariant.info returned a response that wasn't valid JSON."
            ) from exc

    def _variant_route(self, ident: str) -> Any:
        url = (
            VARIANT_URL
            + urllib.parse.quote(ident, safe="")
            + f"?fields={FIELDS}&assembly={self.assembly}"
        )
        return self._get(url)

    def _query_route(self, term: str) -> Any:
        url = (
            QUERY_URL
            + "?q="
            + urllib.parse.quote(term, safe="")
            + f"&fields={FIELDS}&assembly={self.assembly}&size=10"
        )
        return self._get(url)

    # -- fetch + normalize --------------------------------------------------

    def fetch(self) -> list[dict]:
        """Return the list of MyVariant records for this query (cached).

        Raises EvidenceNotFound / EvidenceUpstreamError / EvidenceParseError.
        """
        if self._records is not None:
            return self._records
        if not self.query_id:
            raise EvidenceNotFound("No variant identifier was provided.")

        is_rsid = bool(_RSID_RE.match(self.query_id))
        if is_rsid:
            records = _as_records(self._query_route(self.query_id))
        else:
            raw = self._variant_route(self.query_id)
            if isinstance(raw, dict) and raw.get("__http404__"):
                records = []
            else:
                records = _as_records(raw)
            # Fall back to the query route if the variant route found nothing
            # usable (e.g. an indel whose normalized _id differs from the input).
            if not any(_has_evidence_fields(r) for r in records):
                records = _as_records(self._query_route(self.query_id)) or records

        usable = [r for r in records if _has_evidence_fields(r)]
        if not usable:
            raise EvidenceNotFound(
                f"No record for '{self.query_id}' in MyVariant.info "
                f"(assembly {self.assembly})."
            )
        self._records = usable
        return usable

    # -- derived metadata for a nicer Variant label -------------------------

    def variant_meta(self) -> dict[str, str]:
        recs = self.fetch()
        clinvar = _first(recs, "clinvar") or {}
        best = next((r for r in recs if "clinvar" in r or "gnomad_genome" in r), recs[0])
        hgvs = clinvar.get("hgvs", {}) if isinstance(clinvar, dict) else {}
        gene = ""
        g = clinvar.get("gene") if isinstance(clinvar, dict) else None
        if isinstance(g, dict):
            gene = g.get("symbol", "") or ""
        return {
            "gene": gene,
            "hgvs_c": _hgvs_part(hgvs.get("coding", []), "c.") or self.query_id,
            "hgvs_p": _hgvs_part(hgvs.get("protein", []), "p."),
            "genome_build": "GRCh38" if self.assembly == "hg38" else "GRCh37",
            "coordinate": str(best.get("_id", self.query_id)),
        }

    def build_variant(self, fallback_hgvs: str = "") -> Variant:
        m = self.variant_meta()
        return Variant(
            gene=m["gene"],
            hgvs_c=m["hgvs_c"] or fallback_hgvs or self.query_id,
            hgvs_p=m["hgvs_p"],
            genome_build=m["genome_build"],
            coordinate=m["coordinate"],
        )

    # -- collect (SourceProvider protocol) ----------------------------------

    def collect(self, variant: Variant, ledger: ProvenanceLedger) -> None:
        records = self.fetch()
        recorded = 0
        asm = self.assembly

        # population frequency: gnomAD genome, else exome
        gnomad = _first(records, "gnomad_genome") or _first(records, "gnomad_exome")
        if gnomad:
            af = (gnomad.get("af") or {}).get("af")
            ac = (gnomad.get("ac") or {}).get("ac")
            an = (gnomad.get("an") or {}).get("an")
            hom = (gnomad.get("hom") or {}).get("hom") if isinstance(gnomad.get("hom"), dict) else gnomad.get("hom")
            if af is not None:
                ledger.record(
                    source_type=SourceType.POPULATION_DB,
                    source_name="gnomAD via MyVariant.info",
                    locator=f"{self.query_id} ({asm})",
                    payload={"global_af": af, "allele_count": ac,
                             "allele_number": an, "homozygotes": hom},
                    snippet=f"gnomAD global allele frequency {af}"
                            + (f" ({ac} alleles)." if ac is not None else "."),
                )
                recorded += 1

        # ClinVar assertion(s): one clean headline, raw kept for provenance.
        clinvar = _first(records, "clinvar")
        if clinvar:
            summary = summarize_clinvar(clinvar.get("rcv"))
            if summary:
                ledger.record(
                    source_type=SourceType.CLINICAL_DB,
                    source_name="ClinVar via MyVariant.info",
                    locator=str(clinvar.get("allele_id") or clinvar.get("variant_id") or self.query_id),
                    payload={
                        # clean, human-facing headline (single classification)
                        "aggregate_assertion": summary["headline"],
                        "review_summary": summary["review_summary"],
                        "conflicting": summary["conflicting"],
                        "review_status": summary["review_status"],
                        "condition": summary["condition"],
                        "total_submitters": summary["total_submitters"],
                        # raw values preserved for provenance / audit
                        "raw_significances": summary["raw_significances"],
                        "other_assertions": summary["other_assertions"],
                    },
                    snippet=summary["snippet"],
                )
                recorded += 1

        # in-silico predictor (REVEL from dbNSFP)
        dbnsfp = _first(records, "dbnsfp") or {}
        revel = _revel_scalar(dbnsfp)
        if revel is not None:
            ledger.record(
                source_type=SourceType.IN_SILICO,
                source_name="REVEL via dbNSFP / MyVariant.info",
                locator=f"{self.query_id} ({asm})",
                payload={"revel": revel},
                snippet=f"REVEL score {revel} "
                        + ("(supports a deleterious effect)." if revel >= 0.5
                           else "(does not support a deleterious effect)."),
            )
            recorded += 1

        if recorded == 0:
            raise EvidenceNotFound(
                f"MyVariant.info has a record for '{self.query_id}' but no usable "
                "population, clinical, or predictor evidence for it."
            )
