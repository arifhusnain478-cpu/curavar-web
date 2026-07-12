// Response shapes mirrored from the FastAPI models (web/api/models.py).

export interface Config {
  version: string;
  live_available: boolean;
  case_count: number;
}

export interface CaseSummary {
  id: string;
  gene: string;
  hgvs_c: string;
  hgvs_p: string;
  label: string;
  synthetic: boolean;
}

export interface VariantView {
  gene: string;
  hgvs_c: string;
  hgvs_p: string;
  genome_build: string;
  coordinate: string;
  inheritance: string;
  label: string;
}

export interface EvidenceView {
  id: string;
  source_type: string;
  source_name: string;
  locator: string;
  snippet: string;
  retrieved_at: number;
  entry_hash: string;
  prev_hash: string;
  payload: Record<string, unknown>;
}

export interface CriterionView {
  code: string;
  direction: "pathogenic" | "benign";
  strength: string;
  description: string;
  justification: string;
  points: number;
  evidence_ids: string[];
  evidence: EvidenceView[];
}

export interface RemovedCriterion {
  code?: string;
  reason?: string;
}

export interface ClassificationView {
  headline: string;
  rule_based: string;
  rule_fired: string;
  points_based: string;
  methods_agree: boolean;
  diverges_across_vus: boolean;
  contradiction: boolean;
  note: string;
}

export interface PointsView {
  score: number;
  pathogenic_points: number;
  benign_points: number;
  classification: string;
  conflict: boolean;
  distance_to_next: string;
  breakdown: { code: string; points: number }[];
}

export interface Pvs1View {
  strength: string;
  path: string[];
}

export interface LedgerEntry {
  id: string;
  source_type: string;
  source_name: string;
  locator: string;
  retrieved_at: number;
  payload: Record<string, unknown>;
  snippet: string;
  prev_hash: string;
  entry_hash: string;
}

export interface LedgerDump {
  ledger_version: number;
  entry_count: number;
  entries: LedgerEntry[];
}

export interface ClassifyResult {
  id: string;
  mode: string;
  strict: boolean;
  variant: VariantView;
  classification: ClassificationView;
  points: PointsView;
  activated_criteria: CriterionView[];
  removed_criteria: RemovedCriterion[];
  pvs1: Pvs1View | null;
  ledger: LedgerDump;
  ledger_verified: boolean;
  ledger_problems: string[];
}

export interface TriageItem {
  id: string;
  variant: string;
  gene: string;
  headline: string;
  points: number;
  bucket: "ACT" | "REVIEW" | "CLEAR";
  reason: string;
  priority: number;
  methods_agree: boolean;
  ledger_verified: boolean;
}

export interface TriageResult {
  counts: { ACT: number; REVIEW: number; CLEAR: number };
  total: number;
  items: TriageItem[];
  matched?: number;
  unmatched?: { chrom: string; pos: string; id: string; ref: string; alt: string }[];
  note?: string;
}

export interface LedgerResponse extends LedgerDump {
  id: string;
  variant: string;
  verified: boolean;
  problems: string[];
}

// Tier -> CSS variable suffix used across gauge/verdict/chips.
export const TIER_VAR: Record<string, string> = {
  Benign: "benign",
  "Likely benign": "lbenign",
  "Uncertain significance": "vus",
  "Likely pathogenic": "lpath",
  Pathogenic: "path",
};

export const TIER_ORDER: string[] = [
  "Benign",
  "Likely benign",
  "Uncertain significance",
  "Likely pathogenic",
  "Pathogenic",
];

export const TIER_SHORT: Record<string, string> = {
  Benign: "Benign",
  "Likely benign": "Likely benign",
  "Uncertain significance": "Uncertain (VUS)",
  "Likely pathogenic": "Likely pathogenic",
  Pathogenic: "Pathogenic",
};
