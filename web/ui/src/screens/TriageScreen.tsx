import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, reportUrl, triageReportUrl } from "../api";
import type { TriageResult } from "../types";
import { TIER_VAR } from "../types";
import { TableSkeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";

const BUCKET_CLS: Record<string, string> = {
  ACT: "act",
  REVIEW: "review",
  CLEAR: "clear",
};

export function TriageScreen() {
  const nav = useNavigate();
  const [data, setData] = useState<TriageResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState<string>("bundled cases");

  function load(promise: Promise<TriageResult>, label: string) {
    setLoading(true);
    setError(null);
    setSource(label);
    promise
      .then(setData)
      .catch((e) => {
        setError(String(e?.message ?? e));
        setData(null);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(api.triage(), "bundled cases");
  }, []);

  function onVcf(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) load(api.triageVcf(file), file.name);
    e.target.value = "";
  }

  const counts = data?.counts ?? { ACT: 0, REVIEW: 0, CLEAR: 0 };
  const hasRows = !!data && data.items.length > 0;

  return (
    <div className="wrap">
      <div className="eyebrow">Batch triage</div>
      <h1>Triage worklist</h1>
      <div className="sub">
        The scarce resource is expert attention. Cases are sorted by how much they
        need a human — conflicts and boundary calls first, auto-clears last.{" "}
        <span className="muted">Source: {source}</span>
      </div>

      <div className="cards">
        <div className="stat stat--review">
          <div className="n">{counts.REVIEW}</div>
          <div className="statlbl">Needs review</div>
          <div className="desc">Conflicts, method divergence, or uncertain near a boundary.</div>
        </div>
        <div className="stat stat--act">
          <div className="n">{counts.ACT}</div>
          <div className="statlbl">Actionable</div>
          <div className="desc">Reaches a (likely) pathogenic call — report out.</div>
        </div>
        <div className="stat stat--clear">
          <div className="n">{counts.CLEAR}</div>
          <div className="statlbl">Auto-clear</div>
          <div className="desc">(Likely) benign — low priority.</div>
        </div>
      </div>

      <div className="btnrow" style={{ marginTop: 0, marginBottom: 18 }}>
        <button className="btn" onClick={() => load(api.triage(), "bundled cases")} disabled={loading}>
          Triage all bundled cases
        </button>
        <label className="btn ghost" style={{ cursor: loading ? "not-allowed" : "pointer" }}>
          Upload VCF…
          <input
            type="file"
            accept=".vcf,.txt,text/plain"
            onChange={onVcf}
            disabled={loading}
            style={{ display: "none" }}
          />
        </label>
        <a className="btn ghost" href={triageReportUrl()} target="_blank" rel="noreferrer">
          Open dashboard ↗
        </a>
      </div>

      {loading && (
        <>
          <div className="loading">
            <span className="spinner" />
            Running the full pipeline across the variant set…
          </div>
          <TableSkeleton rows={4} cols={5} />
        </>
      )}

      {error && !loading && (
        <div className="error">
          <strong>Triage failed.</strong> {error}
          <div style={{ marginTop: 10 }}>
            <button className="btn ghost" onClick={() => load(api.triage(), "bundled cases")}>
              Retry with bundled cases
            </button>
          </div>
        </div>
      )}

      {data && !loading && (
        <>
          {hasRows ? (
            <div className="ledger-wrap">
              <div className="tablescroll">
                <table>
                  <thead>
                    <tr>
                      <th>Queue</th>
                      <th>Variant</th>
                      <th>Classification</th>
                      <th>Points</th>
                      <th>Why</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((it) => (
                      <tr
                        key={it.id}
                        className={`rowlink row--${BUCKET_CLS[it.bucket]}`}
                        onClick={() => nav(`/audit/${it.id}`)}
                      >
                        <td>
                          <span className={`badge badge--${BUCKET_CLS[it.bucket]}`}>{it.bucket}</span>
                        </td>
                        <td className="mono">{it.variant}</td>
                        <td>
                          <span className={`tierchip v-${TIER_VAR[it.headline]}`}>{it.headline}</span>
                        </td>
                        <td className="mono">
                          {it.points >= 0 ? "+" : ""}
                          {it.points}
                        </td>
                        <td className="reason">{it.reason}</td>
                        <td>
                          <a
                            href={reportUrl(it.id)}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="mono"
                            style={{ fontSize: 11 }}
                          >
                            report ↗
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <EmptyState icon="◦" title="Nothing to triage">
              {data.note ??
                "No variants were classified. Upload a VCF whose records match the bundled evidence snapshots, or triage the bundled cases."}
            </EmptyState>
          )}

          {hasRows && (
            <div className="foot">
              Click a row for its audit view · each row links to a full report and the verifiable ledger.
            </div>
          )}

          {data.unmatched && data.unmatched.length > 0 && (
            <>
              <div className="sec">
                <span className="num">!</span>
                <h2>Unmatched VCF records</h2>
              </div>
              <p className="hint">
                {data.note ??
                  "Offline replay classifies only variants with a bundled evidence snapshot."}
              </p>
              <div className="ledger-wrap">
                <div className="tablescroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Chrom</th>
                        <th>Pos</th>
                        <th>ID</th>
                        <th>Ref</th>
                        <th>Alt</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.unmatched.map((u, i) => (
                        <tr key={i}>
                          <td className="mono">{u.chrom}</td>
                          <td className="mono">{u.pos}</td>
                          <td className="mono">{u.id}</td>
                          <td className="mono">{u.ref}</td>
                          <td className="mono">{u.alt}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
