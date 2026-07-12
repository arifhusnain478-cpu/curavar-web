import { NavLink } from "react-router-dom";
import type { Config } from "../types";

export function Nav({ config }: { config: Config | null }) {
  return (
    <nav className="nav">
      <div className="nav-inner">
        <NavLink to="/" className="brand">
          <span className="mark">CuraVar</span>
          <span className="tag">Auditable variant curation</span>
        </NavLink>
        <NavLink to="/" end className="link">
          Classify
        </NavLink>
        <NavLink to="/triage" className="link">
          Triage
        </NavLink>
        <span
          className={`livechip ${config?.live_available ? "on" : ""}`}
          title={
            config?.live_available
              ? "ANTHROPIC_API_KEY detected — live mode available"
              : "Offline replay mode — no API key needed"
          }
        >
          {config?.live_available ? "● live ready" : "○ offline replay"}
        </span>
      </div>
    </nav>
  );
}
