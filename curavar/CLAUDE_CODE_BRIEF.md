# Claude Code handoff brief — build CuraVar Web (Phase 1 MVP)

Paste everything below into Claude Code, in a directory that contains the
existing `curavar/` package (unzip `curavar.zip` there first).

---

You are building a web application on top of an existing, tested Python package
called `curavar` (in this repo). Do not rewrite the classification logic — the
`curavar` package is the engine and it is validated. You are wrapping it in a
web API and a browser UI. Read the package's `README.md` and `WEB_ARCHITECTURE.md`
first; they define the domain and the target design.

## Scope for this pass (Phase 1 MVP, research scope only)
Public variants and public evidence only. No patient-identifiable data, no auth
yet. Get a working, demoable web product end to end.

## Backend — FastAPI (Python)
Create `web/api/` with a FastAPI app exposing:
- `POST /classify` — body: `{ "case_path" | "variant" | "hgvs" }`. Runs
  `curavar.pipeline.CuraVarPipeline`. In replay mode it uses bundled cassettes;
  if `ANTHROPIC_API_KEY` is set and `live=true`, it runs live. Returns the
  `CuraVarResult.summary()` plus the activated criteria, points breakdown, PVS1
  decision path, and the full ledger.
- `GET  /variants/{id}/report` — returns the rendered HTML report
  (`curavar.report.render_report`).
- `POST /triage` — accepts a set of cases (or a VCF upload) and returns the
  triage worklist (`curavar.triage.triage_cases`) as JSON.
- `GET  /triage/report` — returns the triage dashboard HTML
  (`curavar.triage_report.render_triage`).
- `GET  /ledger/{id}` — returns the provenance ledger JSON.
Rules: keep the Anthropic key server-side only. Reuse `curavar.io_utils` for any
file I/O (UTF-8 everywhere). Add Pydantic request/response models and let FastAPI
generate OpenAPI docs. Add pytest tests that hit each endpoint in replay mode.

## Frontend — React + Vite + TypeScript
Create `web/ui/`. Screens:
1. **Variant search / classify** — input an HGVS or pick a bundled case; show a
   loading state while evidence is gathered; then render the verdict, the
   five-tier gauge, the points scorebar, each criterion traced to its evidence,
   the PVS1 decision path, and a "verify ledger" panel.
2. **Triage worklist** — table sorted by review priority (REVIEW / ACT / CLEAR)
   with summary cards; each row links to that variant's full report.
3. **Audit view** — render the ledger with the hash chain and a re-verify button.
Match the existing report's visual language: IBM Plex Sans + IBM Plex Mono, the
clinical palette, the five-tier color coding. Do not invent a new look.

## Non-negotiables
- The classification math stays in `curavar` (deterministic, LLM-free). The UI
  only displays results.
- Show provenance everywhere — no claim without its evidence.
- Keep the "research decision-support, not diagnosis" disclaimer visible.
- Offline replay must work with no API key so the app is demoable anywhere.

## Deliverables
- `web/api/` (FastAPI) and `web/ui/` (React) that run together
  (`uvicorn` + `vite dev`), a `docker-compose.yml` to start both, a short
  `web/README.md` with run instructions, and passing endpoint tests.

Build it end to end, make your own implementation calls, and keep the existing
engine untouched.
