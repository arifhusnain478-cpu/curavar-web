import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ClassifyScreen } from "./ClassifyScreen";
import type { Config } from "../types";

const LIVE_CONFIG: Config = { version: "0.1.0", live_available: true, case_count: 4 };
const OFFLINE_CONFIG: Config = { version: "0.1.0", live_available: false, case_count: 4 };

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
  if (u.endsWith("/config")) return ok(LIVE_CONFIG);
  if (u.endsWith("/classify")) {
    classifyBodies.push(JSON.parse(opts.body));
    return ok(RESULT);
  }
  return Promise.resolve({ ok: false, status: 404, statusText: "NF", json: async () => ({ detail: "nf" }) } as Response);
}

function renderScreen(config: Config = LIVE_CONFIG) {
  return render(
    <MemoryRouter>
      <ClassifyScreen config={config} />
    </MemoryRouter>
  );
}

const mainButton = () => screen.getByRole("button", { name: /^(classify|gathering evidence)/i });

beforeEach(() => {
  classifyBodies = [];
  vi.stubGlobal("fetch", vi.fn(mockFetch));
});
afterEach(() => vi.unstubAllGlobals());

describe("ClassifyScreen — no mode toggle", () => {
  it("renders no live/offline mode toggle (only the strict checkbox)", async () => {
    renderScreen();
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    expect(screen.queryByRole("checkbox", { name: /live/i })).toBeNull();
    expect(screen.queryByText(/offline replay/i)).toBeNull();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(1); // strict, and nothing else
    expect(screen.getByRole("checkbox", { name: /strict mode/i })).toBeInTheDocument();
  });

  it("auto-classifies the first bundled case on load, with no live flag", async () => {
    renderScreen();
    await waitFor(() => expect(classifyBodies.length).toBe(1));
    expect(classifyBodies[0]).toMatchObject({ case_id: "brca1_c5266dupC" });
    expect(classifyBodies[0]).not.toHaveProperty("live");
  });
});

describe("ClassifyScreen — auto-routing", () => {
  it("typing a bundled variant classifies offline (no toggle, no live flag)", async () => {
    renderScreen();
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "c.665C>T" } });
    const btn = mainButton();
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    await waitFor(() => expect(classifyBodies.length).toBe(2));
    expect(classifyBodies[1]).toMatchObject({ hgvs: "c.665C>T" });
    expect(classifyBodies[1]).not.toHaveProperty("live"); // the server decides, not the client
  });

  it("typing an rsID auto-does a live lookup when a key is set", async () => {
    renderScreen(LIVE_CONFIG);
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "rs1801133" } });
    const btn = mainButton();
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    await waitFor(() => expect(classifyBodies.length).toBe(2));
    expect(classifyBodies[1]).toMatchObject({ hgvs: "rs1801133" });
    expect(classifyBodies[1]).not.toHaveProperty("live");
  });

  it("a bare cDNA shows the friendly hint as they type, and sends no request", async () => {
    renderScreen(LIVE_CONFIG);
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "c.123A>G" } });

    expect(await screen.findByText(/bare cDNA change can't be looked up/i)).toBeInTheDocument();
    expect(mainButton()).toBeDisabled();
    expect(classifyBodies.length).toBe(1); // still just the auto-run
  });

  it("with no key, a non-bundled variant shows the calm message (not a red error)", async () => {
    renderScreen(OFFLINE_CONFIG);
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "rs1801133" } });

    expect(await screen.findByText(/live lookup isn't enabled here/i)).toBeInTheDocument();
    expect(document.querySelector(".error")).toBeNull(); // calm .notice, never the red box
    expect(mainButton()).toBeDisabled();
    expect(classifyBodies.length).toBe(1);
  });

  it("clicking a known-good live example fills the box and classifies", async () => {
    renderScreen(LIVE_CONFIG);
    await waitFor(() => expect(classifyBodies.length).toBe(1));

    fireEvent.click(await screen.findByRole("button", { name: "rs1799950" }));

    await waitFor(() => expect(classifyBodies.length).toBe(2));
    expect(classifyBodies[1]).toMatchObject({ hgvs: "rs1799950" });
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("rs1799950");
  });

  it("does not offer live-example chips when no key is configured", async () => {
    renderScreen(OFFLINE_CONFIG);
    await waitFor(() => expect(classifyBodies.length).toBe(1));
    expect(screen.queryByRole("button", { name: "rs1799950" })).toBeNull();
  });
});
