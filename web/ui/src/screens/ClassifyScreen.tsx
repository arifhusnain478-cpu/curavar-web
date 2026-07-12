import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, reportUrl, type ClassifyRequest } from "../api";
import type { CaseSummary, ClassifyResult, Config } from "../types";
import { VerdictCard } from "../components/VerdictCard";
import { CriterionCard } from "../components/CriterionCard";
import { Pvs1Path } from "../components/Pvs1Path";
import { RemovedPanel } from "../components/RemovedPanel";
import { LedgerTable } from "../components/LedgerTable";
import { ClassifySkeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";
import {
  LIVE_EXAMPLES,
  isBundledPrefix,
  isGenomicHgvs,
  routeClassifyInput,
} from "../liveInput";

export function ClassifyScreen({ config }: { config: Config | null }) {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [caseId, setCaseId] = useState("");
  const [hgvs, setHgvs] = useState("");
  const [strict, setStrict] = useState(false);
  const [assembly, setAssembly] = useState("hg38");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ClassifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastWasGenomic, setLastWasGenomic] = useState(false);
  const didAutoRun = useRef(false);

  const liveAvailable = !!config?.live_available;

  async function run(req: ClassifyRequest) {
    setLoading(true);
    setError(null);
    setLastWasGenomic(!!req.hgvs && isGenomicHgvs(req.hgvs));
    try {
      setResult(await api.classify(req));
    } catch (e: any) {
      setError(String(e?.message ?? e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  // Load the bundled cases, preselect the first, and classify it immediately so
  // the screen opens on a real result — a smooth entry point for a demo.
  useEffect(() => {
    api
      .cases()
      .then((cs) => {
        setCases(cs);
        if (cs.length && !didAutoRun.current) {
          didAutoRun.current = true;
          setCaseId(cs[0].id);
          run({ case_id: cs[0].id, strict: false });
        }
      })
      .catch((e) => setError(String(e?.message ?? e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function pickCase(id: string) {
    setCaseId(id);
    setHgvs("");
    run({ case_id: id, strict });
  }

  // What will happen with what's typed — decided here exactly as the server
  // decides it, so we can guide input and preempt a request we know will fail.
  const q = hgvs.trim();
  const route = q ? routeClassifyInput(q, cases, liveAvailable) : null;
  const runnable = route?.action === "offline" || route?.action === "live";
  // Show a calm inline note only once the input has clearly diverged from every
  // bundled variant (not while someone is mid-typing one).
  const hint =
    route && !runnable && !isBundledPrefix(q, cases) ? route.message ?? null : null;

  // A typed variant is submittable when the server can classify it (offline or
  // live); with an empty box, the selected bundled case is the fallback.
  const canSubmit = q ? runnable : !!caseId;

  function classifyCurrent() {
    if (!q) {
      if (caseId) run({ case_id: caseId, strict, assembly });
      return;
    }
    // Not classifiable (bare cDNA / unavailable): the inline hint already says
    // why; never fire a doomed request.
    if (!runnable) return;
    run({ hgvs: q, strict, assembly });
  }

  // One-click, known-good live variant: fill the box and run (live is available
  // whenever these chips are shown).
  function runExample(value: string) {
    setHgvs(value);
    run({ hgvs: value, strict, assembly });
  }

  function toggleStrict(next: boolean) {
    setStrict(next);
    if (result) {
      run(q ? { hgvs: q, strict: next, assembly } : { case_id: caseId, strict: next, assembly });
    }
  }

  return (
    <div className="wrap">
      <div className="eyebrow">Variant classification</div>
      <h1>Classify a variant</h1>
      <div className="sub">
        Evidence is gathered, criteria are proposed and reviewed, then the
        published ACMG/AMP rules decide — deterministically. Pick a case to see it
        run.
      </div>

      <div className="panel-card">
        <div className="field" style={{ marginBottom: 4 }}>
          <label>Example variants — click to classify</label>
        </div>
        <div className="chips">
          {cases.map((c) => (
            <button
              key={c.id}
              className={`chip ${caseId === c.id && !hgvs.trim() ? "active" : ""}`}
              onClick={() => pickCase(c.id)}
              disabled={loading}
            >
              <span className="chip-gene">
                {c.gene} {c.hgvs_c}
              </span>
              <span className="chip-sub">{c.hgvs_p}</span>
              {c.synthetic && <span className="chip-syn">synthetic teaching case</span>}
            </button>
          ))}
          {cases.length === 0 && !error && <SkelChips />}
        </div>

        <div className="form-row" style={{ marginTop: 18 }}>
          <div className="field">
            <label htmlFor="hgvs">
              {liveAvailable
                ? "Or look up a variant — rsID, genomic HGVS, or any example above"
                : "Or type an example variant"}
            </label>
            <input
              id="hgvs"
              type="text"
              placeholder={
                liveAvailable
                  ? "e.g. c.665C>T  ·  rs1801133  ·  chr17:g.43094464T>C"
                  : "e.g. c.665C>T (matches an example above)"
              }
              value={hgvs}
              onChange={(e) => setHgvs(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && classifyCurrent()}
              aria-invalid={!!hint}
            />
          </div>
          <button
            className="btn btn-lg"
            onClick={classifyCurrent}
            disabled={loading || !canSubmit}
          >
            {loading ? "Gathering evidence…" : "Classify"}
          </button>
        </div>

        {hint && (
          <div className="notice" role="status">
            {hint}
          </div>
        )}

        {liveAvailable && (
          <div className="examples">
            <span className="examples-lbl">Or try a live lookup:</span>
            {LIVE_EXAMPLES.map((ex) => (
              <button
                key={ex.value}
                className="exchip"
                onClick={() => runExample(ex.value)}
                disabled={loading}
                title={`${ex.gene} · ${ex.note}`}
              >
                {ex.value}
              </button>
            ))}
          </div>
        )}

        <div className="toggles">
          <label className="toggle">
            <input
              type="checkbox"
              checked={strict}
              onChange={(e) => toggleStrict(e.target.checked)}
            />
            Strict mode — exclude circular criteria (PP5/BP6)
          </label>
        </div>

        {liveAvailable && (
          <details className="advanced">
            <summary>Advanced</summary>
            <div className="advbody">
              <label className="advfield">
                Genome build
                <select value={assembly} onChange={(e) => setAssembly(e.target.value)}>
                  <option value="hg38">GRCh38 / hg38</option>
                  <option value="hg19">GRCh37 / hg19</option>
                </select>
              </label>
              <span className="advnote">
                Only used for live lookups of variants outside the bundled set. An{" "}
                <b>rsID</b> resolves regardless of build; a <b>genomic HGVS</b> must
                match the selected build.
              </span>
            </div>
          </details>
        )}
      </div>

      {loading && (
        <>
          <div className="loading">
            <span className="spinner" />
            Gathering evidence…
          </div>
          <ClassifySkeleton />
        </>
      )}

      {error && !loading && (
        <div className="error">
          <strong>Couldn't classify.</strong> {error}
          {lastWasGenomic && (
            <div style={{ marginTop: 8 }}>
              Tip: this genomic HGVS was looked up in{" "}
              <b>{assembly === "hg38" ? "GRCh38" : "GRCh37"}</b>. If it's the wrong
              build, switch the genome build under <b>Advanced</b> and retry — or use
              the variant's <b>rsID</b>, which resolves regardless of build.
            </div>
          )}
          {canSubmit && (
            <div style={{ marginTop: 10 }}>
              <button className="btn ghost" onClick={classifyCurrent}>
                Try again
              </button>
            </div>
          )}
        </div>
      )}

      {result && !loading && (
        <>
          <section className="vstrip">
            <div className="eyebrow" style={{ fontSize: 12 }}>
              Result
              <span className="pill">
                {result.mode === "live" ? "live evidence" : "bundled evidence"}
              </span>
              {result.strict && <span className="pill">strict</span>}
            </div>
            <div className="vg">
              {result.variant.gene} {result.variant.hgvs_c}
            </div>
            <div className="sub" style={{ marginTop: 2, marginBottom: 0 }}>
              {result.variant.hgvs_p} · {result.variant.genome_build} ·{" "}
              {result.variant.coordinate}
            </div>
          </section>

          <div className="sec">
            <span className="num">1</span>
            <h2>The call</h2>
          </div>
          <p className="hint">
            The verdict, reconciled from two independent scoring methods. When they
            disagree, it's reported as Uncertain and flagged — not smoothed over.
          </p>
          <VerdictCard result={result} />

          <div className="sec">
            <span className="num">2</span>
            <h2>The evidence behind the call</h2>
          </div>
          <p className="hint">
            Each ACMG/AMP criterion the evidence met, with the raw data it rests
            on. No criterion appears without its receipt.
          </p>
          {result.activated_criteria.length ? (
            result.activated_criteria.map((c) => <CriterionCard key={c.code} crit={c} />)
          ) : (
            <EmptyState icon="○" title="No criteria met the evidentiary bar">
              The evidence didn't support any ACMG/AMP criterion strongly enough —
              an honest “insufficient evidence” outcome, not a forced call.
            </EmptyState>
          )}

          {result.pvs1 && (
            <>
              <div className="sec">
                <span className="num">3</span>
                <h2>Loss-of-function analysis</h2>
              </div>
              <p className="hint">
                The PVS1 criterion is the most over-applied one. Here's the exact
                decision path that set its strength.
              </p>
              <Pvs1Path pvs1={result.pvs1} />
            </>
          )}

          {result.removed_criteria.length > 0 && (
            <>
              <div className="sec">
                <span className="num">{result.pvs1 ? 4 : 3}</span>
                <h2>What the reviewer discarded</h2>
              </div>
              <p className="hint">
                Proposals dropped for weak support — shown, because what was
                rejected is part of the audit trail.
              </p>
              <RemovedPanel removed={result.removed_criteria} />
            </>
          )}

          <div className="sec">
            <span className="num">
              {(result.pvs1 ? 1 : 0) + (result.removed_criteria.length ? 1 : 0) + 3}
            </span>
            <h2>Proof it holds up</h2>
          </div>
          <p className="hint">
            Every raw observation used, in order, hash-chained so any later edit is
            detectable.
          </p>
          <LedgerTable
            entries={result.ledger.entries}
            verified={result.ledger_verified}
            problems={result.ledger_problems}
          />
          <div className="btnrow">
            <a
              className="btn ghost"
              href={reportUrl(result.id, result.strict)}
              target="_blank"
              rel="noreferrer"
            >
              Open full report ↗
            </a>
            <Link className="btn ghost" to={`/audit/${result.id}`}>
              Open audit view →
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

function SkelChips() {
  return (
    <>
      {Array.from({ length: 4 }).map((_, i) => (
        <span key={i} className="skel" style={{ width: 130, height: 46, borderRadius: 8 }} />
      ))}
    </>
  );
}
