// Kept visible on every screen: this is decision-support, not a diagnosis.
export function Disclaimer() {
  return (
    <div className="disclaimer">
      <strong>Research decision-support only.</strong> CuraVar aggregates public
      evidence and applies the ACMG/AMP 2015 combining rules to make its reasoning
      inspectable. It does not provide a clinical diagnosis. A qualified molecular
      geneticist is responsible for the final interpretation. No
      patient-identifiable data is used; bundled demo evidence is a recorded
      snapshot.
      <div className="foot">
        CuraVar · classification math is deterministic and LLM-free · ledger
        integrity is independently re-verifiable
      </div>
    </div>
  );
}
