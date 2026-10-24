/* Thin client for the BidWit API (backend/bidwit/api). Vite proxies /api to 127.0.0.1:8000 in dev. */

export type RunStatus = "running" | "waiting" | "done" | "failed";

export interface Item {
  requirement_id: string;
  requirement: string;
  page: number | null;
  section: string;
  category: string;
  pass_fail: boolean;
  status: "answered" | "complied" | "gap" | "skipped" | "not_drafted";
  claim_id: string;
  answer: string;
  evidence_ids: string[];
  checks_passed: boolean | null;
  gap_reason: string;
  gap_detail: string;
  human_decision: "" | "approve" | "reject";
}

export interface Verdict {
  decision: "go" | "conditional" | "no_go";
  summary: string;
  pass_fail_total: number;
  pass_fail_covered: number;
  blocking: { requirement_id: string; reason: string; detail: string }[];
}

export interface Report {
  run_id: string;
  tender: { file: string; sha256: string; pages: number; units: number; flags: { page: number; flag: string; detail: string }[] } | null;
  stopped: string;
  verdict: Verdict | null;
  modes: { classify: string | null; retrieve: string | null; writer: string | null };
  counts: Record<string, number>;
  ai_calls: number;
  rounds: { round: number; passed: number; total: number }[];
  final: boolean;
  silent_misses_count: number | null;
  blocked_evidence: { id: string; reason: string; detail: string }[];
  items: Item[];
}

export interface QueueEntry {
  id: string;
  kind: "answer" | "gap" | "group";
  risk: "failed_check" | "blocking_gap" | "gap" | "pass_fail" | "answer" | "human_task" | "compliance";
  requirement_id?: string;
  page?: number | null;
  requirement?: string;
  answer?: string;
  quote?: string;
  checks?: string[];
  evidence?: { id: string; title: string; text: string }[];
  reason?: string;
  detail?: string;
  count?: number;
  statement?: string;
  items?: { requirement_id: string; page: number | null; requirement: string; detail?: string }[];
}

export interface PassFailReq {
  id: string;
  text: string;
  section: string | null;
  page: number;
  category: string;
  pass_fail: boolean;
}

export type Gate =
  | { gate: "A"; notes: { page: number; flag: string; detail: string }[]; pass_fail: PassFailReq[]; requirement_count: number; classify_mode: string }
  | { gate: "no_go"; verdict: Verdict }
  | { gate: "B"; queue: QueueEntry[]; verdict: Verdict };

export interface RunView {
  run_id: string;
  status: RunStatus;
  doing: string;
  gate: Gate | null;
  stopped: string;
  failure?: string;
  report: Report | null;
  audit: { t: string; part: string; level: "info" | "warn" | "error"; event: string }[];
  errors: { kind: string; type: string; message: string }[];
  progress?: { t: string; part: string; message: string }[];
  archived?: boolean;
}

export interface RunRow {
  run_id: string;
  status: RunStatus;
  gate: string | null;
  tender: string | null;
  decision: string | null;
  stopped: string;
}

export interface EvidenceRow {
  id: string;
  title: string;
  client: string | null;
  confidentiality: "public" | "internal" | "restricted";
  date: string;
  expires_on: string | null;
  text: string | null;
  usable: boolean;
  blocked_reason: "" | "restricted" | "expired";
}

export interface Fact {
  label: string;
  value: string;
  note: string;
  source: string;
}

export interface Company {
  id: string;
  name: string;
  city: string;
  founded: number;
  blurb: string;
  facts?: Fact[];
}

export interface ProfileDoc {
  id: string;
  title: string;
  client: string | null;
  confidentiality: string;
  date: string;
  expires_on: string | null;
  text: string | null;
  kind: string;
  usable: boolean;
  blocked_reason: "" | "restricted" | "expired";
}

export interface CompanyProfile extends Company {
  documents: ProfileDoc[];
  counts: Record<string, number>;
}

export interface Health {
  ok: boolean;
  version: string;
  llm: "on" | "off";
  chain: string[];
  keys: { groq: boolean; gemini: boolean };
  max_upload_mb: number;
  ai_budget: number;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  // every POST carries X-BidWit: the backend refuses POSTs without it (blocks cross-site requests)
  const headers = init?.method === "POST" ? { ...(init.headers ?? {}), "X-BidWit": "1" } : init?.headers;
  const r = await fetch(path, { ...init, headers });
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const b = await r.json();
      msg = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail ?? b);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => call<Health>("/api/health"),
  evidence: (company?: string) => call<EvidenceRow[]>(`/api/evidence${company ? `?company=${encodeURIComponent(company)}` : ""}`),
  companies: () => call<Company[]>("/api/companies"),
  company: (id: string) => call<CompanyProfile>(`/api/companies/${encodeURIComponent(id)}`),
  runs: () => call<RunRow[]>("/api/runs"),
  run: (id: string) => call<RunView>(`/api/runs/${encodeURIComponent(id)}`),
  startSample: (sample: string, company?: string) => {
    const f = new FormData();
    f.append("sample", sample);
    if (company) f.append("company", company);
    return call<{ run_id: string }>("/api/runs", { method: "POST", body: f });
  },
  upload: (file: File, company?: string) => {
    const f = new FormData();
    f.append("file", file);
    if (company) f.append("company", company);
    return call<{ run_id: string }>("/api/runs", { method: "POST", body: f });
  },
  answer: (id: string, gate: "A" | "no_go" | "B", body: object) =>
    call<{ run_id: string }>(`/api/runs/${encodeURIComponent(id)}/gates/${gate}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  fileUrl: (id: string, name: string) => `/api/runs/${encodeURIComponent(id)}/files/${name}`,
};
