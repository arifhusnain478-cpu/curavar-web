import type { Pvs1View } from "../types";

// The ClinGen SVI PVS1 loss-of-function decision path. Showing the steps is the
// whole point: it's exactly where a flat rule over-calls Pathogenic.
export function Pvs1Path({ pvs1 }: { pvs1: Pvs1View }) {
  return (
    <section className="panel">
      <h2 style={{ marginTop: 0 }}>PVS1 decision tree</h2>
      <p className="panel-sub">
        Loss-of-function strength assigned by the ClinGen SVI decision tree (Abou
        Tayoun et al. 2018), not by a flat rule. Outcome: <b>{pvs1.strength}</b>.
      </p>
      <ol className="pvs1-steps">
        {pvs1.path.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
    </section>
  );
}
