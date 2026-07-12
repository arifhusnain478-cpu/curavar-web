import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, reportUrl } from "../api";
import type { LedgerResponse } from "../types";
import { LedgerTable } from "../components/LedgerTable";
import { TableSkeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";

export function AuditScreen() {
  const { id = "" } = useParams();
  const [data, setData] = useState<LedgerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verifiedAt, setVerifiedAt] = useState<string | null>(null);

  const fetchLedger = useCallback(
    (reverify: boolean) => {
      if (reverify) setVerifying(true);
      else setLoading(true);
      setError(null);
      api
        .ledger(id)
        .then((d) => {
          setData(d);
          if (reverify) setVerifiedAt(new Date().toLocaleTimeString());
        })
        .catch((e) => {
          setError(String(e?.message ?? e));
          if (!reverify) setData(null);
        })
        .finally(() => {
          setLoading(false);
          setVerifying(false);
        });
    },
    [id]
  );

  useEffect(() => {
    fetchLedger(false);
  }, [fetchLedger]);

  return (
    <div className="wrap">
      <div className="eyebrow">Audit view</div>
      <h1>Provenance ledger</h1>
      <div className="sub">
        {data ? data.variant : id} · independently re-verifiable hash chain
      </div>

      <div className="btnrow" style={{ marginTop: 0, marginBottom: 8 }}>
        <Link className="btn ghost" to="/">
          ← Back to classify
        </Link>
        <a className="btn ghost" href={reportUrl(id)} target="_blank" rel="noreferrer">
          Open full report ↗
        </a>
      </div>

      {loading && <TableSkeleton rows={5} cols={5} />}

      {error && !loading && (
        <div className="error">
          <strong>Couldn't load the ledger.</strong> {error}
          <div style={{ marginTop: 10 }}>
            <button className="btn ghost" onClick={() => fetchLedger(false)}>
              Try again
            </button>
            <Link className="btn ghost" to="/triage" style={{ marginLeft: 8 }}>
              Back to worklist
            </Link>
          </div>
        </div>
      )}

      {data && !loading && (
        <>
          <p className="hint tight" style={{ marginTop: 18 }}>
            The ledger contains no interpretation — only raw observations, where
            each came from, and when. Every classification decision points back
            here. Altering any past entry breaks the chain, and re-verification
            catches it.
          </p>
          {data.entries.length === 0 ? (
            <EmptyState icon="◦" title="This ledger is empty">
              No evidence entries were recorded for this variant.
            </EmptyState>
          ) : (
            <>
              <LedgerTable
                entries={data.entries}
                verified={data.verified}
                problems={data.problems}
                showTime
                onReverify={() => fetchLedger(true)}
                verifying={verifying}
                verifiedAt={verifiedAt}
              />
              <div className="foot">
                {data.entry_count} entries · ledger version {data.ledger_version} ·
                each entry commits to the SHA-256 of the previous one.
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
