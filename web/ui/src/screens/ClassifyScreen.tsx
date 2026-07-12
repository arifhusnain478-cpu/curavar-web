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
  isGenomicHgvs,
  validateLiveInput,
} from "../liveInput";

export function ClassifyScreen({ config }: { config: Config | null }) {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [caseId, setCaseId] = useState("");
  const [hgvs, setHgvs] = useState("");
  const [strict, setStrict] = useState(false);
  const [live, setLive] = useState(false);
  const [assembly, setAssembly] = useState("hg38");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ClassifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inputNudge, setInputNudge] = useState<string | null>(null);
  const [lastWasGenomic, setLastWasGenomic] = useState(false);
  const didAutoRun = useRef(false);

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
          run({ case_id: cs[0].id, strict: false, live: false });
        }
      })
      .catch((e) => setError(String(e?.message ?? e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function pickCase(id: string) {
    setCaseId(id);
    setHgvs("");
    setInputNudge(null);
    run({ case_id: id, strict, live, assembly });
  }

  function classifyCurrent() {
    const q = hgvs.trim();
    // In live mode the text box IS the live-lookup identifier — validate it and
    // block obviously-unresolvable input before spending a MyVariant.info call.
    if (live) {
      const check = validateLiveInput(q);
      if (!check.ok) {
        setInputNudge(check.message ?? "Enter a valid variant identifier.");
        return; // no API call
      }
      setInputNudge(null);
      run({ hgvs: q, strict, live, assembly });
      return;
    }
    // Offline: the box matches a bundled variant (or the API returns a clear
    // "no bundled match" message); a selected case is the fallback.
    setInputNudge(null);
    if (q) run({ hgvs: q, strict, live, assembly });
    else if (caseId) run({ case_id: caseId, strict, live, assembly });
  }

  // One-click, known-good live variant: fill the box, ensure live is on, run.
  function runExample(value: string) {
    setHgvs(value);
    setInputNudge(null);
    setLive(true);
    run({ hgvs: value, strict, live: true, assembly });
  }

  function toggleStrict(next: boolean) {
    setStrict(next);
    if (result) {
      const q = hgvs.trim();
      run(
        q
          ? { hgvs: q, strict: next, live, assembly }
          : { case_id: caseId, strict: next, live, assembly }
      );
    }
  }

  const canRun = !!(hgvs.trim() || caseId);

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
          <label>Bundled cases — click to classify</label>
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
              {live ? "Look up a variant (rsID or genomic HGVS)" : "Or type an HGVS / rsID"}
            </label>
            <input
              id="hgvs"
              type="text"
              placeholder={
                live
                  ? "e.g. rs1799950  ·  chr17:g.43094464T>C"
                  : "e.g. c.665C>T (matches a bundled case)"
              }
              value={hgvs}
              onChange={(e) => {
                setHgvs(e.target.value);
                if (inputNudge) setInputNudge(null);
              }}
              onKeyDown={(e) => e.key === "Enter" && classifyCurrent()}
              aria-invalid={!!inputNudge}
            />
          </div>
          <button
            className="btn btn-lg"
            onClick={classifyCurrent}
            disabled={loading || (!live && !canRun)}
          >
            {loading ? "Gathering evidence…" : live ? "Look up live" : "Classify"}
          </button>
        </div>

        {inputNudge && (
          <div className="inputnudge" role="alert">
            {inputNudge}
          </div>
        )}

        {live && config?.live_available && (
          <div className="examples">
            <span className="examples-lbl">Known-good live examples:</span>
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
          <label
            className={`toggle ${config?.live_available ? "" : "disabled"}`}
            title={
              config?.live_available
                ? "Use live Claude reasoning + live evidence"
                : "Add ANTHROPIC_API_KEY to web/api/.env to enable live mode"
            }
          >
            <input
              type="checkbox"
              checked={live}
              disabled={!config?.live_available}
              onChange={(e) => setLive(e.target.checked)}
            />
            Live mode {config?.live_available ? "" : "(needs API key)"}
          </label>
        </div>

        {live && (
          <div className="livehint">
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <b>Live mode.</b>
              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                Genome build
                <select
                  value={assembly}
                  onChange={(e) => setAssembly(e.target.value)}
                  style={{ padding: "5px 8px" }}
                >
                  <option value="hg38">GRCh38 / hg38</option>
                  <option value="hg19">GRCh37 / hg19</option>
                </select>
              </label>
            </div>
            <div style={{ marginTop: 8 }}>
              A non-bundled variant is looked up on MyVariant.info in the selected
              build. Best input is an <b>rsID</b> (e.g. <code>rs1801133</code>,{" "}
              <code>rs1799950</code>) — it resolves regardless of build. A{" "}
              <b>genomic HGVS</b> works too (e.g. <code>chr17:g.43094464T&gt;C</code>)
              but must match the selected build. A bare cDNA change like{" "}
              <code>c.665C&gt;T</code> can't be resolved upstream.
            </div>
          </div>
        )}
      </div>

      {loading && (
        <>
          <div className="loading">
            <span className="spinner" />
            Collecting evidence → proposing criteria → adjudicating → applying the
            combining rules…
          </div>
          <ClassifySkeleton />
        </>
      )}

      {error && !loading && (
        <div className="error">
          <strong>Couldn't classify.</strong> {error}
          {live && lastWasGenomic && (
            <div style={{ marginTop: 8 }}>
              Tip: this genomic HGVS was looked up in{" "}
              <b>{assembly === "hg38" ? "GRCh38" : "GRCh37"}</b>. If it's the wrong
              build, switch the genome-build selector above and retry — or use the
              variant's <b>rsID</b>, which resolves regardless of build.
            </div>
          )}
          {canRun && (
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
              <span className="pill">{result.mode === "live" ? "live" : "offline replay"}</span>
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
