import type { ClassifyResult } from "../types";
import { TIER_VAR } from "../types";
import { Gauge } from "./Gauge";
import { Scorebar } from "./Scorebar";

// The verdict block: reconciled headline, five-tier gauge, points scorebar, and
// the dual-method cross-check banner (agree vs. diverge → flagged for review).
export function VerdictCard({ result }: { result: ClassifyResult }) {
  const c = result.classification;
  const tier = c.headline;
  return (
    <>
      <section className="verdict">
        <div className="verdict-top">
          <span className="verdict-label">Classification</span>
          <span className={`verdict-value v-${TIER_VAR[tier]}`}>{tier}</span>
          <span className="rule">reconciled from two methods</span>
        </div>
        <Gauge headline={tier} />
        <Scorebar points={result.points} />
      </section>

      {c.methods_agree ? (
        <div className="banner banner--ok">
          <strong>Methods agree.</strong> Both the 2015 combining rules and the
          2018/2020 points system return <b>{c.rule_based}</b>.
        </div>
      ) : (
        <div className="banner banner--warn">
          <strong>Methods diverge — expert review flagged.</strong> 2015 rules:{" "}
          <b>{c.rule_based}</b>; points system: <b>{c.points_based}</b> (
          {result.points.score >= 0 ? "+" : ""}
          {result.points.score} pts). {c.note}
        </div>
      )}
    </>
  );
}
