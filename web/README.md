# CuraVar Web — Phase 1 MVP

A web product wrapped around the tested **`curavar`** engine (auditable ACMG/AMP
variant curation). One variant in → evidence gathered → criteria + verdict +
points scorebar + PVS1 decision path + a verifiable provenance ledger out. A VCF
or a set of cases → a prioritized triage worklist.

The classification math stays entirely in `curavar` — it is deterministic and
LLM‑free. This web layer only **runs the engine and displays its results**; it
never re‑implements a rule or a score. The whole product runs **offline in
replay mode with no API key**, so it is demoable anywhere.

> **Research decision‑support, not a diagnostic device.** CuraVar structures and
> surfaces public evidence; a qualified professional makes the final call. No
> patient‑identifiable data is used.

---

## What's here

```
web/
  api/          FastAPI service over the curavar engine (Python)
    main.py       routes
    models.py     Pydantic request/response models (drive the OpenAPI docs)
    service.py    the only bridge to curavar: run engine + serialize results
    .env.example  copy to .env and paste your ANTHROPIC_API_KEY for live mode
    sample.vcf    demo VCF (matches the bundled evidence snapshots)
    tests/        endpoint tests (offline replay + live/error paths) — 28 tests
    Dockerfile
  ui/           React + Vite + TypeScript
    src/
      screens/    Classify · Triage worklist · Audit (ledger) view
      components/  gauge · scorebar · criterion cards · ledger table · …
      theme.css    the report's clinical palette (IBM Plex Sans/Mono, 5 tiers)
    Dockerfile · nginx.conf
docker-compose.yml   (at the repo root — one level up)
```

The three screens map to a lab's workflow:

1. **Classify** — pick a bundled case or type an HGVS; watch evidence get
   gathered; then read the reconciled verdict, the five‑tier gauge, the points
   scorebar, every activated criterion traced to its ledger evidence, the PVS1
   decision path, and the reviewer's discard list. Links out to the full
   server‑rendered HTML report and the audit view.
2. **Triage worklist** — the whole case set, sorted by how much it needs a human
   (**REVIEW → ACT → CLEAR**), with summary cards. Upload a VCF or triage the
   bundled set. Each row drills into that variant's audit and report.
3. **Audit view** — the raw hash‑chained ledger with a **Re‑verify chain**
   button that re‑walks the chain server‑side and reports integrity.

---

## Run it with Docker (both together)

From the **repo root** (the directory that contains both `curavar/` and `web/`):

```bash
docker compose up --build
```

- App (UI): <http://localhost:8080>
- API docs (Swagger / OpenAPI): <http://localhost:8000/docs>

The UI talks to the API same‑origin at `/api/*`; nginx reverse‑proxies that to
the API container, so there is no CORS and no key in the browser.

To enable **live** Claude reasoning + live evidence, export a key first (it is
passed only to the API container):

```bash
ANTHROPIC_API_KEY=sk-... docker compose up --build
```

With no key, everything runs in offline replay mode.

---

## Run it locally (no Docker)

Two terminals, from the **repo root**.

**API** (Python 3.10+):

```bash
pip install -e ./curavar                 # the engine package
pip install -r web/api/requirements.txt  # fastapi, uvicorn, …
uvicorn web.api.main:app --reload --port 8000
```

**UI** (Node 18+):

```bash
cd web/ui
npm install
npm run dev            # http://localhost:5173  (proxies /api -> :8000)
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to the API on
port 8000 (see `web/ui/vite.config.ts`), mirroring what nginx does in Docker.

### Live mode (optional) — your Anthropic key in a `.env` file

The API auto‑loads `web/api/.env` on startup (via python‑dotenv). To enable live
Claude reasoning + live evidence:

1. Open **`web/api/.env`** and paste your key on the `ANTHROPIC_API_KEY=` line:
   `ANTHROPIC_API_KEY=sk-ant-...`
2. Restart the API (`uvicorn …`).

`/config` then reports `live_available: true`, the nav badge flips from
"offline replay" to "live ready", and the **Live mode** checkbox enables. The
key stays server‑side — it is never sent to the browser. `.env` is git‑ignored;
`web/api/.env.example` is the template. With a blank key the app stays in
offline replay mode.

In live mode, a non‑bundled variant is looked up on **MyVariant.info** (evidence
adapter in `web/api/evidence.py`) and reasoned over by Claude.

- **Best input is an rsID** — it resolves regardless of genome build:
  `rs1801133` (MTHFR, → Benign), `rs1799950` (BRCA1, → Benign).
- A **genomic HGVS** works too but must match the selected build:
  `chr17:g.43094464T>C` in **GRCh38** (the default).
- A bare cDNA change like `c.665C>T` has no genomic anchor and won't resolve.

**Genome build.** MyVariant's variant endpoint defaults to hg19/GRCh37; this
adapter targets **GRCh38 (hg38) by default** because the bundled coordinates are
GRCh38. A build selector (GRCh38 / GRCh37) appears in the UI's Live‑mode panel,
and the API accepts an `"assembly": "hg38"|"hg19"` field on `POST /classify`.
Genomic‑HGVS input must be in the selected build; rsIDs are build‑agnostic.

Failure modes are **distinguishable**, never a generic "failed": variant not in
the database (404), upstream/network/timeout (502/504), adapter parse issue
(502), missing/bad key (400/502) — each with a clear message, never a stack
trace.

For Docker, pass the key via the environment instead:
`ANTHROPIC_API_KEY=sk-... docker compose up --build`.

---

## Tests

Endpoint tests hit every route in offline replay mode (no key, no network):

```bash
# from the repo root
python -m pytest web/api/tests -q
```

The engine's own suite still lives with the package:

```bash
cd curavar && python -m pytest -q      # or: python tests/run_tests.py
```

UI type‑check / production build:

```bash
cd web/ui && npm run build
```

---

## API surface

Full interactive docs at `/docs`. Summary:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/classify` | Classify one variant. Body: one of `case_id` / `case_path` / `hgvs` / `variant`, plus `live`, `strict`. Returns the reconciled verdict, both scoring methods, every activated criterion with its traced evidence, the PVS1 decision path, and the full ledger. |
| `GET`  | `/variants/{id}/report` | The engine's self‑contained auditable HTML report (`?strict=true` optional). |
| `POST` | `/triage` | Triage a set of bundled cases into a worklist. Body `{ "case_ids": [...] }`, or empty for all. |
| `POST` | `/triage/vcf` | Triage a VCF upload; records are matched to bundled snapshots, unmatched ones reported. |
| `GET`  | `/triage/report` | The triage dashboard HTML. |
| `GET`  | `/ledger/{id}` | The raw hash‑chained provenance ledger + an independent re‑verification. |
| `GET`  | `/cases` · `/config` · `/health` | Discovery: bundled variants, live‑mode availability, liveness. |

### Scope notes (honest boundaries)

- **Offline replay** classifies the four **bundled** variants (by `case_id` or by
  typing their HGVS). Classifying an *arbitrary* variant needs `live=true` and an
  API key — the live path uses `curavar`'s MyVariant.info adapter and live Claude
  reasoning. Requests it can't satisfy offline return a clear `422`, not a guess.
- `case_path` is confined to the engine's bundled data directory — the API does
  not read arbitrary server paths.
- VCF triage matches records to bundled evidence snapshots (by ID column or
  `CHROM:POS`); unmatched records are listed, never silently dropped.

---

## Design guarantees carried through from the engine

- **The model proposes; deterministic rules decide.** The UI shows scores and
  tiers; it never computes them.
- **No claim without a receipt.** Every criterion card lists the ledger entries
  that justify it.
- **Tamper‑evident.** The ledger is hash‑chained; the audit view re‑verifies it.
- **Honest about conflict.** When the two methods diverge, the verdict is
  reported as Uncertain and visibly flagged for expert review.
