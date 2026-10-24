/* Approval screens built for reading: Gate A (checklist) and Gate B (review).
   Header = StatsBento (supplied template); items = one readable card each, grouped, with plain-language
   controls. Table rows from the tender ("5 | criterion | Y/N | proof") are split into criterion + proof. */
import * as React from "react";
import { AlertTriangle, Bot, Check, ChevronDown, ListChecks, Scale, Undo2, X } from "lucide-react";
import { Pills, Tile, cx } from "./bidwit-bento";
import { StatsBento } from "./stats-bento";
import { api } from "@/data/api";
import type { Gate, PassFailReq, QueueEntry, RunView } from "@/data/api";

const ACCENT = "oklch(0.97 0 0)";
const INK = "oklch(0.145 0 0)";
const WARN = "oklch(0.68 0.15 25)";
const VIOLET = "oklch(0.72 0 0)";
const MUTED = "oklch(0.55 0 0)";

/* ------------------------------------------------------------------ readable text */
const SERIAL = /^(\(?[0-9ivxIVX]{1,4}(\.[0-9]{1,3})*[.)]?|[A-Za-z][.)]|S\.?\s?No\.?|Sr\.?\s?No\.?)$/;
const PROOF = /certificate|document|declaration|undertaking|copy|report|purchase order|letter|proof|statement/i;

export function readable(text: string) {
  const cells = text.split(" | ").map((c) => c.trim()).filter(Boolean);
  if (cells.length < 2) return { main: text, proof: "", flag: "", extra: [] as string[] };
  let flag = "";
  const rest: string[] = [];
  cells.forEach((c, i) => {
    if (i === 0 && SERIAL.test(c)) return;
    if (/^(Y\/N|Yes\/No)$/i.test(c)) return;
    if (c === "M") return void (flag = "Mandatory");
    if (c === "O") return void (flag = "Optional");
    rest.push(c);
  });
  if (!rest.length) return { main: text, proof: "", flag, extra: [] };
  const main = rest.reduce((a, b) => (b.length > a.length ? b : a));
  const others = rest.filter((c) => c !== main);
  const proof = others.filter((c) => PROOF.test(c)).join(" · ");
  return { main, proof, flag, extra: others.filter((c) => !PROOF.test(c)) };
}

function Readable({ text, size = "text-[15px]" }: { text: string; size?: string }) {
  const r = readable(text);
  return (
    <div className="min-w-0">
      <p className={cx(size, "leading-relaxed text-foreground")}>{r.main}</p>
      {(r.proof || r.flag || r.extra.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {r.flag && <Chip color={r.flag === "Mandatory" ? WARN : MUTED}>{r.flag}</Chip>}
          {r.proof && <Chip>Proof: {r.proof}</Chip>}
          {r.extra.map((e, i) => <Chip key={i}>{e}</Chip>)}
        </div>
      )}
    </div>
  );
}

function Chip({ children, color }: { children: React.ReactNode; color?: string }) {
  return (
    <span className="inline-flex max-w-full items-center rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground" style={color ? { color, borderColor: color } : undefined}>
      <span className="truncate">{children}</span>
    </span>
  );
}

function Ref({ id, page }: { id: string; page?: number | null }) {
  return (
    <div className="w-[68px] shrink-0 pt-0.5 font-mono text-[11px] leading-5 text-muted-foreground">
      <div className="text-foreground">{id}</div>
      {page != null && <div>page {page}</div>}
    </div>
  );
}

function Footer({ children }: { children: React.ReactNode }) {
  return (
    <div className="sticky bottom-3 z-10 mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card/95 px-4 py-3 shadow-lg backdrop-blur">
      {children}
    </div>
  );
}

function Primary({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-[13px] font-semibold disabled:opacity-40" style={{ background: ACCENT, color: INK }}>
      {children}
    </button>
  );
}

function groupBy<T>(xs: T[], key: (x: T) => string) {
  const m = new Map<string, T[]>();
  for (const x of xs) m.set(key(x), [...(m.get(key(x)) ?? []), x]);
  return [...m.entries()];
}

/* ------------------------------------------------------------------ Gate A */
/** A statement as short points: sentences, and numbered lists inside a sentence ("1.ISO ... 2.ISO ..."). */
export function points(text: string): string[] {
  const main = readable(text).main.replace(/\s+/g, " ").trim();
  const parts = main
    .split(/(?<=[.;])\s+(?=[A-Z(])|\s+(?=\d{1,2}\s?\.\s?[A-Z])|\s+(?=[o•▪]\s)/)
    .map((p) => p.replace(/^[o•▪]\s+/, "").trim())
    .filter((p) => p.length > 1);
  return parts.length ? parts.slice(0, 8) : [main];
}

type MustMeet = "yes" | "no" | "drop";

function Choice({ on, color, ink, onClick, children, label }: { on: boolean; color: string; ink: string; onClick: () => void; children: React.ReactNode; label: string }) {
  return (
    <button type="button" aria-pressed={on} aria-label={label} onClick={onClick}
      className="inline-flex w-full items-center justify-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-[12px] font-semibold transition-colors hover:bg-muted sm:w-[150px]"
      style={on ? { background: color, color: ink, borderColor: color } : undefined}>
      {children}
    </button>
  );
}

export function GateATile({ view, gate, reviewer, onSent }: { view: RunView; gate: Extract<Gate, { gate: "A" }>; reviewer: string; onSent: () => void }) {
  const [dec, setDec] = React.useState<Record<string, MustMeet>>({});
  const [filter, setFilter] = React.useState<"All" | "To review" | "Eligibility">("All");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const items = gate.pass_fail;
  const set = (id: string, d: MustMeet) => setDec((m) => { const n = { ...m }; if (n[id] === d) delete n[id]; else n[id] = d; return n; });
  const n = (d: MustMeet) => Object.values(dec).filter((x) => x === d).length;
  const open = items.filter((r) => !dec[r.id]).length;
  const kept = items.length - n("no") - n("drop");
  const cats = ["eligibility", "technical", "commercial", "format"];
  const shown = items.filter((r) => (filter === "To review" ? !dec[r.id] : filter === "Eligibility" ? r.category === "eligibility" : true));
  const confirmRest = () => setDec((m) => { const x = { ...m }; for (const r of items) if (!x[r.id]) x[r.id] = "yes"; return x; });
  const send = async () => {
    setBusy(true);
    try {
      const ids = (d: MustMeet) => Object.entries(dec).filter(([, v]) => v === d).map(([k]) => k);
      await api.answer(view.run_id, "A", { reviewer, not_requirements: ids("drop"), pass_fail_remove: ids("no") });
      onSent();
    } catch (e) {
      setErr(String((e as Error).message));
      setBusy(false);
    }
  };

  return (
    <Tile title="Gate A · confirm the must-meet rules" action={<Pills label="filter" value={filter} options={["All", "To review", "Eligibility"]} onChange={setFilter} />}>
      <StatsBento
        primary={{ label: "Must-meet rules", value: `${kept}/${items.length}`,
          caption: "A must-meet rule is a condition the buyer uses to reject a bid outright, before any scoring. Confirm each one, or mark it as not must-meet." }}
        secondary={{ label: "By category", value: <span className="font-mono">{gate.requirement_count} <span className="text-[13px] text-muted-foreground">requirements read</span></span>,
          bars: cats.map((c, i) => ({ label: c, value: items.filter((r) => r.category === c).length, color: [ACCENT, VIOLET, WARN, MUTED][i] })) }}
        small={{ value: open, label: "to review" }}
        wide={{ icon: gate.classify_mode === "ai" ? <Bot className="size-4" /> : <ListChecks className="size-4" />, value: gate.classify_mode === "ai" ? "Found by AI + rules" : "Found by rules", label: `Reviewer: ${reviewer}` }}
      />

      {gate.notes.length > 0 && (
        <div className="mt-4 rounded-2xl border p-4" style={{ borderColor: WARN }}>
          <p className="mb-2 flex items-center gap-2 text-[13px] font-semibold" style={{ color: WARN }}><AlertTriangle className="size-4" /> Check these pages by hand</p>
          <ul className="space-y-1 text-[13px]">{gate.notes.map((x, i) => <li key={i}><b>Page {x.page}</b> · {x.flag.replace("_", " ")}: {x.detail}</li>)}</ul>
        </div>
      )}

      <div className="mt-5 space-y-6">
        {groupBy(shown, (r: PassFailReq) => r.section || "No section").map(([section, rs]) => (
          <section key={section}>
            <h4 className="mb-2 flex items-baseline justify-between px-1 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              <span className="truncate">{section}</span>
              <span className="font-mono">{rs.length}</span>
            </h4>
            <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border">
              {rs.map((r) => {
                const d = dec[r.id];
                const ps = points(r.text);
                const meta = readable(r.text);
                return (
                  <li key={r.id} className={cx("flex flex-col gap-4 p-4 sm:flex-row sm:items-start", d === "drop" && "opacity-45")}>
                    <Ref id={r.id} page={r.page} />
                    <div className={cx("min-w-0 flex-1", d === "drop" && "line-through")}>
                      {ps.length > 1 ? (
                        <ul className="space-y-1.5">
                          {ps.map((p, i) => (
                            <li key={i} className="flex gap-2.5 text-[15px] leading-relaxed">
                              <span className="mt-[9px] size-1.5 shrink-0 rounded-full" style={{ background: ACCENT }} aria-hidden />
                              <span>{p}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-[15px] leading-relaxed">{ps[0]}</p>
                      )}
                      {(meta.proof || meta.flag || meta.extra.length > 0) && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {meta.extra.map((x, i) => <Chip key={i}>{x}</Chip>)}
                          {meta.flag && <Chip color={meta.flag === "Mandatory" ? WARN : MUTED}>Tender marks it: {meta.flag}</Chip>}
                          {meta.proof && <Chip>Proof asked: {meta.proof}</Chip>}
                        </div>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-col gap-1.5">
                      <Choice label={`${r.id} is must-meet`} on={d === "yes"} color={ACCENT} ink={INK} onClick={() => set(r.id, "yes")}><Check className="size-3.5" /> Must-meet</Choice>
                      <Choice label={`${r.id} is not must-meet`} on={d === "no"} color={WARN} ink="oklch(0.18 0.04 25)" onClick={() => set(r.id, "no")}><X className="size-3.5" /> Not must-meet</Choice>
                      <button type="button" onClick={() => set(r.id, "drop")} className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
                        {d === "drop" ? <span className="inline-flex items-center gap-1"><Undo2 className="size-3" /> Undo remove</span> : "Not a requirement at all"}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>

      <Footer>
        <div className="flex flex-wrap items-center gap-3 text-[13px] text-muted-foreground">
          <span><b className="text-foreground">{n("yes")}</b> confirmed · <b className="text-foreground">{n("no")}</b> not must-meet · <b className="text-foreground">{n("drop")}</b> removed · <b className="text-foreground">{open}</b> to review</span>
          {open > 0 && <button type="button" onClick={confirmRest} className="rounded-full border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted">Confirm the {open} remaining</button>}
        </div>
        <Primary disabled={busy || open > 0} onClick={send}><Check className="size-4" /> {open > 0 ? `Review ${open} more` : "Approve checklist"}</Primary>
      </Footer>
      {err && <p className="mt-2 text-[13px]" style={{ color: WARN }}>{err}</p>}
    </Tile>
  );
}

/* ------------------------------------------------------------------ Gate B */
const RISK: Record<QueueEntry["risk"], { label: string; color: string; group: string }> = {
  failed_check: { label: "Failed check", color: WARN, group: "Fix or reject: the checker found a problem" },
  blocking_gap: { label: "Blocking gap", color: WARN, group: "Blocking gaps: pass/fail items without evidence" },
  gap: { label: "Gap", color: VIOLET, group: "Other gaps: no evidence or a missing standard" },
  pass_fail: { label: "Pass/fail answer", color: ACCENT, group: "Drafted answers to pass/fail items" },
  answer: { label: "Answer", color: ACCENT, group: "Other drafted answers" },
  human_task: { label: "For a person", color: MUTED, group: "One click: tasks for a person" },
  compliance: { label: "Compliance", color: MUTED, group: "One click: standard compliance statements" },
};

const GAP_WHY: Record<string, string> = {
  no_evidence: "no company evidence strong enough to cite. Add a document to the evidence library, or answer it by hand.",
  missing_terms: "the evidence found does not mention a required standard or term.",
  ai_unavailable: "not drafted because the AI was unavailable; the evidence may exist.",
  over_draft_limit: "not drafted this run (draft limit reached).",
  failed_checks: "the AI's answer failed the checks and was dropped.",
  human_decides: "a person decides this.",
};

function Decide({ id, value, set }: { id: string; value?: "approve" | "reject"; set: (d?: "approve" | "reject") => void }) {
  return (
    <div className="flex shrink-0 gap-1.5">
      <button type="button" aria-label={`approve ${id}`} onClick={() => set(value === "approve" ? undefined : "approve")}
        className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-[12px] font-medium"
        style={value === "approve" ? { background: ACCENT, color: INK, borderColor: ACCENT } : undefined}><Check className="size-3" /> Approve</button>
      <button type="button" aria-label={`reject ${id}`} onClick={() => set(value === "reject" ? undefined : "reject")}
        className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-[12px] font-medium"
        style={value === "reject" ? { background: WARN, color: "oklch(0.18 0.04 25)", borderColor: WARN } : undefined}><X className="size-3" /> Reject</button>
    </div>
  );
}

function Entry({ q, value, set }: { q: QueueEntry; value?: "approve" | "reject"; set: (d?: "approve" | "reject") => void }) {
  const [open, setOpen] = React.useState(q.kind !== "group");
  return (
    <li className="p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        {q.kind === "group" ? <Ref id={q.id} /> : <Ref id={q.requirement_id ?? q.id} page={q.page} />}
        <div className="min-w-0 flex-1">
          {q.kind === "group" ? (
            <p className="text-[15px] leading-relaxed"><b className="font-mono">{q.count}</b> items · {q.detail}</p>
          ) : (
            <Readable text={q.requirement ?? ""} />
          )}
        </div>
        <Decide id={q.id} value={value} set={set} />
      </div>
      <div className="mt-3 sm:ml-[80px]">
        {q.kind === "answer" && (
          <div className="rounded-2xl bg-muted p-4">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Drafted answer {q.id}</p>
            <p className="mt-1 text-[15px] leading-relaxed">{q.answer}</p>
            {q.checks && q.checks.length > 0 && <ul className="mt-2 space-y-0.5 text-[13px]" style={{ color: WARN }}>{q.checks.map((c, i) => <li key={i}>✗ {c}</li>)}</ul>}
            {q.evidence?.map((e) => (
              <p key={e.id} className="mt-2 text-[13px] text-muted-foreground"><b className="font-mono text-foreground">{e.id}</b> {e.title} · quote checked: “{q.quote}”</p>
            ))}
          </div>
        )}
        {q.kind === "gap" && (
          <p className="text-[13px] text-muted-foreground">
            <b className="text-foreground">Why it's a gap:</b> {GAP_WHY[q.reason ?? ""] ?? q.reason}
            {q.detail && <span className="ml-1 font-mono text-[11px] opacity-70">({q.detail})</span>}
          </p>
        )}
        {q.kind === "group" && (
          <>
            {q.statement && <p className="text-[13px] text-muted-foreground"><b className="text-foreground">Statement used:</b> {q.statement}</p>}
            <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="mt-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground">
              <ChevronDown className={cx("size-3.5 transition-transform", !open && "-rotate-90")} /> {open ? "Hide" : "Show"} the {q.count} items
            </button>
            {open && (
              <ul className="mt-2 max-h-[260px] divide-y divide-border overflow-y-auto rounded-2xl border border-border">
                {q.items?.map((i) => (
                  <li key={i.requirement_id} className="flex gap-3 px-3 py-2 text-[13px]">
                    <span className="w-[56px] shrink-0 font-mono text-[11px] text-muted-foreground">{i.requirement_id}</span>
                    <span className="min-w-0">{readable(i.requirement).main}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </li>
  );
}

export function GateBReviewTile({ view, gate, reviewer, onSent }: { view: RunView; gate: Extract<Gate, { gate: "B" }>; reviewer: string; onSent: () => void }) {
  const [dec, setDec] = React.useState<Record<string, "approve" | "reject">>({});
  const [filter, setFilter] = React.useState<"All" | "Open" | "Risky">("All");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const q = gate.queue;
  const done = Object.keys(dec).length;
  const shown = q.filter((x) => (filter === "Open" ? !dec[x.id] : filter === "Risky" ? ["failed_check", "blocking_gap", "gap"].includes(x.risk) : true));
  const count = (r: QueueEntry["risk"][]) => q.filter((x) => r.includes(x.risk)).length;
  const set = (id: string) => (d?: "approve" | "reject") => setDec((m) => { const n = { ...m }; if (d) n[id] = d; else delete n[id]; return n; });
  const approveAnswers = () => setDec((m) => { const n = { ...m }; for (const x of q) if ((x.risk === "pass_fail" || x.risk === "answer") && !n[x.id]) n[x.id] = "approve"; return n; });
  const send = async () => {
    setBusy(true);
    try {
      await api.answer(view.run_id, "B", { reviewer, decisions: dec });
      onSent();
    } catch (e) {
      setErr(String((e as Error).message));
      setBusy(false);
    }
  };
  const v = gate.verdict;

  return (
    <Tile title="Gate B · review before anything leaves" action={<Pills label="filter" value={filter} options={["All", "Open", "Risky"]} onChange={setFilter} />}>
      <StatsBento
        primary={{ label: "Decisions", value: `${done}/${q.length}`, caption: "Riskiest first. Undecided items stay open in the report; nothing is sent on the AI's word." }}
        secondary={{ label: "Queue by risk", value: <span className="font-mono">{count(["failed_check", "blocking_gap", "gap"])} <span className="text-[13px] text-muted-foreground">need a careful look</span></span>,
          bars: [
            { label: "failed checks", value: count(["failed_check"]), color: WARN },
            { label: "blocking gaps", value: count(["blocking_gap"]), color: WARN },
            { label: "gaps", value: count(["gap"]), color: VIOLET },
            { label: "answers", value: count(["pass_fail", "answer"]), color: ACCENT },
            { label: "groups", value: count(["human_task", "compliance"]), color: MUTED },
          ] }}
        small={{ value: v.blocking.length, label: "blocking" }}
        wide={{ icon: <Scale className="size-4" />, value: `Judge: ${v.decision.replace("_", "-").toUpperCase()}`, label: v.summary }}
      />

      <div className="mt-5 space-y-6">
        {groupBy(shown, (x: QueueEntry) => x.risk).map(([risk, xs]) => (
          <section key={risk}>
            <h4 className="mb-2 flex items-baseline justify-between px-1 text-[11px] font-semibold uppercase tracking-widest" style={{ color: RISK[risk as QueueEntry["risk"]].color }}>
              <span>{RISK[risk as QueueEntry["risk"]].group}</span>
              <span className="font-mono">{xs.length}</span>
            </h4>
            <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border">
              {xs.map((x) => <Entry key={x.id} q={x} value={dec[x.id]} set={set(x.id)} />)}
            </ul>
          </section>
        ))}
      </div>

      <Footer>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[13px] text-muted-foreground"><b className="text-foreground">{done}</b> of {q.length} decided</span>
          <button type="button" onClick={approveAnswers} className="rounded-full border border-border px-3 py-1.5 text-[12px] font-medium hover:bg-muted">Approve all drafted answers</button>
        </div>
        <Primary disabled={busy} onClick={send}><Check className="size-4" /> Submit review as {reviewer}</Primary>
      </Footer>
      {err && <p className="mt-2 text-[13px]" style={{ color: WARN }}>{err}</p>}
    </Tile>
  );
}
