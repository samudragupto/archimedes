/**
 * Typed client for the Archimedes FastAPI backend.
 *
 * Every call attaches the caller's Supabase access token; the API validates
 * it (HS256/JWKS) and scopes every query with RLS-equivalent ownership
 * checks. The browser never talks to Supabase Postgres for project data —
 * only to this API (and to Supabase Auth/Realtime directly).
 */
import type {
  ChatFrame,
  Job,
  JobEvent,
  Project,
  ProjectAggregate,
  RequirementsDigest,
  Section,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail ?? body);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as T;
}

export const api = {
  health: () => fetch(`${API_URL}/health`).then((r) => r.json()),

  listProjects: (token: string) => request<Project[]>("/projects", token),

  getProject: (token: string, id: string) => request<ProjectAggregate>(`/projects/${id}`, token),

  createProject: (token: string, body: { title: string; funder_name?: string }) =>
    request<Project>("/projects", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  /** Multipart upload; kind is solicitation | organization. */
  uploadDocument: async (token: string, projectId: string, kind: string, file: File) => {
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    return request<{ document: Record<string, unknown>; preview: string; total_chars: number; chunks: number }>(
      `/projects/${projectId}/documents`,
      token,
      { method: "POST", body: form },
    );
  },

  ingestUrl: (token: string, projectId: string, sourceUrl: string, kind: string) =>
    request<{ document: Record<string, unknown>; preview: string; total_chars: number; chunks: number }>(
      `/projects/${projectId}/documents/url`,
      token,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_url: sourceUrl, kind }),
      },
    ),

  requirementsDigest: (token: string, projectId: string) =>
    request<RequirementsDigest>(`/projects/${projectId}/requirements-digest`, token),

  /** Start the full agent pipeline — 202 with the job to watch. */
  run: (token: string, projectId: string) =>
    request<{ job_id: string; runtime: string; detail: string }>(`/projects/${projectId}/run`, token, {
      method: "POST",
    }),

  getJob: (token: string, jobId: string) => request<Job>(`/jobs/${jobId}`, token),

  jobEvents: (token: string, jobId: string, since?: string) =>
    request<JobEvent[]>(
      `/jobs/${jobId}/events${since ? `?since=${encodeURIComponent(since)}` : ""}`,
      token,
    ),

  saveSection: (token: string, sectionId: string, contentMd: string) =>
    request<Section>(`/sections/${sectionId}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content_md: contentMd }),
    }),

  fixIssue: (token: string, issueId: string) =>
    request<{ issue: Record<string, unknown>; section: Section; model_used: string; tokens_out: number }>(
      `/compliance-issues/${issueId}/fix`,
      token,
      { method: "POST" },
    ),

  /** Export as a blob (caller triggers the download / preview). */
  exportBlob: async (token: string, projectId: string, format: "md" | "docx" | "pdf") => {
    const res = await fetch(`${API_URL}/api/v1/projects/${projectId}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new ApiError(res.status, await parseError(res));
    return res.blob();
  },

  exportText: async (token: string, projectId: string) => {
    const res = await fetch(`${API_URL}/api/v1/projects/${projectId}/export?format=md`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new ApiError(res.status, await parseError(res));
    return res.text();
  },
};

/**
 * Consume the chat SSE stream. The endpoint answers with
 *   data: {"delta": "..."}*  → data: {"done": true, ...}  → data: [DONE]
 * and yields one parsed frame per delta/done frame.
 */
export async function streamChat(
  token: string,
  projectId: string,
  message: string,
  onFrame: (frame: ChatFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/v1/projects/${projectId}/chat`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, await parseError(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    // SSE frames are delimited by blank lines; each data line carries one JSON payload.
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of raw.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;
        try {
          onFrame(JSON.parse(payload) as ChatFrame);
        } catch {
          // a malformed frame must never kill the stream
        }
      }
    }
  }
}
