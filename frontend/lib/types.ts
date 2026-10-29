// TypeScript mirrors of the Pydantic schemas in backend/api/schemas/.
// Kept in sync by hand through W16; W17+ generates from OpenAPI.

export type UseType =
  | "residential"
  | "hostel"
  | "office"
  | "institutional"
  | "commercial"
  | "mixed_use";

export type StructuralSystem = "rcc_framed" | "rcc_flat_slab" | "load_bearing";
export type SpecLevel = "basic" | "standard" | "premium";
export type PlanShape = "rectangular" | "l_shape" | "square" | "irregular";
export type InputSource = "form" | "text" | "plan";

export interface BuildingParams {
  use_type: UseType;
  plot_area_m2: number;
  builtup_area_m2: number;
  floors: number;
  floor_height_m: number;
  plan_shape: PlanShape;
  aspect_ratio: number;
  structural_system: StructuralSystem;
  spec_level: SpecLevel;
  sbc_kpa: number;
  location: string;
  source: InputSource;
}

export interface Project {
  id: string;
  org_id: string;
  name: string;
  location: string | null;
  use_type: string | null;
  created_at: string;
}

export interface ProjectEstimatePoint {
  estimate_id: string;
  created_at: string;
  total_inr: number | null;
  cost_per_m2: number | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  location: string | null;
  use_type: string | null;
  created_at: string;
  estimate_count: number;
  latest_total_inr: number | null;
  latest_cost_per_m2: number | null;
  series: ProjectEstimatePoint[];
}

export type Element =
  | "substructure"
  | "frame"
  | "masonry"
  | "finishes"
  | "doors_windows"
  | "waterproofing"
  | "services"
  | "external_works"
  | "miscellaneous";

export interface FormulaTrace {
  rule_id: string;
  version: string;
  formula: string;
  inputs: Record<string, string | number>;
  output: number;
  source: string | null;
}

export interface BOQLine {
  id: string;
  estimate_id: string;
  element: Element;
  seq: number;
  description: string;
  unit: string;
  qty: number;
  rate: number | null;
  amount: number | null;
  rate_item_id: string | null;
  formula_trace: FormulaTrace | null;
  override_reason: string | null;
  is_overridden: boolean;
}

export interface Estimate {
  id: string;
  project_id: string;
  version: number;
  status: "draft" | "in_review" | "approved";
  rule_set_id: string | null;
  rate_edition_id: string | null;
  cost_index: number;
  total_cost: number | null;
  totals_by_element: Record<Element, number> | null;
  scenario_label: string | null;
  created_at: string;
}

export type RunEventStatus = "pending" | "running" | "awaiting_user" | "completed" | "failed";

export interface RunEvent {
  step: string;
  status: RunEventStatus;
  message: string | null;
  data: Record<string, unknown> | null;
  ts: string;
}

export interface RunResponse {
  run_id: string;
  estimate_id: string;
  status: string;
  event_count: number;
}

export interface ApiErrorDetail {
  loc: string;
  msg: string;
  type: string;
}

export interface MappingCandidate {
  rate_item_id: string;
  item_no: string;
  chapter: string;
  description: string;
  unit: string;
  rate: number;
  score: number;
}

export interface MappingProposal {
  id: string;
  boq_line_id: string;
  boq_description: string;
  boq_unit: string;
  boq_qty: number;
  boq_element: Element;
  confidence: number;
  reason: string | null;
  strategy: string;
  status: "pending" | "accepted" | "skipped";
  top_candidates: MappingCandidate[];
  created_at: string;
}

export interface Benchmark {
  builtup_m2: number;
  total_inr: number;
  cost_per_m2: number;
  concrete_m3_per_m2: number | null;
  steel_kg_per_m2: number | null;
}

export interface ElementVariance {
  element: string;
  expected_inr: number;
  computed_inr: number;
  delta_inr: number;
  delta_pct: number;
}

export interface CaseReport {
  case_id: string;
  split: "calibration" | "held_out";
  source: string;
  expected_total_inr: number;
  computed_total_inr: number;
  total_delta_pct: number;
  cost_per_m2_expected: number;
  cost_per_m2_computed: number;
  element_variance: ElementVariance[];
  element_weighted_abs_error_pct: number;
  pass_total: boolean;
  pass_element: boolean;
}

export interface Gate2Report {
  cases: CaseReport[];
  median_total_abs_pct: number;
  median_element_weighted_pct: number;
  all_calibration_within_20: boolean;
  all_held_out_within_25: boolean;
  passed: boolean;
}
