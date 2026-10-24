/* Turns a live run (GET /api/runs/{id}) into the props the bento dashboard needs.
   Nothing is invented: every number is counted from the run. */
import type { AuditItem, ReqRow, ReqStatus, VaultDoc } from "./adapter-types";
import type { EvidenceRow, RunView } from "./api";

export const STAGES = [
  { key: "extract", label: "Reader" },
  { key: "classify", label: "Classifier" },
  { key: "gate_a", label: "Gate A" },
  { key: "kb", label: "Librarian" },
  { key: "judge", label: "Judge" },
  { key: "writer", label: "Writer" },
  { key: "checker", label: "Checker" },
  { key: "gate_b", label: "Gate B" },
  { key: "package", label: "Package" },
] as const;

const STAGE_OF_STEP: Record<string, number> = { "1/7": 0, "2/7": 1, "3/7": 3, "4/7": 4, "5/7": 5, "6/7": 6, "7/7": 8 };

function stageIndex(v: RunView): number {
  if (v.status === "done") return STAGES.length;
  if (v.gate?.gate === "A") return 2;
  if (v.gate?.gate === "no_go") return 4;
  if (v.gate?.gate === "B") return 7;
  const last = [...(v.progress ?? [])].reverse().find((p) => p.part === "workflow");
  const m = last?.message.match(/stage (\d\/7)/);
  if (m) return STAGE_OF_STEP[m[1]] ?? 0;
  return 0;
}

export function pipeline(v: RunView) {
  const detail: Record<string, string> = {};
  for (const e of v.audit) {
    if (e.event === "ok" || e.level === "error") continue;
    const key = e.part === "gate_nogo" ? "judge" : e.part;
    if (!detail[key]) detail[key] = e.event.split(";")[0].slice(0, 60);
  }
  const at = stageIndex(v);
  return {
    stages: STAGES.map((s) => ({ key: s.key, label: s.label, detail: detail[s.key] ?? "" })),
    at: Math.min(at, STAGES.length - 1),
  };
}

function status(i: RunView["report"] extends infer R ? (R extends { items: (infer I)[] } ? I : never) : never): ReqStatus | null {
  if (i.status === "skipped") return null;
  if (i.status === "not_drafted") return "pending";                 // not searched / drafted yet
  if (i.status === "answered") return i.checks_passed === false ? "flagged" : "cited";
  if (i.status === "complied") return "needs_input";
  if (i.status === "gap" && i.gap_reason === "human_decides") return "human";
  return "flagged";
}

const REASON: Record<string, string> = {
  no_evidence: "no company evidence",
  missing_terms: "a required standard or term is missing",
  human_decides: "a person decides",
  over_draft_limit: "over the draft limit",
  failed_checks: "failed the checks",
  ai_unavailable: "AI unavailable",
};

export function requirements(v: RunView): ReqRow[] {
  const out: ReqRow[] = [];
  for (const i of v.report?.items ?? []) {
    const s = status(i);
    if (!s) continue;
    out.push({
      id: i.requirement_id,
      text: i.requirement || i.requirement_id,
      page: i.page,
      mandatory: i.pass_fail,
      category: i.category,
      status: s,
      evidence: i.evidence_ids,
      score: i.status === "answered" ? 1 : 0,
      note: i.status === "gap" ? REASON[i.gap_reason] ?? i.gap_reason : i.status === "complied" ? "compliance statement" : i.evidence_ids.join(", "),
    });
  }
  return out;
}

export function verdict(v: RunView) {
  const vd = v.report?.verdict ?? (v.gate && "verdict" in v.gate ? v.gate.verdict : null);
  if (!vd) return null;
  return {
    decision: vd.decision,
    summary: vd.summary,
    reasons: vd.blocking.map((b) => ({ requirement_id: b.requirement_id, reason: b.detail || REASON[b.reason] || b.reason })),
  };
}

export function queue(v: RunView) {
  const q = v.gate?.gate === "B" ? v.gate.queue : [];
  const by = q.reduce<Record<string, number>>((m, x) => ((m[x.risk] = (m[x.risk] ?? 0) + 1), m), {});
  return { by, total: q.length };
}

const LOOK = {
  restricted: { color: "oklch(0.4 0 0)", color2: "oklch(0.28 0 0)", ink: "oklch(0.92 0 0)" },
  expired: { color: "oklch(0.8 0 0)", color2: "oklch(0.6 0 0)", ink: "oklch(0.15 0 0)" },
  cited: { color: "oklch(0.97 0 0)", color2: "oklch(0.82 0 0)", ink: "oklch(0.145 0 0)" },
};

export function vault(v: RunView, ev: EvidenceRow[]): VaultDoc[] {
  const uses = new Map<string, string[]>();
  for (const i of v.report?.items ?? []) for (const e of i.evidence_ids) uses.set(e, [...(uses.get(e) ?? []), i.requirement_id]);
  const blocked = ev.filter((e) => e.blocked_reason).map<VaultDoc>((e) => ({
    id: e.id,
    title: e.title.replace(/ - .*/, ""),
    meta: `${e.confidentiality}${e.expires_on ? ` · expired ${e.expires_on}` : ""}`,
    state: "blocked",
    why: e.blocked_reason === "restricted" ? "Restricted. Never indexed, never sent to any model." : "Expired. Filtered out of every search, so it can't be cited.",
    ...LOOK[e.blocked_reason as "restricted" | "expired"],
  }));
  const cited = [...uses.entries()]
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, 3)
    .map<VaultDoc>(([id, reqs]) => {
      const e = ev.find((x) => x.id === id);
      return {
        id,
        title: (e?.title ?? id).replace(/ - .*/, ""),
        meta: `${e?.confidentiality ?? ""}${e?.expires_on ? ` · valid to ${e.expires_on}` : ""}`,
        state: "cited",
        why: `Cited for ${reqs.slice(0, 3).join(", ")}${reqs.length > 3 ? ` +${reqs.length - 3}` : ""}. Quote checked in code.`,
        ...LOOK.cited,
      };
    });
  return [...blocked, ...cited];
}

export function audit(v: RunView): AuditItem[] {
  const out: AuditItem[] = [];
  const step: Record<string, string> = { extract: "01", classify: "02", gate_a: "03", kb: "04", judge: "05", gate_nogo: "05", writer: "06", checker: "07", gate_b: "08", package: "09" };
  v.audit.forEach((e, n) => {
    const s = step[e.part] ?? "--";
    const id = `a${n}`;
    if (e.level === "error") out.push({ id, kind: "flagged", title: `${e.part} failed, fallback used`, detail: e.event.slice(0, 90), status: "flagged", step: s });
    else if (e.part === "kb" && e.event.includes("blocked:") && !e.event.includes("blocked: none"))
      out.push({ id, kind: "blocked", title: "Evidence blocked", detail: e.event.split("blocked: ")[1].split(";")[0], status: "blocked", step: s });
    else if (e.part === "checker" && e.event.startsWith("FAIL")) out.push({ id, kind: "fail", title: e.event.slice(5, 60), detail: "Checker · sent back for rewrite", status: "fixed", step: s });
    else if (e.part.startsWith("gate")) out.push({ id, kind: "approved", title: e.part === "gate_a" ? "Checklist approved" : e.part === "gate_b" ? "Review done" : "No-go decision", detail: e.event.slice(0, 90), status: "approved", step: s });
    else if (e.part === "judge" && e.event !== "ok") out.push({ id, kind: "decision", title: e.event.split(":")[0], detail: e.event.slice(0, 90), status: "decided", step: s });
  });
  return out.reverse().slice(0, 8);
}
