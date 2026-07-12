"""
Service layer: the bridge between the web API and the CuraVar engine.

Every classification, triage, report and ledger the API returns is produced by
the *unmodified* ``curavar`` package. This module does three things and nothing
more:

  1. Make ``curavar`` importable and locate its bundled demo cases.
  2. Run the engine (replay by default; live when a key is present and asked for).
  3. Serialize the engine's rich result objects into plain JSON-able dicts the
     browser can render, preserving full provenance (every criterion -> evidence,
     the PVS1 decision path, and the hash-chained ledger).

No classification math lives here. If you find yourself computing a tier or a
point total in this file, it belongs in ``curavar`` instead.
"""

from __future__ import annotations

import glob
import os
import re
import socket
import sys
import urllib.error
from dataclasses import dataclass, replace
from typing import Any, Optional

# --- load web/api/.env so the Anthropic key can live in a file --------------
# Loaded once at import, before any request reads the environment. Absent or
# blank key -> the app stays in offline replay mode. python-dotenv is optional:
# if it isn't installed the app still runs (just without .env autoloading).
try:  # pragma: no cover - trivial import guard
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ModuleNotFoundError:  # pragma: no cover
    pass

# --- make the curavar package importable ------------------------------------
# In Docker / an installed environment ``import curavar`` resolves to the
# installed package. For local ``uvicorn web.api.main:app`` run from the repo
# root, the sibling ``curavar/`` *repo* directory (which has no __init__.py)
# would otherwise be picked up as an empty namespace package and shadow the real
# one. Prepend the package repo root (…/curavar, which contains the actual
# ``curavar/`` package) to sys.path first so the real source package always wins.
_CURAVAR_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "curavar")
)
if os.path.isfile(os.path.join(_CURAVAR_REPO, "curavar", "__init__.py")):
    if _CURAVAR_REPO not in sys.path:
        sys.path.insert(0, _CURAVAR_REPO)

import curavar  # noqa: E402

# Guard against the namespace-package shadow: a real package has a __file__.
if getattr(curavar, "__file__", None) is None:  # pragma: no cover
    raise ImportError(
        "The 'curavar' package resolved to a namespace package, not the engine. "
        "Install it (`pip install -e ./curavar`) or run from the repo root."
    )

from curavar.acmg import CRITERIA, points_for
from curavar.llm import LLMClient
from curavar.pipeline import CuraVarPipeline, CuraVarResult
from curavar.provenance import ProvenanceLedger
from curavar.report import render_report
from curavar.sources import BundledSourceProvider, Variant
from curavar.triage import summary_counts, triage_cases
from curavar.triage_report import render_triage

# Corrected live-evidence adapter (see web/api/evidence.py). The curavar engine
# is untouched; this provides the same collect(variant, ledger) protocol.
from .evidence import (
    EvidenceNotFound,
    EvidenceParseError,
    EvidenceUpstreamError,
    MyVariantEvidence,
)

TOOL_VERSION = "0.1.0"

DATA_DIR = os.path.join(os.path.dirname(curavar.__file__), "data")
# truth_set.json is a labeled benchmark set, not a variant case (it has no
# "variant" key). Everything else in data/ is a bundled demo case.
_NON_CASE_FILES = {"truth_set.json"}


class CaseError(Exception):
    """Raised when a requested case/variant cannot be classified offline.

    Carries an HTTP-ish status hint so the route layer can map it cleanly.
    """

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Case registry: discover the bundled demo cases and index them by a stable id.
# The id is the case-file basename without extension (e.g. "brca1_c5266dupC").
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseInfo:
    id: str
    path: str
    gene: str
    hgvs_c: str
    hgvs_p: str
    label: str
    synthetic: bool


def _load_registry() -> dict[str, CaseInfo]:
    registry: dict[str, CaseInfo] = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        if os.path.basename(path) in _NON_CASE_FILES:
            continue
        try:
            prov = BundledSourceProvider(path)
            v = prov.variant
        except (KeyError, ValueError):
            # Not a well-formed case file; skip it rather than crash discovery.
            continue
        cid = os.path.splitext(os.path.basename(path))[0]
        registry[cid] = CaseInfo(
            id=cid,
            path=path,
            gene=v.gene,
            hgvs_c=v.hgvs_c,
            hgvs_p=v.hgvs_p,
            label=v.label,
            synthetic="synthetic" in (v.coordinate or "").lower()
            or v.gene.upper().startswith("DEMO"),
        )
    return registry


_REGISTRY: dict[str, CaseInfo] = _load_registry()


def list_cases() -> list[CaseInfo]:
    return list(_REGISTRY.values())


def get_case(case_id: str) -> Optional[CaseInfo]:
    return _REGISTRY.get(case_id)


def all_case_paths() -> list[str]:
    return [c.path for c in _REGISTRY.values()]


def live_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _norm_hgvs(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


def _match_hgvs(hgvs: str) -> Optional[CaseInfo]:
    """Best-effort match of a free-text HGVS (or 'GENE c.xxx' label) to a
    bundled case, so the offline demo can classify by typing a variant."""
    q = _norm_hgvs(hgvs)
    if not q:
        return None
    for info in _REGISTRY.values():
        candidates = {
            _norm_hgvs(info.hgvs_c),
            _norm_hgvs(f"{info.gene}{info.hgvs_c}"),
            _norm_hgvs(info.label),
            _norm_hgvs(f"{info.gene}:{info.hgvs_c}"),
        }
        if q in candidates:
            return info
    return None


# ---------------------------------------------------------------------------
# Running the engine.
# ---------------------------------------------------------------------------


def _resolve_case_path(
    case_id: Optional[str] = None,
    case_path: Optional[str] = None,
) -> str:
    """Resolve a request to a bundled case file path, confined to DATA_DIR.

    Accepting an arbitrary server path would be a file-read primitive, so a
    supplied ``case_path`` is normalized and must resolve inside the data dir.
    """
    if case_id:
        info = get_case(case_id)
        if not info:
            raise CaseError(
                f"Unknown case id '{case_id}'. Known ids: "
                f"{', '.join(sorted(_REGISTRY)) or '(none)'}.",
                status=404,
            )
        return info.path
    if case_path:
        # allow a bare basename or a path; confine to DATA_DIR
        candidate = os.path.abspath(
            case_path
            if os.path.isabs(case_path)
            else os.path.join(DATA_DIR, os.path.basename(case_path))
        )
        if os.path.commonpath([candidate, DATA_DIR]) != DATA_DIR:
            raise CaseError("case_path must reference a bundled case.", status=400)
        if not os.path.isfile(candidate):
            raise CaseError(f"No such bundled case: {case_path}", status=404)
        return candidate
    raise CaseError("Provide one of: case_id, case_path, variant, or hgvs.", status=400)


def run_bundled(case_path: str, strict: bool = False) -> tuple[BundledSourceProvider, CuraVarResult]:
    """Run a bundled case in offline replay mode (deterministic, no network)."""
    prov = BundledSourceProvider(case_path)
    llm = LLMClient(mode="replay", cassettes=prov.cassettes)
    result = CuraVarPipeline(source=prov, llm=llm).run(
        prov.variant, pvs1_features=prov.pvs1_features, strict=strict
    )
    return prov, result


def _raise_evidence(query_id: str, exc: Exception) -> "CaseError":
    """Map the adapter's three distinct failure types to distinguishable,
    user-facing messages and statuses. Never leaks a stack trace."""
    if isinstance(exc, EvidenceNotFound):
        return CaseError(
            f"{exc} It may be genuinely absent for this genome build, or an indel "
            "whose normalized ID differs — try the rsID (e.g. rs1801133), or "
            "switch the build (hg38/hg19).",
            status=404,
        )
    if isinstance(exc, EvidenceUpstreamError):
        return CaseError(
            f"Live evidence is unavailable: {exc} This is an upstream/network "
            "problem, not your variant — try again shortly, or use a bundled case.",
            status=504 if getattr(exc, "timeout", False) else 502,
        )
    if isinstance(exc, EvidenceParseError):
        return CaseError(
            f"MyVariant.info responded but the evidence couldn't be parsed "
            f"(adapter issue): {exc}",
            status=502,
        )
    return CaseError(f"Failed to gather live evidence for '{query_id}'.", status=502)


def run_live(
    variant: Variant,
    query_id: str,
    strict: bool = False,
    assembly: str = "hg38",
) -> CuraVarResult:
    """Run against live evidence (MyVariant.info) + live Claude reasoning.

    Failure modes are surfaced as *distinguishable* errors: variant not in the
    database (404), upstream/network/timeout (502/504), adapter parse issue
    (502), missing/bad key (400/502). No raw stack trace ever reaches the client.
    """
    if not live_available():
        raise CaseError(
            "Live lookup needs an Anthropic API key on the server. Add it to "
            "web/api/.env (ANTHROPIC_API_KEY=…) and restart the API.",
            status=400,
        )

    provider = MyVariantEvidence(query_id=query_id, assembly=assembly)

    # 1. Pre-flight evidence fetch — classify the failure before any LLM spend.
    try:
        provider.fetch()
        enriched = provider.build_variant(fallback_hgvs=variant.hgvs_c)
        if not enriched.gene and variant.gene:
            enriched = replace(enriched, gene=variant.gene)
    except (EvidenceNotFound, EvidenceUpstreamError, EvidenceParseError) as exc:
        raise _raise_evidence(query_id, exc)

    # 2. Deterministic engine + live Claude reasoning (evidence already cached).
    llm = LLMClient(mode="live")
    try:
        return CuraVarPipeline(source=provider, llm=llm).run(enriched, strict=strict)
    except CaseError:
        raise
    except (EvidenceNotFound, EvidenceUpstreamError, EvidenceParseError) as exc:
        raise _raise_evidence(query_id, exc)
    except (TimeoutError, socket.timeout):
        raise CaseError("The live reasoning request timed out. Please try again.", status=504)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise CaseError(
                "The Anthropic API key was rejected. Check the key in web/api/.env.",
                status=502,
            )
        if exc.code == 429:
            raise CaseError(
                "The Anthropic API is rate-limiting right now. Please retry shortly.",
                status=502,
            )
        raise CaseError(f"An upstream service returned an error ({exc.code}).", status=502)
    except urllib.error.URLError:
        raise CaseError(
            "Couldn't reach the live reasoning service (network issue).", status=502
        )
    except ValueError:
        # e.g. the model returned something that wasn't the expected JSON
        raise CaseError(
            "The live reasoning response couldn't be parsed. Please retry.", status=502
        )
    except Exception:
        raise CaseError(
            "Live classification failed unexpectedly. Please retry or use a bundled case.",
            status=502,
        )


def classify(
    *,
    case_id: Optional[str] = None,
    case_path: Optional[str] = None,
    hgvs: Optional[str] = None,
    variant: Optional[dict] = None,
    live: bool = False,
    strict: bool = False,
    assembly: str = "hg38",
) -> dict[str, Any]:
    """Classify one variant and return a fully-serialized, provenance-complete
    result. Resolution order: explicit case -> hgvs match -> live variant."""
    # 1. explicit bundled case
    if case_id or case_path:
        path = _resolve_case_path(case_id=case_id, case_path=case_path)
        cid = os.path.splitext(os.path.basename(path))[0]
        _, result = run_bundled(path, strict=strict)
        return serialize_result(result, variant_id=cid, mode="replay", strict=strict)

    # 2. free-text HGVS — auto-routed. The caller just sends the variant; the
    #    server decides how to classify it:
    #      a) it matches a bundled evidence snapshot  -> classify offline, instantly
    #      b) otherwise, if a server key is configured -> do the live lookup
    #      c) otherwise                                -> a clean, distinguishable signal
    #    (``live=True`` still force-selects the live path so an explicit request
    #    surfaces the "needs a key" error rather than silently falling through.)
    if hgvs:
        match = _match_hgvs(hgvs)
        if match:
            _, result = run_bundled(match.path, strict=strict)
            return serialize_result(result, variant_id=match.id, mode="replay", strict=strict)
        if live or live_available():
            # run_live raises a clear 400 if the server has no API key.
            v = Variant(gene="", hgvs_c=hgvs, hgvs_p="", genome_build="", coordinate=hgvs)
            result = run_live(v, query_id=hgvs, strict=strict, assembly=assembly)
            return serialize_result(result, variant_id=_slug(hgvs), mode="live", strict=strict)
        raise CaseError(
            f"'{hgvs}' isn't one of the bundled example variants, and live lookup "
            f"isn't enabled on this server. Try a bundled variant "
            f"({', '.join(c.hgvs_c for c in list_cases())}).",
            status=422,
        )

    # 3. full variant object (live only)
    if variant:
        try:
            v = Variant(**variant)
        except TypeError as exc:
            raise CaseError(f"Malformed variant object: {exc}", status=422)
        query = variant.get("coordinate") or variant.get("hgvs_c") or v.label
        result = run_live(v, query_id=query, strict=strict, assembly=assembly)
        return serialize_result(result, variant_id=_slug(v.label), mode="live", strict=strict)

    raise CaseError("Provide one of: case_id, case_path, hgvs, or variant.", status=400)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "variant"


# ---------------------------------------------------------------------------
# Serialization: engine objects -> plain dicts (JSON-ready), provenance intact.
# ---------------------------------------------------------------------------


def _evidence_view(ev) -> dict[str, Any]:
    return {
        "id": ev.id,
        "source_type": ev.source_type.value,
        "source_name": ev.source_name,
        "locator": ev.locator,
        "snippet": ev.snippet,
        "retrieved_at": ev.retrieved_at,
        "entry_hash": ev.entry_hash,
        "prev_hash": ev.prev_hash,
        "payload": ev.payload,
    }


def serialize_result(
    result: CuraVarResult,
    variant_id: str,
    mode: str = "replay",
    strict: bool = False,
) -> dict[str, Any]:
    v = result.variant
    rec = result.reconciled
    cls = result.classification
    pts = result.points
    ledger_ok, ledger_problems = result.ledger.verify()
    by_id = {e.id: e for e in result.ledger.all()}

    # activated criteria, each traced to its evidence entries
    activated = []
    for c in result.activated:
        direction, _, desc = CRITERIA[c.code]
        activated.append(
            {
                "code": c.code,
                "direction": direction.value,
                "strength": c.strength.value,
                "description": desc,
                "justification": c.justification,
                "points": points_for(c),
                "evidence_ids": c.evidence_ids,
                "evidence": [
                    _evidence_view(by_id[eid]) for eid in c.evidence_ids if eid in by_id
                ],
            }
        )

    # PVS1 decision path + reviewer-removed list, both pulled from the ledger
    pvs1 = None
    removed: list[dict[str, Any]] = []
    for e in result.ledger.all():
        if e.source_name == "CuraVar PVS1 decision tree":
            pvs1 = {"strength": e.payload.get("strength", ""), "path": e.payload.get("path", [])}
        if e.source_name == "CuraVar adjudicator":
            removed = list(e.payload.get("removed", []))

    return {
        "id": variant_id,
        "mode": mode,
        "strict": strict,
        "variant": {
            "gene": v.gene,
            "hgvs_c": v.hgvs_c,
            "hgvs_p": v.hgvs_p,
            "genome_build": v.genome_build,
            "coordinate": v.coordinate,
            "inheritance": v.inheritance,
            "label": v.label,
        },
        "classification": {
            "headline": rec.headline.value,
            "rule_based": cls.classification.value,
            "rule_fired": cls.rule_fired,
            "points_based": pts.classification.value,
            "methods_agree": rec.agree,
            "diverges_across_vus": rec.diverges_across_vus,
            "contradiction": cls.contradiction,
            "note": rec.note,
        },
        "points": {
            "score": pts.score,
            "pathogenic_points": pts.pathogenic_points,
            "benign_points": pts.benign_points,
            "classification": pts.classification.value,
            "conflict": pts.conflict,
            "distance_to_next": pts.distance_to_next,
            "breakdown": [{"code": code, "points": p} for code, p in pts.breakdown],
        },
        "activated_criteria": activated,
        "removed_criteria": removed,
        "pvs1": pvs1,
        "ledger": result.ledger.to_dict(),
        "ledger_verified": ledger_ok,
        "ledger_problems": ledger_problems,
    }


def report_html(case_id: str, strict: bool = False) -> str:
    path = _resolve_case_path(case_id=case_id)
    _, result = run_bundled(path, strict=strict)
    return render_report(result, tool_version=TOOL_VERSION)


def ledger_json(case_id: str, strict: bool = False) -> dict[str, Any]:
    path = _resolve_case_path(case_id=case_id)
    _, result = run_bundled(path, strict=strict)
    ledger_ok, ledger_problems = result.ledger.verify()
    return {
        "id": case_id,
        "variant": result.variant.label,
        "verified": ledger_ok,
        "problems": ledger_problems,
        **result.ledger.to_dict(),
    }


# ---------------------------------------------------------------------------
# Triage.
# ---------------------------------------------------------------------------


def _triage_item_view(it) -> dict[str, Any]:
    return {
        "id": _result_case_id(it),
        "variant": it.variant,
        "gene": it.gene,
        "headline": it.headline.value,
        "points": it.points,
        "bucket": it.bucket,
        "reason": it.reason,
        "priority": it.priority,
        "methods_agree": it.result.reconciled.agree,
        "ledger_verified": it.result.ledger.verify()[0],
    }


def _result_case_id(it) -> str:
    """Map a triage item back to its bundled case id via the variant label."""
    for info in _REGISTRY.values():
        if info.label == it.variant:
            return info.id
    return _slug(it.variant)


def triage(case_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Triage a set of bundled cases (default: all) into a prioritized worklist."""
    if case_ids:
        paths = []
        for cid in case_ids:
            info = get_case(cid)
            if not info:
                raise CaseError(f"Unknown case id '{cid}'.", status=404)
            paths.append(info.path)
    else:
        paths = all_case_paths()
    items = triage_cases(paths, mode="replay")
    return {
        "counts": summary_counts(items),
        "total": len(items),
        "items": [_triage_item_view(it) for it in items],
    }


def triage_html(case_ids: Optional[list[str]] = None) -> str:
    if case_ids:
        paths = [get_case(cid).path for cid in case_ids if get_case(cid)]
    else:
        paths = all_case_paths()
    items = triage_cases(paths, mode="replay")
    return render_triage(items, tool_version=TOOL_VERSION)


# ---------------------------------------------------------------------------
# VCF -> worklist. In offline replay we can only classify variants that have a
# bundled evidence snapshot, so VCF records are matched to bundled cases by
# their ID column (= case id) or by a CHROM:POS prefix of the case coordinate.
# Unmatched records are reported honestly rather than silently dropped.
# ---------------------------------------------------------------------------


def _match_vcf_record(chrom: str, pos: str, vid: str) -> Optional[CaseInfo]:
    if vid and vid != ".":
        # ID column may carry a case id directly
        if vid in _REGISTRY:
            return _REGISTRY[vid]
    coord_prefix = f"{chrom}:{pos}"
    for info in _REGISTRY.values():
        prov = BundledSourceProvider(info.path)
        if (prov.variant.coordinate or "").replace("chr", "chr").startswith(coord_prefix):
            return info
        # also allow chrom without 'chr'
        if (prov.variant.coordinate or "").startswith(f"chr{chrom.lstrip('chr')}:{pos}"):
            return info
    return None


def triage_vcf(vcf_text: str) -> dict[str, Any]:
    matched_ids: list[str] = []
    unmatched: list[dict[str, str]] = []
    seen: set[str] = set()
    records_seen = 0
    for line in (vcf_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = re.split(r"\s+", line)
        if len(cols) < 5:
            continue  # not a well-formed VCF data row (need CHROM POS ID REF ALT)
        records_seen += 1
        chrom, pos, vid, ref, alt = cols[0], cols[1], cols[2], cols[3], cols[4]
        info = _match_vcf_record(chrom, pos, vid)
        if info and info.id not in seen:
            matched_ids.append(info.id)
            seen.add(info.id)
        elif not info:
            unmatched.append({"chrom": chrom, "pos": pos, "id": vid, "ref": ref, "alt": alt})

    worklist = (
        triage(case_ids=matched_ids)
        if matched_ids
        else {"counts": summary_counts([]), "total": 0, "items": []}
    )
    worklist["matched"] = len(matched_ids)
    worklist["unmatched"] = unmatched
    if records_seen == 0:
        worklist["note"] = (
            "No variant records found in the uploaded file. A VCF needs data rows "
            "with at least CHROM POS ID REF ALT columns."
        )
    else:
        worklist["note"] = (
            "Offline replay classifies only variants with a bundled evidence snapshot; "
            "unmatched VCF records are listed but not classified (they need live evidence)."
        )
    return worklist
