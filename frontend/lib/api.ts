// Typed fetch client + SSE streamer for the CE 725 BOQ API.
// Env: NEXT_PUBLIC_API_BASE (default http://127.0.0.1:8000),
//      NEXT_PUBLIC_API_KEY  (optional; required if the server has API_KEY set).

import type {
  Benchmark,
  BOQLine,
  BuildingParams,
  Estimate,
  Gate2Report,
  MappingProposal,
  Project,
  ProjectSummary,
  RunEvent,
  RunResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

function headers(extra?: HeadersInit): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return { ...h, ...(extra as Record<string, string> | undefined) };
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
  }
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    const msg =
      (typeof detail === "object" && detail && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : null) ?? `HTTP ${res.status}`;
    throw new ApiError(res.status, msg, detail);
  }
  return res.json() as Promise<T>;
}

// ------------------------------------------------------------------ projects
export const api = {
  async createProject(payload: {
    name: string;
    location?: string;
    use_type?: string;
  }): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(payload),
    });
    return j<Project>(res);
  },

  async listProjects(): Promise<Project[]> {
    const res = await fetch(`${API_BASE}/projects`, { headers: headers() });
    return j<Project[]>(res);
  },

  async listProjectSummaries(): Promise<ProjectSummary[]> {
    const res = await fetch(`${API_BASE}/projects/-/summary`, { headers: headers() });
    return j<ProjectSummary[]>(res);
  },

  // ---------------------------------------------------------------- estimates
  async createEstimate(
    projectId: string,
    payload: { params?: BuildingParams; text_brief?: string; cost_index?: number },
  ): Promise<Estimate> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/estimates`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(payload),
    });
    return j<Estimate>(res);
  },

  async getEstimate(id: string): Promise<Estimate> {
    const res = await fetch(`${API_BASE}/estimates/${id}`, { headers: headers() });
    return j<Estimate>(res);
  },

  async getEstimateParams(
    id: string,
  ): Promise<{ inputs: Partial<BuildingParams>; confidence: Record<string, number> | null; source: string }> {
    const res = await fetch(`${API_BASE}/estimates/${id}/params`, { headers: headers() });
    return j(res);
  },

  async listBOQ(id: string): Promise<BOQLine[]> {
    const res = await fetch(`${API_BASE}/estimates/${id}/boq`, { headers: headers() });
    return j<BOQLine[]>(res);
  },

  async patchBOQLine(
    estimateId: string,
    lineId: string,
    patch: { qty?: number; rate?: number; override_reason: string },
  ): Promise<BOQLine> {
    const res = await fetch(`${API_BASE}/estimates/${estimateId}/boq/${lineId}`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(patch),
    });
    return j<BOQLine>(res);
  },

  // ---------------------------------------------------------------- runs
  async startRun(estimateId: string): Promise<RunResponse> {
    const res = await fetch(`${API_BASE}/estimates/${estimateId}/runs`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ mode: "full" }),
    });
    return j<RunResponse>(res);
  },

  // ---------------------------------------------------------------- mapping
  async runMapping(
    estimateId: string,
    editionId?: string,
  ): Promise<{
    strategy: string;
    processed: number;
    auto_applied: number;
    queued: number;
    cache_hits: number;
    duration_s: number;
  }> {
    const q = editionId ? `?edition_id=${encodeURIComponent(editionId)}` : "";
    const res = await fetch(`${API_BASE}/estimates/${estimateId}/map${q}`, {
      method: "POST",
      headers: headers(),
    });
    return j(res);
  },

  async listMappingQueue(estimateId: string): Promise<MappingProposal[]> {
    const res = await fetch(`${API_BASE}/estimates/${estimateId}/mapping-queue`, {
      headers: headers(),
    });
    return j<MappingProposal[]>(res);
  },

  async acceptMapping(
    estimateId: string,
    proposalId: string,
    rateItemId: string,
  ): Promise<MappingProposal> {
    const res = await fetch(
      `${API_BASE}/estimates/${estimateId}/mapping/${proposalId}`,
      {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ rate_item_id: rateItemId }),
      },
    );
    return j<MappingProposal>(res);
  },

  async skipMapping(estimateId: string, proposalId: string): Promise<MappingProposal> {
    const res = await fetch(
      `${API_BASE}/estimates/${estimateId}/mapping/${proposalId}`,
      { method: "DELETE", headers: headers() },
    );
    return j<MappingProposal>(res);
  },

  // ---------------------------------------------------------------- validation
  async getBenchmarks(estimateId: string): Promise<Benchmark> {
    const res = await fetch(`${API_BASE}/estimates/${estimateId}/benchmarks`, {
      headers: headers(),
    });
    return j<Benchmark>(res);
  },

  async getGate2Report(): Promise<Gate2Report> {
    const res = await fetch(`${API_BASE}/validation/gate2`, { headers: headers() });
    return j<Gate2Report>(res);
  },

  // ---------------------------------------------------------------- exports
  exportUrl(estimateId: string, format: "xlsx" = "xlsx"): string {
    return `${API_BASE}/estimates/${estimateId}/export?format=${format}`;
  },
};

// -------------------------------------------------------------- SSE streaming
/** Stream run events via fetch + ReadableStream. EventSource can't send
 *  custom headers; fetch streaming can. */
export async function* streamRunEvents(runId: string, signal?: AbortSignal): AsyncGenerator<RunEvent> {
  const res = await fetch(`${API_BASE}/runs/${runId}/events`, {
    headers: headers({ Accept: "text/event-stream" }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, `SSE stream failed: HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split(/\n\n/);
    buf = blocks.pop() ?? "";
    for (const block of blocks) {
      const line = block.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const json = line.slice("data:".length).trim();
      if (!json) continue;
      try {
        yield JSON.parse(json) as RunEvent;
      } catch {
        // ignore malformed events; the backend emits well-formed JSON
      }
    }
  }
}

export { API_BASE, API_KEY };
