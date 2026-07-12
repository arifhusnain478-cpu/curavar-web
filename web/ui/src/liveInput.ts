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

// ---------------------------------------------------------------------------
// Auto-routing: the user never chooses offline vs. live. Given what they typed
// and the server's capability, decide what will happen — mirroring the backend
// so the UI can guide input and preempt a doomed request. Pure + testable.
// ---------------------------------------------------------------------------

// Just the case fields the matcher needs (a subset of CaseSummary).
export interface BundledCase {
  gene: string;
  hgvs_c: string;
  label: string;
}

function normHgvs(s: string): string {
  return (s || "").replace(/\s+/g, "").toLowerCase();
}

// Mirrors the backend's service._match_hgvs: a normalized query matches a
// bundled case by its cDNA, "GENE cDNA", "GENE:cDNA", or full label.
export function matchesBundledCase(q: string, cases: BundledCase[]): boolean {
  const nq = normHgvs(q);
  if (!nq) return false;
  return cases.some((c) => {
    const candidates = [
      normHgvs(c.hgvs_c),
      normHgvs(`${c.gene}${c.hgvs_c}`),
      normHgvs(`${c.gene}:${c.hgvs_c}`),
      normHgvs(c.label),
    ];
    return candidates.includes(nq);
  });
}

// A strict prefix of some bundled candidate — i.e. the user is part-way through
// typing a bundled variant (several bundled cases are themselves bare cDNAs, so
// we must not flash a "can't be looked up" nudge at them mid-type).
export function isBundledPrefix(q: string, cases: BundledCase[]): boolean {
  const nq = normHgvs(q);
  if (!nq) return false;
  return cases.some((c) => {
    const candidates = [
      normHgvs(c.hgvs_c),
      normHgvs(`${c.gene}${c.hgvs_c}`),
      normHgvs(`${c.gene}:${c.hgvs_c}`),
      normHgvs(c.label),
    ];
    return candidates.some((cand) => cand.startsWith(nq) && cand !== nq);
  });
}

export const LIVE_UNAVAILABLE_MSG =
  "Live lookup isn't enabled here — try one of the example variants above.";

export type ClassifyAction = "offline" | "live" | "guide" | "unavailable";

export interface ClassifyRoute {
  action: ClassifyAction;
  // Present for "guide" (input-shape nudge) and "unavailable" (calm capability
  // note). Absent for "offline"/"live", which just run.
  message?: string;
}

// Decide how a typed query will be classified, and whether to nudge first.
//   offline     — matches a bundled snapshot; runs instantly, always available
//   live        — resolvable identifier + a server key; the backend looks it up
//   guide       — a bare cDNA / malformed id; show a friendly hint, no request
//   unavailable — not bundled and no server key; show one calm line, no request
export function routeClassifyInput(
  raw: string,
  cases: BundledCase[],
  liveAvailable: boolean
): ClassifyRoute {
  const q = (raw || "").trim();
  if (matchesBundledCase(q, cases)) return { action: "offline" };
  if (!liveAvailable) return { action: "unavailable", message: LIVE_UNAVAILABLE_MSG };
  const check = validateLiveInput(q);
  if (!check.ok) return { action: "guide", message: check.message };
  return { action: "live" };
}
