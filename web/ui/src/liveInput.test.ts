import { describe, it, expect } from "vitest";
import {
  LIVE_EXAMPLES,
  LIVE_UNAVAILABLE_MSG,
  isBundledPrefix,
  isGenomicHgvs,
  isRsid,
  matchesBundledCase,
  routeClassifyInput,
  validateLiveInput,
} from "./liveInput";

// Mirror the two real bundled cases (both happen to be bare cDNAs).
const CASES = [
  { gene: "BRCA1", hgvs_c: "c.5266dupC", label: "BRCA1 c.5266dupC (p.Gln1756fs)" },
  { gene: "MTHFR", hgvs_c: "c.665C>T", label: "MTHFR c.665C>T (p.Ala222Val)" },
];

describe("validateLiveInput", () => {
  it("accepts rsIDs", () => {
    for (const q of ["rs1799950", "rs1801133", "RS80357906"]) {
      const r = validateLiveInput(q);
      expect(r.ok).toBe(true);
      expect(r.kind).toBe("ok");
    }
  });

  it("accepts genomic HGVS (with or without chr prefix)", () => {
    for (const q of ["chr17:g.43094464T>C", "17:g.43094464T>C", "chrX:g.100A>G"]) {
      expect(validateLiveInput(q).ok).toBe(true);
    }
  });

  it("blocks a bare cDNA change with the cDNA nudge (no lookup)", () => {
    for (const q of ["c.665C>T", "c.5266dupC", "n.123A>G"]) {
      const r = validateLiveInput(q);
      expect(r.ok).toBe(false);
      expect(r.kind).toBe("cdna");
      expect(r.message).toMatch(/bare cDNA change can't be looked up/i);
      expect(r.message).toMatch(/rsID/); // points to a working format
    }
  });

  it("blocks empty / whitespace input with a prompt to enter something", () => {
    for (const q of ["", "   ", "\t"]) {
      const r = validateLiveInput(q);
      expect(r.ok).toBe(false);
      expect(r.kind).toBe("empty");
      expect(r.message).toMatch(/enter a variant/i);
    }
  });

  it("blocks malformed input that matches no accepted shape", () => {
    for (const q of ["BRCA1", "p.Gln285Arg", "hello world", "rsABC"]) {
      const r = validateLiveInput(q);
      expect(r.ok).toBe(false);
      expect(r.kind).toBe("malformed");
      expect(r.message).toMatch(/doesn't look like an rsID or a genomic HGVS/i);
    }
  });

  it("trims surrounding whitespace before judging", () => {
    expect(validateLiveInput("  rs1799950  ").ok).toBe(true);
  });
});

describe("shape helpers", () => {
  it("isRsid / isGenomicHgvs", () => {
    expect(isRsid("rs123")).toBe(true);
    expect(isRsid("c.1A>G")).toBe(false);
    expect(isGenomicHgvs("chr17:g.43094464T>C")).toBe(true);
    expect(isGenomicHgvs("rs123")).toBe(false);
  });
});

describe("LIVE_EXAMPLES", () => {
  it("are all themselves valid live inputs", () => {
    expect(LIVE_EXAMPLES.length).toBeGreaterThanOrEqual(3);
    for (const ex of LIVE_EXAMPLES) {
      expect(validateLiveInput(ex.value).ok).toBe(true);
    }
  });
});

describe("matchesBundledCase (mirrors backend _match_hgvs)", () => {
  it("matches a bare cDNA, GENE+cDNA, GENE:cDNA, or full label — case/space-insensitive", () => {
    expect(matchesBundledCase("c.665C>T", CASES)).toBe(true);
    expect(matchesBundledCase("  c.665c>t ", CASES)).toBe(true); // trimmed + lowercased
    expect(matchesBundledCase("MTHFR c.665C>T", CASES)).toBe(true);
    expect(matchesBundledCase("MTHFR:c.665C>T", CASES)).toBe(true);
    expect(matchesBundledCase("BRCA1 c.5266dupC (p.Gln1756fs)", CASES)).toBe(true);
  });

  it("does not match a non-bundled variant", () => {
    for (const q of ["rs1801133", "c.123A>G", "chr17:g.43094464T>C", ""]) {
      expect(matchesBundledCase(q, CASES)).toBe(false);
    }
  });
});

describe("isBundledPrefix (mid-typing suppression)", () => {
  it("is true for a strict prefix of a bundled variant", () => {
    expect(isBundledPrefix("c.5266dup", CASES)).toBe(true);
    expect(isBundledPrefix("c.665C>", CASES)).toBe(true);
  });
  it("is false for a full match or an unrelated string", () => {
    expect(isBundledPrefix("c.665C>T", CASES)).toBe(false); // full match, not a strict prefix
    expect(isBundledPrefix("rs1801133", CASES)).toBe(false);
    expect(isBundledPrefix("", CASES)).toBe(false);
  });
});

describe("routeClassifyInput (the auto-routing decision)", () => {
  it("routes a bundled variant to offline — regardless of live availability", () => {
    expect(routeClassifyInput("c.665C>T", CASES, true).action).toBe("offline");
    expect(routeClassifyInput("BRCA1 c.5266dupC (p.Gln1756fs)", CASES, false).action).toBe(
      "offline"
    );
  });

  it("routes a resolvable non-bundled id to live when a key is available", () => {
    expect(routeClassifyInput("rs1801133", CASES, true).action).toBe("live");
    expect(routeClassifyInput("chr17:g.43094464T>C", CASES, true).action).toBe("live");
  });

  it("guides a bare cDNA (non-bundled) toward an rsID when live is available", () => {
    const r = routeClassifyInput("c.123A>G", CASES, true);
    expect(r.action).toBe("guide");
    expect(r.message).toMatch(/bare cDNA change can't be looked up/i);
  });

  it("shows the calm 'not enabled here' note for a non-bundled id when no key", () => {
    const r = routeClassifyInput("rs1801133", CASES, false);
    expect(r.action).toBe("unavailable");
    expect(r.message).toBe(LIVE_UNAVAILABLE_MSG);
    expect(r.message).toMatch(/isn't enabled here/i);
  });
});
