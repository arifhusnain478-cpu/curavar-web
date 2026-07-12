// Client-side guidance for the live-lookup input. Detects obviously
// unresolvable identifiers BEFORE spending a MyVariant.info lookup, so a curious
// user gets a friendly nudge instead of a confusing "not found". Pure functions
// (no React) so they're trivially unit-testable.

export interface LiveExample {
  value: string;
  gene: string;
  note: string;
}

// Only variants confirmed to resolve live are offered as one-click examples.
export const LIVE_EXAMPLES: LiveExample[] = [
  { value: "rs1799950", gene: "BRCA1", note: "rsID" },
  { value: "rs1801133", gene: "MTHFR", note: "rsID" },
  { value: "chr17:g.43094464T>C", gene: "BRCA1", note: "genomic HGVS · GRCh38" },
];

const RSID = /^rs\d+$/i;
// genomic HGVS: optional "chr", a chromosome (1-22, X, Y, M/MT), then ":g."
const GENOMIC = /^(chr)?(\d{1,2}|x|y|m|mt):g\..+/i;
// a bare cDNA (c.) or non-coding (n.) change — no gene/genomic anchor
const BARE_CDNA = /^[cn]\.\S+/i;

export function isRsid(s: string): boolean {
  return RSID.test((s || "").trim());
}

export function isGenomicHgvs(s: string): boolean {
  return GENOMIC.test((s || "").trim());
}

export type LiveInputKind = "ok" | "empty" | "cdna" | "malformed";

export interface LiveInputCheck {
  ok: boolean;
  kind: LiveInputKind;
  message?: string;
}

const TRY = "Try an rsID (e.g. rs1799950) or a genomic HGVS (e.g. chr17:g.43094464T>C).";

// Validate a would-be live identifier. Returns ok:true for rsIDs and genomic
// HGVS; otherwise a friendly, specific nudge and never an API call.
export function validateLiveInput(raw: string): LiveInputCheck {
  const q = (raw || "").trim();
  if (!q) {
    return {
      ok: false,
      kind: "empty",
      message: `Enter a variant to look up. ${TRY} Or pick a bundled case above.`,
    };
  }
  if (RSID.test(q) || GENOMIC.test(q)) {
    return { ok: true, kind: "ok" };
  }
  if (BARE_CDNA.test(q)) {
    return {
      ok: false,
      kind: "cdna",
      message: `A bare cDNA change can't be looked up directly. ${TRY}`,
    };
  }
  return {
    ok: false,
    kind: "malformed",
    message: `That doesn't look like an rsID or a genomic HGVS. ${TRY}`,
  };
}
