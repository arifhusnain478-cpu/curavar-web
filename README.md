# CuraVar

**An auditable assistant for classifying genetic variants — it does the legwork and shows every step, so a human expert can check the reasoning instead of trusting a black box.**

Built for **Built with Claude: Life Sciences** · Development track

- **Engine:** ACMG/AMP 2015 combining rules + 2018/2020 Bayesian points
- **Interface:** Web (React + FastAPI) · offline and live modes
- **Status:** Working · 24/24 engine tests · 36 API tests · 100% on validation set

---

## The problem

Everyone carries thousands of small differences in their DNA. Most are harmless; a few cause serious disease. When a clinical lab finds one in a patient, a specialist has to decide whether it's harmful or harmless — following an official rulebook (the ACMG/AMP guidelines) that weighs many lines of evidence, and defending that call to a review board. It's slow, high-stakes, and doesn't scale to the flood of variants modern sequencing produces. Worse, a large share of results come back "uncertain," and different labs often disagree because they apply the rules inconsistently.

## What CuraVar does

You give it a variant. CuraVar then:

1. **Gathers the evidence** — population frequency, clinical-database assertions, computational predictors, gene mechanism.
2. **Uses Claude to propose which official rules apply** — each with a citation to the specific evidence that supports it.
3. **Double-checks that reasoning** with a second Claude pass, discarding weak or duplicate claims.
4. **Applies the scoring rules deterministically** to reach a verdict — the AI never touches the final number.
5. **Shows every step in a tamper-proof record** a human can verify.

The core design choice: **Claude proposes, deterministic code decides.** The language model does the hard, fuzzy work (reading messy evidence, applying a complex rubric); a plain, published calculator does the final math. That makes the verdict reproducible and impossible to "drift," while the reasoning stays inspectable at every step.

It is **decision-support**: the final call stays with a qualified professional.

## The five verdicts

`Benign` · `Likely benign` · `Uncertain (VUS)` · `Likely pathogenic` · `Pathogenic`

CuraVar returns "Uncertain" honestly rather than forcing a confident answer when the evidence conflicts.

---

## Key features

- **Every criterion traced to its evidence.** No rule appears without its "receipt" — the raw data it rests on, with source and locator.
- **Shows what it discarded.** Criteria the reviewer removed are shown with the reason, because what was rejected is part of the audit trail.
- **Hash-chained provenance ledger.** Every observation is logged in order and hash-chained, so any later edit is detectable. A "Re-verify chain" button re-walks the record on demand.
- **Two independent scoring methods.** The 2015 combining rules and the 2018/2020 points system run separately; disagreement is surfaced for expert review rather than resolved silently.
- **Strict mode.** Excludes the circular PP5/BP6 criteria so a verdict rests only on primary evidence.
- **PVS1 decision tree.** Follows the ClinGen SVI tree to assign loss-of-function variants their correct strength, avoiding the common false-positive of applying PVS1 at full strength.
- **Offline and live modes.** Runs fully offline on bundled snapshots for a zero-setup demo; live mode pulls from MyVariant.info (gnomAD / ClinVar / dbNSFP) with an API key.

---

## Architecture

### Engine (Python package `curavar`)

| Module | Responsibility |
|---|---|
| `provenance.py` | Append-only, hash-chained evidence ledger with independent verification |
| `acmg.py` | The 28 ACMG/AMP criteria, the 2015 combining rules, the 2018/2020 points system, strict mode |
| `pvs1.py` | The ClinGen SVI PVS1 loss-of-function decision tree |
| `agents.py` | Claude-driven evidence-gathering and the reviewer/adjudicator |
| `sources.py` / `evidence.py` | Evidence providers: bundled offline snapshots and the live MyVariant.info adapter |
| `llm.py` | Claude client with a live mode and an offline record/replay layer |
| `pipeline.py` | End-to-end orchestration of the seven pipeline steps |
| `triage.py` / `report.py` | Batch triage into a prioritized worklist, and the auditable HTML report renderer |
| `io_utils.py` | Centralized UTF-8 file I/O (cross-platform safety) |

### Web application

- **Backend — FastAPI.** A thin API over the engine: classify, per-variant report, triage (+ VCF), ledger, plus cases/config/health. Typed request/response models, auto OpenAPI docs, Anthropic key kept server-side.
- **Frontend — React + Vite + TypeScript.** Three screens (Classify, Triage, Audit) mirroring the engine report's visual language, with input validation for live lookups.
- **Live evidence.** MyVariant.info aggregates gnomAD, ClinVar, and dbNSFP behind one query; the adapter handles genome build, rsID vs genomic HGVS, and multi-record responses.
- **Ops.** Dockerfiles for API and UI, a compose file, and documented local run commands.

---

## Getting started

> Replace the commands below with your actual scripts if they differ.

### Run with Docker (recommended)

```bash
docker compose up --build
```

Then open the frontend URL shown in the terminal. This runs fully offline on bundled cases — no API key needed.

### Run locally

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### Enable live lookups (optional)

Set your Anthropic API key so CuraVar can run live reasoning and look up real variants:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

In the UI, toggle **Live mode** and pick a genome build (GRCh38 / GRCh37).

---

## How it works, end to end

| Step | What happens |
|---|---|
| 1. Gather evidence | Raw observations collected and written to the provenance ledger (offline snapshots or live MyVariant.info). |
| 2. Propose criteria (Claude) | Claude proposes which ACMG/AMP criteria are met — each must cite specific evidence. |
| 3. Adjudicate (Claude) | A reviewer pass prunes weak proposals, removes duplicates, and surfaces conflicts. |
| 4. Refine PVS1 | The ClinGen SVI decision tree assigns PVS1 its correct strength. |
| 5. Score — deterministically | Two independent methods run with **no Claude involvement**. |
| 6. Reconcile | If the methods agree, that's the verdict. If they conflict, CuraVar reports Uncertain and flags it. |
| 7. Report | Verdict, criteria, evidence, discarded proposals, and the verifiable ledger are rendered. |

---

## Validation

- **Engine:** 24/24 tests pass, including ledger tamper-detection, both scoring methods, the PVS1 tree, strict mode, and safe reconciliation.
- **Benchmark:** 100% (18/18) on a truth set spanning all five tiers, at ~70,000 classifications/sec.
- **Web API:** 36 tests pass, covering live not-found / upstream / timeout / parse errors and build validation.

---

## How this differs from existing tools

| Aspect | Typical tools (InterVar, Franklin, VarSome) | CuraVar |
|---|---|---|
| Output | Often a final label | Every criterion traced to its evidence |
| Provenance | Limited | Hash-chained, re-verifiable ledger |
| Circular criteria | Several borrow a database's answer via PP5/BP6 | Strict mode excludes them |
| Method | Single approach | Cross-checks two and flags disagreement |
| Conflict | Often resolved silently | Surfaced for expert review |

CuraVar doesn't try to out-scale established platforms on database size or team features; it competes on **clarity, transparency, and honesty**.

---

## How Claude was used

Claude plays two roles in this project:

- **Inside CuraVar:** Claude is the reasoning engine — it reads the raw evidence, proposes which ACMG/AMP rules apply (each with a citation), and a second Claude pass reviews and removes weak proposals. Claude never does the final scoring; deterministic code does the math, so results are always reproducible.
- **As a building partner:** Claude helped brainstorm the idea, research the problem space, design the architecture, and write and debug the Python + FastAPI + React application.

---

## Roadmap

- Easier setup across operating systems, so any lab can run it with minimal friction.
- Gene-specific ClinGen VCEP rule packs and calibrated predictor thresholds.
- Longer-term: reasoning about how a single mutation propagates from the DNA level up through a whole protein's structure and function — rather than classifying the variant in isolation.

---

## Scope and honesty

This is **research decision-support, not a diagnostic device.** Final interpretation is the responsibility of a qualified professional. No patient-identifiable data is used. Bundled evidence is a labelled recorded snapshot so the demo runs anywhere; live evidence is pulled from MyVariant.info under a key.

`classification math is deterministic and LLM-free · ledger integrity is independently re-verifiable`

---

## License

MIT
