# CuraVar Web — Architecture & Build Plan

How to turn the CuraVar engine into a web product a real lab would use. The
design mirrors the proven pattern of ClinGen's Variant Curation Interface (VCI),
the FDA-recognized reference platform, and layers CuraVar's differentiators on
top: Claude-driven evidence gathering, dual-method cross-check, the PVS1 decision
tree, the tamper-proof provenance ledger, and batch triage.

---

## What "a lab would actually use" requires

From how the ClinGen VCI and commercial tools (Franklin, VarSome) work, a real
platform needs:

1. **Accounts, roles, and teams** — curators, reviewers, admins; group curation
   with peer review ("affiliations" in VCI terms).
2. **A controlled workflow** — search a variant → auto-gather evidence → review
   criteria → sign-off → archive. Enforced order prevents sloppy calls.
3. **A living evidence panel** — population frequency, ClinVar, predictors,
   literature, pulled from external sources and editable by the curator.
4. **Full provenance on every assertion** — who asserted what, on what evidence,
   when. (CuraVar's hash-chained ledger already does this.)
5. **Export / submission** — an auditable report and, ideally, ClinVar-format
   submission.
6. **Scale** — batch import (VCF) and a triage worklist. (CuraVar has this.)
7. **Security/compliance** — depends on data scope (see below).

The good news: CuraVar's Python core (`acmg`, `pvs1`, `agents`, `pipeline`,
`provenance`, `triage`) is the hard, domain-heavy part, and it's done and tested.
The web product wraps it — it does not rewrite it.

---

## Recommended architecture

```
              ┌────────────────────────── Browser (React) ──────────────────────────┐
              │  variant search · evidence panel · criteria board · verdict+scorebar │
              │  PVS1 decision path · audit/ledger view · triage worklist · sign-off │
              └───────────────▲───────────────────────────────────────▲─────────────┘
                              │ HTTPS / JSON                           │
              ┌───────────────┴──────────── API (FastAPI, Python) ─────┴─────────────┐
              │  /classify  /variants/{id}  /variants/{id}/report  /triage  /ledger  │
              │  auth (OIDC) · roles · workflow state machine · rate limiting        │
              └───────┬───────────────────────┬───────────────────────┬─────────────┘
                      │                        │                       │
        ┌─────────────▼───────┐   ┌────────────▼──────────┐  ┌─────────▼──────────────┐
        │ CuraVar engine      │   │ Evidence manager      │  │ Async workers          │
        │ (existing package)  │   │ MyVariant.info,       │  │ live evidence + Claude │
        │ classify/PVS1/points│   │ gnomAD, ClinVar, +cache│  │ calls (queued)         │
        └─────────────┬───────┘   └───────────────────────┘  └────────────────────────┘
                      │
        ┌─────────────▼───────────────────────────────────────────────────────────────┐
        │ Postgres: users, variants, classifications, ledgers, evidence, audit log     │
        │ Object storage (S3): generated reports                                        │
        └───────────────────────────────────────────────────────────────────────────────┘
```

**Why this stack**
- **Python/FastAPI backend**: keeps the whole engine in one language, so the
  classification logic on the web is *the same code* that's already validated —
  no reimplementation, no drift. FastAPI gives typed request/response models and
  auto OpenAPI docs.
- **React frontend**: same choice ClinGen VCI made; rich enough for the criteria
  board and evidence panel.
- **Postgres + JSON columns**: the VCI stores its classification model as JSON;
  Postgres JSONB gives that flexibility plus real relational queries for
  worklists and audit.
- **Async workers**: live evidence pulls and Claude calls take seconds, so they
  run off the request thread (a queue like RQ/Celery, or just background tasks
  for the MVP).
- **Server-side Claude keys**: the Anthropic API key never touches the browser.
  The existing `llm.py` record/replay layer becomes the test harness.

---

## Data & compliance scope — decide this first

The architecture is the same; the compliance burden depends entirely on the data:

- **Research / public-variant tool (recommended MVP scope).** Only public
  variants (HGVS/rsID) and public evidence — no patient identifiers. Light
  compliance. This is a genuinely useful product (it's what curators use to
  prioritize) and it's the honest scope for a hackathon build.
- **Clinical / patient-linked (later).** If variants are tied to patients, this
  becomes PHI: HIPAA applies — a BAA with the cloud provider, encryption in
  transit and at rest, strict RBAC, and a complete audit trail (CuraVar's ledger
  is a head start). Framed as **decision-support, not a diagnostic device**, so a
  qualified professional signs every call; a true diagnostic device would add
  regulatory scope (CLIA/LDT considerations).

Start in research scope; design the schema so patient-linking can be added
behind an auth wall later without rework.

---

## Build in three phases

**Phase 1 — Web MVP (research scope).** FastAPI wrapping the engine + a React (or
even server-rendered) UI. One variant in → evidence gathered → criteria + verdict
+ scorebar + PVS1 path + verifiable ledger out. VCF upload → triage worklist.
Offline replay mode for the demo; live mode with an API key. *This is the
demoable, submittable web product.*

**Phase 2 — Multi-user & collaboration.** Accounts and roles, saved variants,
editable evidence panel, two-reviewer sign-off, affiliations, evidence caching.

**Phase 3 — Clinical hardening.** HIPAA controls, patient linking behind auth,
gene-specific ClinGen VCEP rule packs, calibrated predictor thresholds
(Pejaver et al.), and ClinVar-format submission.

---

## What makes CuraVar Web better than what exists

Mapping the engine's differentiators onto the web product:

- **Claude gathers and explains the evidence** — most tools apply static rules;
  CuraVar reads messy evidence and shows its reasoning.
- **Dual-method cross-check** — surfaces exactly the hard variants where the 2015
  rules and the points system disagree, and flags them for a human.
- **PVS1 decision tree** — avoids the classic full-strength-PVS1 false positives.
- **Tamper-proof ledger** — the provenance/audit requirement, already built.
- **Triage worklist** — points scarce expert time at the cases that need it.

The web layer is packaging and workflow; the intelligence and rigor are the core
that's already done.
