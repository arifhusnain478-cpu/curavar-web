// Typed client for the CuraVar Web API. Everything is same-origin under a
// configurable `/api` prefix (Vite proxy in dev, nginx in prod), so the
// Anthropic key and engine stay entirely server-side.

import type {
  CaseSummary,
  ClassifyResult,
  Config,
  LedgerResponse,
  TriageResult,
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE || "/api";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export interface ClassifyRequest {
  case_id?: string;
  hgvs?: string;
  live?: boolean;
  strict?: boolean;
  assembly?: string; // "hg38" (GRCh38, default) | "hg19" (GRCh37) — live lookups
}

export const api = {
  config: () => fetch(`${API_BASE}/config`).then((r) => j<Config>(r)),

  cases: () =>
    fetch(`${API_BASE}/cases`).then((r) =>
      j<{ cases: CaseSummary[] }>(r).then((d) => d.cases)
    ),

  classify: (req: ClassifyRequest) =>
    fetch(`${API_BASE}/classify`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    }).then((r) => j<ClassifyResult>(r)),

  triage: (case_ids?: string[]) =>
    fetch(`${API_BASE}/triage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(case_ids ? { case_ids } : {}),
    }).then((r) => j<TriageResult>(r)),

  triageVcf: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${API_BASE}/triage/vcf`, { method: "POST", body: fd }).then(
      (r) => j<TriageResult>(r)
    );
  },

  ledger: (id: string, strict = false) =>
    fetch(`${API_BASE}/ledger/${encodeURIComponent(id)}?strict=${strict}`).then(
      (r) => j<LedgerResponse>(r)
    ),
};

// URLs for the server-rendered HTML documents (opened in a new tab).
export const reportUrl = (id: string, strict = false) =>
  `${API_BASE}/variants/${encodeURIComponent(id)}/report?strict=${strict}`;

export const triageReportUrl = () => `${API_BASE}/triage/report`;
