import type { CriterionView } from "../types";

const STRENGTH_LABEL: Record<string, string> = {
  very_strong: "Very strong",
  strong: "Strong",
  moderate: "Moderate",
  supporting: "Supporting",
  standalone: "Standalone",
};

// One activated ACMG criterion, traced to the ledger evidence that justifies it.
// No claim without its receipt — every criterion lists its cited entries.
export function CriterionCard({ crit }: { crit: CriterionView }) {
  const isPath = crit.direction === "pathogenic";
  const pts = `${crit.points >= 0 ? "+" : ""}${crit.points} pt${
    Math.abs(crit.points) !== 1 ? "s" : ""
  }`;
  return (
    <article className={`crit crit--${isPath ? "path" : "benign"}`}>
      <header className="crit-head">
        <span className="crit-code">{crit.code}</span>
        <span className="crit-strength">
          {STRENGTH_LABEL[crit.strength] ?? crit.strength} ·{" "}
          {isPath ? "Pathogenic" : "Benign"}
        </span>
        <span className="crit-pts">{pts}</span>
      </header>
      <p className="crit-desc">{crit.description}</p>
      <p className="crit-just">
        <span className="lbl">Why it applies</span>
        {crit.justification}
      </p>
      <div className="crit-ev">
        <span className="lbl">Traced to evidence</span>
        {crit.evidence.length === 0 ? (
          <div className="ev-miss">no evidence found</div>
        ) : (
          crit.evidence.map((e) => (
            <div className="ev" key={e.id}>
              <div className="ev-head">
                <span className="ev-id">{e.id}</span>
                <span className="ev-src">{e.source_name}</span>
                <span className="ev-loc">{e.locator}</span>
              </div>
              <div className="ev-snip">{e.snippet}</div>
            </div>
          ))
        )}
      </div>
    </article>
  );
}
