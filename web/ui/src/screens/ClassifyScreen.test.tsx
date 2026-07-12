import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ClassifyScreen } from "./ClassifyScreen";
import type { Config } from "../types";

const CONFIG: Config = { version: "0.1.0", live_available: true, case_count: 4 };

const CASES = [
  { id: "brca1_c5266dupC", gene: "BRCA1", hgvs_c: "c.5266dupC", hgvs_p: "p.Gln1756fs", label: "BRCA1 c.5266dupC (p.Gln1756fs)", synthetic: false },
  { id: "mthfr_c665CtoT", gene: "MTHFR", hgvs_c: "c.665C>T", hgvs_p: "p.Ala222Val", label: "MTHFR c.665C>T (p.Ala222Val)", synthetic: false },
];

// A minimal-but-complete ClassifyResult so the result tree renders.
const RESULT = {
  id: "brca1_c5266dupC",
  mode: "replay",
  strict: false,
  variant: { gene: "BRCA1", hgvs_c: "c.5266dupC", hgvs_p: "p.Gln1756fs", genome_build: "GRCh38", coordinate: "chr17:43057062:dupC", inheritance: "", label: "BRCA1 c.5266dupC" },
  classification: { headline: "Pathogenic", rule_based: "Pathogenic", rule_fired: "r", points_based: "Pathogenic", methods_agree: true, diverges_across_vus: false, contradiction: false, note: "Both methods agree." },
  points: { score: 11, pathogenic_points: 11, benign_points: 0, classification: "Pathogenic", conflict: false, distance_to_next: "", breakdown: [{ code: "PVS1", points: 8 }] },
  activated_criteria: [],
  removed_criteria: [],
  pvs1: null,
  ledger: { ledger_version: 1, entry_count: 0, entries: [] },
  ledger_verified: true,
  ledger_problems: [],
};

let classifyBodies: any[] = [];

function mockFetch(url: any, opts?: any) {
  const u = String(url);
  const ok = (data: any) => Promise.resolve({ ok: true, status: 200, json: async () => data } as Response);
  if (u.endsWith("/cases")) return ok({ cases: CASES });
  if (u.endsWith("/config")) return ok(CONFIG);
  if (u.endsWith("/classify")) {
    classifyBodies.push(JSON.parse(opts.body));
    return ok(RESULT);
  }
  return Promise.resolve({ ok: false, status: 404, statusText: "NF", json: async () => ({ detail: "nf" }) } as Response);
}

function renderScreen() {
  return render(
    <MemoryRouter>
      <ClassifyScreen config={CONFIG} />
    </MemoryRouter>
  );
}

beforeEach(() => {
  classifyBodies = [];
  vi.stubGlobal("fetch", vi.fn(mockFetch));
});
afterEach(() => vi.unstubAllGlobals());

describe("ClassifyScreen live-input validation", () => {
  it("auto-classifies the first bundled case on load", async () => {
    renderScreen();
    await waitFor(() => expect(classifyBodies.length).toBe(1));
    expect(classifyBodies[0]).toMatchObject({ case_id: "brca1_c5266dupC" });
  });

  it("typing a bare cDNA in live mode shows the nudge and does NOT hit the API", async () => {
    renderScreen();
    await waitFor(() => expect(classifyBodies.length).toBe(1)); // auto-run only

    fireEvent.click(screen.getByRole("checkbox", { name: /live mode/i }));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "c.665C>T" } });

    const btn = await screen.findByRole("button", { name: /look up live/i });
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    // friendly nudge appears...
    expect(await screen.findByText(/bare cDNA change can't be looked up/i)).toBeInTheDocument();
    // ...and NO new classify request was sent (still just the auto-run)
    expect(classifyBodies.length).toBe(1);
  });

  it("empty input in live mode prompts to enter something, no API call", async () => {
    renderScreen();
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    fireEvent.click(screen.getByRole("checkbox", { name: /live mode/i }));
    fireEvent.click(await screen.findByRole("button", { name: /look up live/i }));

    expect(await screen.findByText(/enter a variant/i)).toBeInTheDocument();
    expect(classifyBodies.length).toBe(1);
  });

  it("clicking a known-good example chip fills the box and classifies live", async () => {
    renderScreen();
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    fireEvent.click(screen.getByRole("checkbox", { name: /live mode/i }));
    const chip = await screen.findByRole("button", { name: "rs1799950" });
    fireEvent.click(chip);

    await waitFor(() => expect(classifyBodies.length).toBe(2));
    expect(classifyBodies[1]).toMatchObject({ hgvs: "rs1799950", live: true });
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("rs1799950");
  });

  it("a valid rsID typed manually is allowed through to the API", async () => {
    renderScreen();
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    fireEvent.click(screen.getByRole("checkbox", { name: /live mode/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "rs1801133" } });
    fireEvent.click(await screen.findByRole("button", { name: /look up live/i }));

    await waitFor(() => expect(classifyBodies.length).toBe(2));
    expect(classifyBodies[1]).toMatchObject({ hgvs: "rs1801133", live: true });
  });
});
