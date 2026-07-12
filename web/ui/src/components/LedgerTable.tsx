import type { LedgerEntry } from "../types";

function fmtTime(ts: number): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

interface Props {
  entries: LedgerEntry[];
  verified: boolean;
  problems: string[];
  showTime?: boolean;
  onReverify?: () => void;
  verifying?: boolean;
  verifiedAt?: string | null;
}

// The hash-chained provenance ledger: every raw observation in entry order,
// each committing to the previous one. Optionally re-verifiable in place.
export function LedgerTable({
  entries,
  verified,
  problems,
  showTime = false,
  onReverify,
  verifying = false,
  verifiedAt = null,
}: Props) {
  return (
    <>
      <div className="ledger-wrap">
        <div className="tablescroll">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Source</th>
                <th>Locator</th>
                {showTime && <th>Retrieved</th>}
                <th>Prev → entry hash</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="mono">{e.id}</td>
                  <td>{e.source_type}</td>
                  <td>{e.source_name}</td>
                  <td className="mono">{e.locator}</td>
                  {showTime && <td className="mono">{fmtTime(e.retrieved_at)}</td>}
                  <td className="mono chain" title={e.entry_hash}>
                    <span className="lnk">
                      {e.prev_hash ? e.prev_hash.slice(0, 12) : "—"}
                    </span>
                    {" → "}
                    <span className="cur">{e.entry_hash.slice(0, 12)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className={`verify ${verified ? "ok" : "bad"}`}>
        <span className="mark">{verified ? "✓" : "✕"}</span>
        <span>
          {verified
            ? "Chain verified — every entry hashes correctly and links to the previous one."
            : "Chain FAILED: " + problems.join("; ")}
          {verifiedAt ? ` (re-verified ${verifiedAt})` : ""}
        </span>
        {onReverify && (
          <button
            className="btn ghost"
            style={{ marginLeft: "auto" }}
            onClick={onReverify}
            disabled={verifying}
          >
            {verifying ? "Re-verifying…" : "Re-verify chain"}
          </button>
        )}
      </div>
    </>
  );
}
