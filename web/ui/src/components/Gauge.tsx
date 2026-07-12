import { TIER_ORDER, TIER_SHORT, TIER_VAR } from "../types";

// The five-tier ACMG classification gauge, with the reconciled headline active.
export function Gauge({ headline }: { headline: string }) {
  return (
    <div className="gauge">
      {TIER_ORDER.map((t) => (
        <div
          key={t}
          className={`tier tier--${TIER_VAR[t]}${t === headline ? " active" : ""}`}
        >
          <span className="tier-dot" />
          {TIER_SHORT[t]}
        </div>
      ))}
    </div>
  );
}
