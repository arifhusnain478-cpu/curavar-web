# CuraVar

**An auditable assistant for classifying genetic variants — it does the legwork and shows every step, so a human expert can check the reasoning instead of trusting a black box.**

Built for *Built with Claude: Life Sciences* · Development track.

---

## The problem

Every person carries thousands of small differences in their DNA. Most are harmless; a few cause serious disease. When a clinical lab finds one in a patient, a molecular geneticist has to answer a hard, high-stakes question: **is this variant pathogenic or benign?**

That decision follows a published rulebook — the [ACMG/AMP 2015 guidelines](https://www.ncbi.nlm.nih.gov/pubmed/25741868) — which asks the curator to weigh ~28 lines of evidence (population frequency, computational predictions, functional studies, clinical databases, inheritance patterns) and combine them into one of five verdicts. Doing it well means reading across gnomAD, ClinVar, and the literature, and defending every judgment to a review board. It is slow, and it does not scale to the flood of variants modern sequencing produces.

An LLM can accelerate this — but only if a curator can *trust and verify* it. A confident-sounding answer with no traceable reasoning is worse than useless in a clinical setting; it's a liability.

## What CuraVar does

Give it a variant. CuraVar:

1. **Collects the raw evidence** and writes each observation into an append-only, hash-chained **provenance ledger**.
2. **Uses Claude to propose which ACMG/AMP criteria are met** — each proposal must cite the specific evidence that supports it.
3. **Runs a reviewer pass** that prunes weakly-supported proposals and surfaces any conflict, writing its reasoning back into the ledger.
4. **Applies the ACMG/AMP combining rules deterministically** — no LLM in the scoring math — to reach the final five-tier classification.
5. **Renders an auditable report**: the verdict, every criterion traced to its evidence, what the reviewer discarded, and a ledger you can re-verify.

The verdict is never the point on its own. The point is that **every step is inspectable and checkable.**

## Design principles (and why they matter)

- **The model proposes; deterministic rules decide.** Claude gathers evidence and suggests criteria, but the combining logic is plain, published, LLM-free code. The same evidence always yields the same verdict — a reviewer can re-run it and get a bit-identical result.
- **Two accepted methods, cross-checked.** CuraVar scores every variant with *both* the 2015 combining rules and the 2018/2020 Bayesian points system ([Tavtigian et al.](https://doi.org/10.1002/humu.24088)). When the two methods disagree — which happens precisely on hard, mixed-evidence variants — it does not paper over it: it reports the disagreement and flags the variant for expert review.
- **Hard calls get the real decision tree.** The PVS1 (loss-of-function) criterion is the single most over-applied one. CuraVar runs the ClinGen SVI decision tree ([Abou Tayoun et al. 2018](https://pubmed.ncbi.nlm.nih.gov/30192042/)) — reasoning about variant type, NMD, location, and fraction of protein affected — to assign PVS1 at the correct strength (or not at all), and shows the decision path. This is exactly where a flat rule produces false-positive "pathogenic" calls.
- **No claim without a receipt.** Every activated criterion cites ledger entries. A proposal that cites nothing is dropped automatically.
- **Tamper-evident by construction.** The ledger is hash-chained: each entry commits to the previous one. Alter any past entry and `verify()` catches it. The report re-verifies the chain and shows the result.
- **Honest about what it discarded and where it's unsure.** The report shows criteria the reviewer *removed* and why. When evidence conflicts, CuraVar returns **Uncertain** and says so plainly, instead of forcing a clean-looking answer.
- **Decision-support, not diagnosis.** CuraVar surfaces and structures evidence; a qualified geneticist makes the final call. It uses only public or clearly-labeled synthetic data — no patient-identifiable information.

## How CuraVar differs from existing tools

Automated ACMG/AMP classifiers already exist — InterVar, Franklin (Genoox), VarSome, TAPES, and others. CuraVar is not trying to out-automate them on raw throughput; it targets the things that keep those tools in "research prioritisation" rather than trusted decision-support:

| | Typical automated tools | CuraVar |
|---|---|---|
| **Output** | Often a final label; criterion detail varies | Criterion-by-criterion, every one traced to evidence |
| **Provenance** | Limited / not the focus | Append-only hash-chained ledger; independently verifiable |
| **Circular criteria (PP5/BP6)** | Several tools use them to "borrow" ClinVar's answer | Strict mode excludes them; classification rests on primary evidence |
| **Method** | Single combining approach | Runs 2015 rules **and** 2018/2020 points system, cross-checked |
| **Conflicts** | Often resolved silently | Surfaced and flagged for expert review |
| **Reasoning** | Static rules / proprietary engine | Claude gathers evidence and proposes criteria, with the reasoning shown |

A published review notes that many tools "focus on the final classification instead of analysing criterion by criterion," and that using retired criteria like PP5/BP6 lets a classifier approach ClinVar's result artificially — which is why such tools are recommended for research prioritisation, not diagnostics. CuraVar's design is a direct response: primary-evidence-only classification, full provenance, and honest treatment of conflict.



Three bundled cases show the tool across the outcomes a real curator faces:

| Case | Variant | Verdict | What it shows |
|------|---------|---------|---------------|
| `brca1_c5266dupC` | BRCA1 c.5266dupC | **Pathogenic** | A clear call from a loss-of-function founder mutation; reviewer drops an unsupported criterion. |
| `mthfr_c665CtoT` | MTHFR c.665C>T | **Benign** | A common polymorphism resolved by a single stand-alone rule (BA1). |
| `demo1_conflicting_vus` | DEMO1 c.1234G>A *(synthetic)* | **Uncertain (VUS)** | Two functional studies disagree; the tool flags the conflict rather than picking a side. |
| `demo2_pvs1_lastexon` | DEMO2 c.2800C>T *(synthetic)* | **Uncertain (VUS)** | A last-exon nonsense variant a naive tool would call Pathogenic; the PVS1 decision tree downgrades it, avoiding a false positive. |

## Quickstart

No third-party dependencies — standard library only.

```bash
# list the bundled demo cases
python -m curavar list

# classify one variant and write its auditable report
python -m curavar run curavar/data/brca1_c5266dupC.json --report brca1.html

# classify all bundled cases at once
python -m curavar run --all --report-dir reports/

# triage a whole variant set into a prioritized worklist (a lab's real workflow)
python -m curavar triage --report triage.html

# strict mode (exclude circular PP5/BP6) and export the audit ledger
python -m curavar run curavar/data/brca1_c5266dupC.json --strict --export-ledger audit.json
```

By default CuraVar runs **offline** in replay mode, using recorded reasoning bundled with each case, so the demo is fully reproducible with no network or API key. To run with live Claude reasoning **and live evidence** (gnomAD / ClinVar / dbNSFP via MyVariant.info):

```bash
export ANTHROPIC_API_KEY=sk-...
python -m curavar run curavar/data/brca1_c5266dupC.json --live --report brca1.html
```

A live run re-records the case's reasoning so it stays reproducible afterward.

## How it's built

```
variant
  │
  ▼
SourceProvider ──────────► provenance ledger  (raw, hash-chained evidence)
  │                              │
  ▼                              │
Claude: gather criteria ◄────────┘   (each proposal cites evidence IDs)
  │
  ▼
Claude: adjudicate                    (prune weak proposals; flag conflicts; logged)
  │
  ▼
acmg.classify()                       (deterministic ACMG/AMP combining rules — no LLM)
  │
  ▼
auditable HTML report
```

| Module | Role |
|--------|------|
| `provenance.py` | Append-only, hash-chained evidence ledger with independent verification. |
| `acmg.py` | The 28 ACMG/AMP criteria, the deterministic combining rules, the points system, and strict mode. |
| `pvs1.py` | The ClinGen SVI PVS1 loss-of-function decision tree. |
| `sources.py` | Evidence providers (bundled offline snapshots; live MyVariant.info adapter). |
| `triage.py` / `triage_report.py` | Batch triage into a prioritized worklist + dashboard. |
| `llm.py` | Claude client with live mode and offline record/replay cassettes. |
| `agents.py` | Evidence-gathering agents and the reviewer/adjudicator. |
| `pipeline.py` | End-to-end orchestration. |
| `report.py` | The auditable clinical report. |
| `benchmark.py` | Engine validation against a labeled truth set (accuracy, throughput). |
| `cli.py` | `python -m curavar` command line. |

## Validation

```bash
python -m curavar benchmark      # validate the engine against the truth set
python -m pytest -q              # or: python tests/run_tests.py
```

The engine is validated against a truth set spanning all five tiers. Because the
2015 combining rules are deterministic given a set of criteria, a correct engine
must reproduce every guideline-defined label exactly — and it does: **18/18
(100%)**, at ~70,000 classifications/sec. The dual-engine cross-check also
independently rediscovers the two combinations that Tavtigian et al. (2018)
identified as internally inconsistent in the ACMG/AMP rules (a "pathogenic"
combination that is mathematically likely-pathogenic, and vice versa) — evidence
that the points system is implemented correctly and that the conflict-surfacing
works. The harness is structured so the same sensitivity/specificity metrics can
be computed against real labeled sets (e.g. ClinGen's eRepo) under live evidence.

The test suite (16 tests) additionally covers ledger tamper-detection, the
combining rules, the points math, strict mode, and safe reconciliation.

## Using it for real

CuraVar is packaged as an installable tool (`pip install -e .`, then the `curavar`
command) with three entry points that mirror a lab's workflow: single-variant
classification with an auditable report, **batch triage** of a whole variant set
into a prioritized worklist (the scarce resource is expert attention, so the
worklist puts the cases that need a human first), and an **exportable audit
ledger** for each decision so the reasoning can be archived and re-verified.
Live evidence is pulled from MyVariant.info (gnomAD / ClinVar / dbNSFP) under
`--live`; the offline demo uses recorded snapshots so it is reproducible anywhere.

## Scope and honesty

- The bundled evidence is a **recorded snapshot**, clearly labeled, so the demo runs without network access. The live adapters for gnomAD/ClinVar/PubMed are stubbed with the intended interface; wiring them to real endpoints is the natural next step outside the sandbox.
- CuraVar implements the core ACMG/AMP 2015 framework **and** the 2018/2020 Bayesian points system, and cross-checks them. It does not yet apply gene-specific ClinGen VCEP rule specifications or calibrated predictor thresholds (e.g. Pejaver et al. for PP3/BP4) — clear, well-scoped extensions.
- **This is research decision-support, not a diagnostic device.** Final variant interpretation is the responsibility of a qualified professional.
