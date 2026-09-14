/**
 * Types mirrored from services/api/app/models/schemas.py — the single source
 * of truth for the wire format. Keep both sides in sync; the API returns
 * plain dicts of these rows (Pydantic serializes datetimes to ISO strings).
 */

export type ProjectStatus =
  | "draft"
  | "extracting"
  | "researching"
  | "drafting"
  | "auditing"
  | "revising"
  | "complete"
  | "failed";

export type DocumentKind = "solicitation" | "organization" | "supporting";

export type RequirementCategory =
  | "deadline"
  | "budget"
  | "eligibility"
  | "section"
  | "format"
  | "evaluation"
  | "other";

export type SectionStatus = "pending" | "drafting" | "done" | "needs_revision";
export type IssueSeverity = "blocker" | "major" | "minor";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type JobEventLevel = "info" | "model" | "tool" | "warn" | "error";
export type JobRuntime = "local" | "nebius_serverless";
export type Tier = "nano" | "super" | "ultra";

export interface Project {
  id: string;
  user_id: string;
  title: string;
  funder_name: string | null;
  status: ProjectStatus;
  solicitation_doc_id: string | null;
  org_doc_id: string | null;
  compliance_score: number | null;
  abstract: string | null;
  created_at?: string;
}

export interface Requirement {
  id: string | null;
  project_id: string | null;
  category: RequirementCategory;
  key: string;
  value: string;
  is_mandatory: boolean;
  source_excerpt: string | null;
  confidence: number;
}

export interface ResearchFinding {
  id: string | null;
  project_id: string | null;
  query: string;
  title: string;
  url: string;
  snippet: string | null;
  relevance: number;
  used_in_sections: string[];
}

export interface Section {
  id: string | null;
  project_id: string | null;
  order_index: number;
  title: string;
  content_md: string;
  model_used: string | null;
  token_count: number;
  status: SectionStatus;
}

export interface ComplianceIssue {
  id: string | null;
  project_id: string | null;
  section_id: string | null;
  requirement_id: string | null;
  severity: IssueSeverity;
  description: string;
  suggested_fix: string | null;
  resolved: boolean;
}

export interface Job {
  id: string;
  project_id: string;
  kind: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  error: string | null;
  runtime: JobRuntime;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobEvent {
  id: string | null;
  job_id: string | null;
  level: JobEventLevel;
  step: string | null;
  message: string;
  model_used: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  ts: string | null;
}

/** GET /projects/{id} — the aggregate payload the workspace binds to. */
export interface ProjectAggregate extends Project {
  requirements: Requirement[];
  sections: Section[];
  compliance_issues: ComplianceIssue[];
  research_findings: ResearchFinding[];
  jobs: Job[];
}

export interface DigestSection {
  title: string;
  requirements: { key: string; value: string }[];
}

export interface RequirementsDigest {
  deadline: string | null;
  budget: string | null;
  page_limit: string | null;
  eligibility: string[];
  sections: DigestSection[];
  total_requirements: number;
}

export interface ChatFrame {
  delta?: string;
  done?: boolean;
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  latency_ms?: number;
  needs_web?: boolean;
}

/** Map a full Nemotron model id (or "tavily") to its badge tier. */
export function tierOf(modelUsed: string | null | undefined): Tier | "tavily" | null {
  if (!modelUsed) return null;
  const m = modelUsed.toLowerCase();
  if (m.includes("nano")) return "nano";
  if (m.includes("super")) return "super";
  if (m.includes("ultra")) return "ultra";
  if (m.includes("tavily")) return "tavily";
  return null;
}

export const TIER_LABEL: Record<Tier | "tavily", string> = {
  nano: "Nemotron Nano",
  super: "Nemotron Super",
  ultra: "Nemotron Ultra",
  tavily: "Tavily",
};
