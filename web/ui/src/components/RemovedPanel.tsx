import type { RemovedCriterion } from "../types";

// Criteria the reviewer (adjudicator) proposed then dropped for weak support.
// Showing what was discarded is part of the audit trail.
export function RemovedPanel({ removed }: { removed: RemovedCriterion[] }) {
  if (!removed.length) return null;
  return (
    <section className="panel">
      <h2 style={{ marginTop: 0 }}>Reviewer removed</h2>
      <p className="panel-sub">
        Proposed by the evidence pass but dropped for insufficient support.
        Removing weak claims is part of the audit trail.
      </p>
      <ul className="removed">
        {removed.map((r, i) => (
          <li key={i}>
            <span className="crit-code sm">{r.code}</span>
            {r.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}
