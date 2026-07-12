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
        {/* A quiet positive indicator when live lookups are possible. No
            "mode" is ever shown to the user — bundled cases always work. */}
        {config?.live_available && (
          <span
            className="livechip on"
            title="A server API key is set — variants outside the bundled set are looked up live automatically."
          >
            ● live evidence
          </span>
        )}
      </div>
    </nav>
  );
}
