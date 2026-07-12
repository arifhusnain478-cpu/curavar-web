"""
CuraVar Web API (FastAPI).

A thin, typed HTTP surface over the CuraVar engine. It classifies variants,
renders the auditable HTML report and triage dashboard, triages a variant set
into a worklist, and serves the raw provenance ledger for audit. All the
classification logic lives in the ``curavar`` package; this layer only routes,
validates, and serializes.

The Anthropic API key stays server-side: it is read from the environment inside
``curavar.llm`` and is never sent to or accepted from the browser. Classification
is auto-routed — a variant with a bundled evidence snapshot is replayed offline,
anything else is looked up live when a key is present — so the whole product is
demoable with no key at all, and the caller never picks a mode.

Docs: ``/docs`` (Swagger) and ``/redoc``.
"""

from __future__ import annotations

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import service
from .models import (
    CasesResponse,
    CaseSummary,
    ClassifyRequest,
    ClassifyResponse,
    ConfigResponse,
    LedgerResponse,
    TriageRequest,
    TriageResponse,
)

app = FastAPI(
    title="CuraVar Web API",
    version=service.TOOL_VERSION,
    description=(
        "Auditable ACMG/AMP variant curation. The classification math is "
        "deterministic and LLM-free (it lives in the `curavar` engine); this API "
        "only gathers evidence, runs the engine, and returns fully-traced results. "
        "Research decision-support, not a diagnostic device."
    ),
)

# Dev convenience: the Vite UI proxies /api -> here, but allow direct browser
# calls from the dev server origins too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://localhost:8080",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(service.CaseError)
async def _case_error_handler(_: Request, exc: service.CaseError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Last-resort guard: turn any unexpected error into a clean message. The
    # detail is logged server-side (uvicorn shows the traceback); the client
    # only ever sees a friendly line, never a stack trace.
    import logging

    logging.getLogger("curavar.web").exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on the server. Please try again."},
    )


# --------------------------------------------------------------------------- #
# Meta / discovery
# --------------------------------------------------------------------------- #


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": service.TOOL_VERSION}


@app.get("/config", response_model=ConfigResponse, tags=["meta"])
async def config() -> ConfigResponse:
    """Front-end capability probe: is a live lookup possible (``live_available``),
    and how many bundled demo cases exist. The front-end uses this to guide input,
    never to offer a mode toggle."""
    return ConfigResponse(
        version=service.TOOL_VERSION,
        live_available=service.live_available(),
        case_count=len(service.list_cases()),
    )


@app.get("/cases", response_model=CasesResponse, tags=["meta"])
async def cases() -> CasesResponse:
    """List the bundled demo variants the offline replay demo can classify."""
    return CasesResponse(
        cases=[
            CaseSummary(
                id=c.id,
                gene=c.gene,
                hgvs_c=c.hgvs_c,
                hgvs_p=c.hgvs_p,
                label=c.label,
                synthetic=c.synthetic,
            )
            for c in service.list_cases()
        ]
    )


# --------------------------------------------------------------------------- #
# Classify
# --------------------------------------------------------------------------- #


@app.post("/classify", response_model=ClassifyResponse, tags=["classify"])
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    """Run the CuraVar pipeline on one variant and return the full, traced result:
    the reconciled verdict, both scoring methods, every activated criterion tied
    to its evidence, the PVS1 decision path, and the hash-chained ledger."""
    data = service.classify(
        case_id=req.case_id,
        case_path=req.case_path,
        hgvs=req.hgvs,
        variant=req.variant,
        live=req.live,
        strict=req.strict,
        assembly=req.assembly,
    )
    return ClassifyResponse(**data)


@app.get("/variants/{variant_id}/report", response_class=HTMLResponse, tags=["classify"])
async def variant_report(
    variant_id: str,
    strict: bool = Query(False, description="Exclude circular criteria (PP5/BP6)."),
) -> HTMLResponse:
    """The self-contained, auditable HTML clinical report for a bundled variant."""
    return HTMLResponse(content=service.report_html(variant_id, strict=strict))


# --------------------------------------------------------------------------- #
# Triage
# --------------------------------------------------------------------------- #


@app.post("/triage", response_model=TriageResponse, tags=["triage"])
async def triage(req: TriageRequest | None = None) -> TriageResponse:
    """Triage a set of bundled cases into a prioritized worklist
    (REVIEW / ACT / CLEAR). Omit the body to triage every bundled variant."""
    case_ids = req.case_ids if req else None
    return TriageResponse(**service.triage(case_ids=case_ids))


@app.post("/triage/vcf", response_model=TriageResponse, tags=["triage"])
async def triage_vcf(file: UploadFile = File(..., description="A VCF file.")) -> TriageResponse:
    """Triage a VCF upload. Records are matched to bundled evidence snapshots for
    the offline demo; unmatched records are reported rather than silently dropped."""
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")
    return TriageResponse(**service.triage_vcf(text))


@app.get("/triage/report", response_class=HTMLResponse, tags=["triage"])
async def triage_report() -> HTMLResponse:
    """The triage dashboard HTML across all bundled variants."""
    return HTMLResponse(content=service.triage_html())


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


@app.get("/ledger/{variant_id}", response_model=LedgerResponse, tags=["audit"])
async def ledger(
    variant_id: str,
    strict: bool = Query(False, description="Exclude circular criteria (PP5/BP6)."),
) -> LedgerResponse:
    """The raw, hash-chained provenance ledger for a variant, with an
    independent re-verification of the chain."""
    return LedgerResponse(**service.ledger_json(variant_id, strict=strict))
