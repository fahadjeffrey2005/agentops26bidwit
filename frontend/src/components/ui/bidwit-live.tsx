/* Live-run tiles shown full-width above the bento: start, progress, no-go gate, outputs (Gate A/B: bidwit-approvals).
   Same visual language as bidwit-bento (Tile, mono numbers, lime accent). */
import * as React from "react";
import { Database, Download, FileUp, Loader2, Zap } from "lucide-react";
import { Tile, cx } from "./bidwit-bento";
import { GateHeader, RunRibbon } from "./bidwit-gatechrome";
import { api } from "@/data/api";
import type { Gate, Health, RunRow, RunView } from "@/data/api";

const ACCENT = "oklch(0.97 0 0)";
const INK = "oklch(0.145 0 0)";
const WARN = "oklch(0.68 0.15 25)";
const VIOLET = "oklch(0.72 0 0)";

function Btn({ children, onClick, kind = "ghost", disabled, title }: { children: React.ReactNode; onClick?: () => void; kind?: "primary" | "ghost" | "warn"; disabled?: boolean; title?: string }) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] font-semibold transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40",
        kind === "ghost" && "border border-border hover:bg-muted",
      )}
      style={kind === "primary" ? { background: ACCENT, color: INK } : kind === "warn" ? { background: WARN, color: "oklch(0.18 0.04 25)" } : undefined}
    >
      {children}
    </button>
  );
}

function Err({ msg }: { msg: string }) {
  return msg ? <p className="mt-3 rounded-xl border border-border px-3 py-2 text-[12px]" style={{ color: WARN }}>{msg}</p> : null;
}

/* ------------------------------------------------------------------ start */
export function StartTile({ health, runs, company, companyName, onStarted, onOpen, onBack }: { health: Health | null; runs: RunRow[]; company?: string; companyName?: string; onStarted: (id: string) => void; onOpen: (id: string) => void; onBack?: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [over, setOver] = React.useState(false);
  const [cached, setCached] = React.useState(true);          // demo default: instant, no provider calls
  const input = React.useRef<HTMLInputElement>(null);

  const go = async (p: Promise<{ run_id: string }>) => {
    setBusy(true);
    setErr("");
    try {
      onStarted((await p).run_id);
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };
  const pick = (f: File | undefined) => f && go(api.upload(f, company, cached));

  return (
    <Tile title={companyName ? `Give ${companyName} a tender` : "Start a run"}
      action={<span className="flex items-center gap-2">{onBack && <button type="button" onClick={onBack} className="rounded-full border border-border px-3 py-1 font-mono text-[11px] hover:bg-muted">change company</button>}{health && <AiBadge health={health} />}</span>}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border p-3">
        <span className="flex min-w-0 items-center gap-2.5">
          {cached ? <Database className="size-4 shrink-0" /> : <Zap className="size-4 shrink-0" />}
          <span className="min-w-0 text-[13px]">
            <b>{cached ? "Use cached data" : "Call the AI live"}</b>
            <span className="text-muted-foreground">
              {cached
                ? ` — answers replay from ${health?.cached_answers ?? 0} saved AI responses. Seconds, and no provider is called.`
                : " — every batch goes to the provider. Minutes on a free tier, and it can hit a rate limit."}
            </span>
          </span>
        </span>
        <span className="flex shrink-0 gap-1" role="radiogroup" aria-label="AI mode">
          {([[true, "Use cached data"], [false, "Live AI"]] as [boolean, string][]).map(([v, label]) => (
            <button key={label} type="button" role="radio" aria-checked={cached === v} onClick={() => setCached(v)}
              className="rounded-full border border-border px-3 py-1.5 text-[12px] font-semibold"
              style={cached === v ? { background: "oklch(0.97 0 0)", color: "oklch(0.145 0 0)", borderColor: "oklch(0.97 0 0)" } : undefined}>
              {label}
            </button>
          ))}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-[1.3fr_1fr]">
        <div
          role="button"
          tabIndex={0}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          onDragOver={(e) => (e.preventDefault(), setOver(true))}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => (e.preventDefault(), setOver(false), pick(e.dataTransfer.files[0]))}
          className={cx("flex min-h-[150px] cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border border-dashed p-5 text-center transition-colors", over ? "bg-muted" : "border-border")}
          style={over ? { borderColor: ACCENT } : undefined}
        >
          {busy ? <Loader2 className="size-6 animate-spin" /> : <FileUp className="size-6" />}
          <p className="text-[14px] font-semibold">Drop a tender PDF</p>
          <p className="text-[12px] text-muted-foreground">or click to choose · max {health?.max_upload_mb ?? 20} MB</p>
          <input ref={input} type="file" accept="application/pdf,.pdf" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-[12px] font-medium text-muted-foreground">Or a bundled public tender</p>
          <Btn kind="primary" disabled={busy} onClick={() => go(api.startSample("tender_main", company, cached))}>Network operations centre RFP (85 pages)</Btn>
          <Btn disabled={busy} onClick={() => go(api.startSample("tender_backup", company, cached))}>Security operations centre RFP (backup)</Btn>
          {runs.length > 0 && (
            <>
              <p className="mt-2 text-[12px] font-medium text-muted-foreground">Previous runs</p>
              <ul className="max-h-[120px] space-y-1 overflow-y-auto pr-1">
                {runs.slice(0, 12).map((r) => (
                  <li key={r.run_id}>
                    <button type="button" onClick={() => onOpen(r.run_id)} className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1 text-left text-[12px] hover:bg-muted">
                      <span className="truncate font-mono">{r.tender ?? r.run_id}</span>
                      <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{r.gate ? `gate ${r.gate}` : r.decision ?? r.status}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
      <Err msg={err} />
    </Tile>
  );
}

function AiBadge({ health }: { health: Health }) {
  const on = health.llm === "on" && (health.keys.groq || health.keys.gemini);
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 font-mono text-[11px]">
      <span className="size-1.5 rounded-full" style={{ background: on ? ACCENT : WARN }} aria-hidden />
      {on ? `AI on · ${health.keys.groq ? "Groq" : "Gemini"}` : "AI off · rules only"}
    </span>
  );
}

/* ------------------------------------------------------------------ live progress */
const RUN_STAGES = [
  ["extract", "Reading the tender", "PDF opened in a sandboxed process: text, tables, hidden text, scanned pages."],
  ["classify", "Classifying requirements", "What each unit is, and whether it is a must-meet rule."],
  ["gate_a", "Gate A", "You confirm the checklist."],
  ["kb", "Searching company evidence", "Restricted and expired records removed before the search."],
  ["judge", "Bid / no-bid", "Counts must-meet criteria with no evidence. Code only."],
  ["writer", "Drafting answers", "Only where the evidence is strong. Cites ids, quotes the evidence."],
  ["checker", "Checking every answer", "Citation, quote, numbers, overclaim, blocked source, coverage."],
  ["gate_b", "Gate B", "You review, riskiest first."],
  ["package", "Writing the outputs", "Bid draft, compliance matrix, report, audit trail."],
] as const;

export function LiveTile({ view }: { view: RunView }) {
  const trail = view.progress ?? [];
  const seen = new Set(trail.map((t) => t.part));
  const stageMsg = (k: string) => [...trail].reverse().find((t) => t.part === k)?.message ?? "";
  const lastWorkflow = [...trail].reverse().find((t) => t.part === "workflow")?.message ?? "";
  const m = lastWorkflow.match(/stage (\d)\/7/);
  const byStep: Record<string, number> = { "1": 0, "2": 1, "3": 3, "4": 4, "5": 5, "6": 6, "7": 8 };
  const at = m ? byStep[m[1]] ?? 0 : 0;
  const bottom = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { bottom.current?.scrollIntoView({ block: "nearest" }); }, [trail.length]);

  return (
    <Tile
      className="min-h-[calc(100vh-7rem)]"
      title={<span className="flex items-center gap-2"><Loader2 className="size-3.5 animate-spin" /> Running</span>}
      action={<span className="font-mono text-[11px] text-muted-foreground">{view.run_id}</span>}
    >
      <p className="text-[22px] font-semibold tracking-[-0.02em]">{view.doing || "starting"}</p>
      <p className="mt-1 text-[13px] text-muted-foreground">Every stage reports as it works. You can leave this open; the run keeps going.</p>
      {(view.progress ?? []).some((t) => /cached answers only/.test(t.message)) && (
        <p className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1 font-mono text-[11px]">
          <Database className="size-3.5" /> replaying cached AI answers
        </p>
      )}

      <div className="mt-6 grid flex-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <ol className="space-y-0">
          {RUN_STAGES.map(([key, label, what], i) => {
            const done = i < at || (seen.has(key) && i !== at);
            const cur = i === at;
            const gate = key.startsWith("gate");
            return (
              <li key={key} className="flex gap-3">
                <div className="flex w-5 shrink-0 flex-col items-center">
                  <span className="mt-[7px] block rounded-full" style={{
                    width: gate ? 13 : 9, height: gate ? 13 : 9,
                    border: gate ? `2px solid ${cur ? ACCENT : done ? "var(--foreground)" : "var(--muted-foreground)"}` : "none",
                    background: gate ? "var(--card)" : cur ? ACCENT : done ? "var(--foreground)" : "var(--muted-foreground)",
                    opacity: done || cur ? 1 : 0.3,
                    animation: cur ? "bw-pulse 1.8s ease-in-out infinite" : undefined,
                  }} />
                  {i < RUN_STAGES.length - 1 && <span className="w-px flex-1 bg-border" style={{ minHeight: 22 }} />}
                </div>
                <div className="min-w-0 pb-3">
                  <p className="text-[14px] font-medium" style={{ opacity: done || cur ? 1 : 0.45 }}>
                    {label}{gate && <span className="ml-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">you</span>}
                  </p>
                  <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground" style={{ opacity: done || cur ? 1 : 0.5 }}>
                    {(cur && stageMsg(key)) || what}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>

        <div className="flex min-h-[320px] flex-col rounded-2xl border border-border bg-muted/40 p-4">
          <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">Live log</p>
          <ol className="flex-1 space-y-1 overflow-y-auto font-mono text-[12px]" style={{ maxHeight: "min(52vh, 560px)" }} aria-live="polite">
            {trail.map((t, i) => (
              <li key={i} className={cx("flex gap-3", i === trail.length - 1 ? "" : "text-muted-foreground")}>
                <span className="shrink-0 tabular-nums opacity-60">{new Date(t.t).toLocaleTimeString([], { hour12: false })}</span>
                <span className="w-[66px] shrink-0" style={{ color: t.part === "workflow" ? ACCENT : t.part === "ai" ? VIOLET : undefined }}>{t.part}</span>
                <span className="min-w-0">{t.message}</span>
              </li>
            ))}
            {trail.length === 0 && <li className="text-muted-foreground">waiting for the first checkpoint…</li>}
            <div ref={bottom} />
          </ol>
        </div>
      </div>
    </Tile>
  );
}

/* ------------------------------------------------------------------ no-go gate */
export function NoGoTile({ view, gate, reviewer, onSent }: { view: RunView; gate: Extract<Gate, { gate: "no_go" }>; reviewer: string; onSent: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const v = gate.verdict;
  const send = async (action: "stop" | "continue") => {
    setBusy(true);
    try {
      await api.answer(view.run_id, "no_go", { reviewer, action });
      onSent();
    } catch (e) {
      setErr(String((e as Error).message));
      setBusy(false);
    }
  };
  return (
    <>
    <RunRibbon at="Judge" tender={view.report?.tender?.file} />
    <Tile title={<span className="font-mono text-[11px] uppercase tracking-widest">Decision gate · before any drafting</span>}>
      <GateHeader
        gate="B"
        kicker="The judge recommends not bidding"
        title="No-go"
        lede={`${v.summary.replace(/[.\s]*$/, "")}. Nothing has been drafted yet. Either stop here, or override and let the system draft what it can for the criteria that are covered.`}
        stat={<>{v.pass_fail_covered}<span className="opacity-40">/{v.pass_fail_total}</span></>}
        statLabel="must-meet criteria backed"
        strip={[
          { label: "backed by evidence", value: v.pass_fail_covered, color: "oklch(0.97 0 0)" },
          { label: "blocking gaps", value: v.blocking.length, color: WARN },
        ]}
        meta={<span className="text-muted-foreground">Decided in code, not by the AI. You can override it.</span>}
      />

      <h4 className="mb-2 mt-5 px-1 font-mono text-[11px] font-semibold uppercase tracking-widest" style={{ color: WARN }}>
        Blocking gaps <span className="font-normal text-muted-foreground">{v.blocking.length}</span>
      </h4>
      <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border">
        {v.blocking.map((b) => (
          <li key={b.requirement_id} className="flex flex-col gap-1 p-4 sm:flex-row sm:items-baseline sm:gap-3">
            <span className="w-[62px] shrink-0 font-mono text-[11px] text-muted-foreground">{b.requirement_id}</span>
            <span className="min-w-0 text-[14px] leading-relaxed">{b.detail || b.reason}</span>
          </li>
        ))}
      </ul>

      <div className="sticky bottom-3 z-10 mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-lg">
        <span className="text-[13px] text-muted-foreground">Stopping here ends the run with a report. Overriding continues to drafting and Gate B.</span>
        <span className="flex gap-2">
          <Btn disabled={busy} onClick={() => send("continue")}>Override: draft anyway</Btn>
          <Btn kind="warn" disabled={busy} onClick={() => send("stop")}>Confirm: do not bid</Btn>
        </span>
      </div>
      <Err msg={err} />
    </Tile>
    </>
  );
}

/* ------------------------------------------------------------------ outputs */
export function DoneTile({ view, onNew }: { view: RunView; onNew: () => void }) {
  const r = view.report;
  const files = ["bid_draft.md", "compliance.csv", "report.json", "audit.jsonl"];
  return (
    <Tile title={view.stopped ? "Run stopped" : "Run complete"} action={<Btn onClick={onNew}>New run</Btn>}>
      {view.stopped && <p className="mb-2 text-[13px]" style={{ color: WARN }}>{view.stopped}</p>}
      {view.failure && <p className="mb-2 text-[13px]" style={{ color: WARN }}>Internal error: {view.failure}</p>}
      {r && (
        <p className="text-[14px]">
          <b className="font-mono">{r.counts.answered ?? 0}</b> cited answers · <b className="font-mono">{r.counts.complied ?? 0}</b> compliance statements ·{" "}
          <b className="font-mono">{r.items.filter((i) => i.status === "gap" && i.gap_reason !== "human_decides").length}</b> gaps flagged ·{" "}
          <b className="font-mono">{r.items.filter((i) => i.gap_reason === "human_decides").length}</b> person tasks · <b className="font-mono" style={{ color: ACCENT }}>{r.silent_misses_count ?? "-"}</b> silent misses
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {files.map((f) => (
          <a key={f} href={api.fileUrl(view.run_id, f)} className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 font-mono text-[12px] hover:bg-muted">
            <Download className="size-3.5" /> {f}
          </a>
        ))}
      </div>
    </Tile>
  );
}
