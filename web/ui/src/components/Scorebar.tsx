import type { PointsView } from "../types";

// Points scorebar over a −10..+12 window, mirroring the engine report exactly:
// colored tier zones with a needle at the score. Display-only — the number and
// the tiering both come from the deterministic engine.
const LO = -10;
const HI = 12;
const mark = (x: number) => ((x - LO) / (HI - LO)) * 100;

export function Scorebar({ points }: { points: PointsView }) {
  const clamped = Math.max(LO, Math.min(HI, points.score));
  const needle = mark(clamped);
  const zone = (a: number, b: number, color: string) => ({
    left: `${mark(a)}%`,
    width: `${mark(b) - mark(a)}%`,
    background: `var(${color})`,
  });

  return (
    <div className="scorebar">
      <div className="sb-track">
        <span className="sb-zone" style={zone(LO, -6, "--benign")} />
        <span className="sb-zone" style={zone(-6, -1, "--lbenign")} />
        <span className="sb-zone" style={zone(0, 5, "--vus")} />
        <span className="sb-zone" style={zone(6, 9, "--lpath")} />
        <span
          className="sb-zone"
          style={{ left: `${mark(10)}%`, width: `${100 - mark(10)}%`, background: "var(--path)" }}
        />
        <span className="sb-needle" style={{ left: `${needle}%` }} />
      </div>
      <div className="sb-labels">
        <span>Benign &minus;6</span>
        <span>VUS 0&ndash;5</span>
        <span>Path &ge;10</span>
      </div>
      <div className="sb-caption">
        Points score{" "}
        <b>
          {points.score >= 0 ? "+" : ""}
          {points.score}
        </b>{" "}
        ({points.pathogenic_points >= 0 ? "+" : ""}
        {points.pathogenic_points} pathogenic, {points.benign_points} benign)
        {points.distance_to_next ? ` · ${points.distance_to_next}` : ""}
      </div>
    </div>
  );
}
