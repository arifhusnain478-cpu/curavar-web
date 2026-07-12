import { describe, it, expect } from "vitest";
import {
  LIVE_EXAMPLES,
  isGenomicHgvs,
  isRsid,
  validateLiveInput,
} from "./liveInput";

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
