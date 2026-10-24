/* Live-run tiles shown full-width above the bento: start, progress, no-go gate, outputs (Gate A/B: bidwit-approvals).
   Same visual language as bidwit-bento (Tile, mono numbers, lime accent). */
import * as React from "react";
import { Download, FileUp, Loader2 } from "lucide-react";
import { Tile, cx } from "./bidwit-bento";
import { api } from "@/data/api";
import type { Gate, Health, RunRow, RunView } from "@/data/api";

const ACCENT = "oklch(0.89 0.2 128)";
const INK = "oklch(0.24 0.06 135)";
const WARN = "oklch(0.72 0.17 35)";
const VIOLET = "oklch(0.74 0.12 300)";

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
      style={kind === "primary" ? { background: ACCENT, color: INK } : kind === "warn" ? { background: WARN, color: "oklch(0.2 0.05 35)" } : undefined}
    >
      {children}
    </button>
  );
}

function Err({ msg }: { msg: string }) {
  return msg ? <p className="mt-3 rounded-xl border border-border px-3 py-2 text-[12px]" style={{ color: WARN }}>{msg}</p> : null;
}

/* ------------------------------------------------------------------ start */
export function StartTile({ health, runs, onStarted, onOpen }: { health: Health | null; runs: RunRow[]; onStarted: (id: string) => void; onOpen: (id: string) => void }) {
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [over, setOver] = React.useState(false);
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
  const pick = (f: File | undefined) => f && go(api.upload(f));

  return (
    <Tile title="Start a run" action={health && <AiBadge health={health} />}>
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
          <Btn kind="primary" disabled={busy} onClick={() => go(api.startSample("tender_main"))}>Network operations centre RFP (85 pages)</Btn>
          <Btn disabled={busy} onClick={() => go(api.startSample("tender_backup"))}>Security operations centre RFP (backup)</Btn>
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
export function LiveTile({ view }: { view: RunView }) {
  const trail = (view.progress ?? []).slice(-9);
  return (
    <Tile
      title={<span className="flex items-center gap-2"><Loader2 className="size-3.5 animate-spin" /> Running</span>}
      action={<span className="font-mono text-[11px] text-muted-foreground">{view.run_id}</span>}
    >
      <p className="text-[18px] font-semibold tracking-[-0.02em]">{view.doing || "starting"}</p>
      <ol className="mt-3 space-y-1 font-mono text-[12px]" aria-live="polite">
        {trail.map((p, i) => (
          <li key={i} className={cx("flex gap-3", i === trail.length - 1 ? "" : "text-muted-foreground")}>
            <span className="shrink-0 tabular-nums opacity-60">{new Date(p.t).toLocaleTimeString([], { hour12: false })}</span>
            <span className="shrink-0 w-[72px]" style={{ color: p.part === "workflow" ? ACCENT : p.part === "ai" ? VIOLET : undefined }}>{p.part}</span>
            <span className="min-w-0">{p.message}</span>
          </li>
        ))}
      </ol>
    </Tile>
  );
}

/* ------------------------------------------------------------------ no-go gate */
export function NoGoTile({ view, gate, reviewer, onSent }: { view: RunView; gate: Extract<Gate, { gate: "no_go" }>; reviewer: string; onSent: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
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
    <Tile title="No-go gate · the judge recommends not bidding">
      <p className="text-[15px] font-semibold">{gate.verdict.summary}</p>
      <ul className="mt-2 space-y-1 text-[12px]">
        {gate.verdict.blocking.slice(0, 8).map((b) => <li key={b.requirement_id}><b className="font-mono">{b.requirement_id}</b> · {b.detail || b.reason}</li>)}
      </ul>
      <div className="mt-4 flex justify-end gap-2">
        <Btn disabled={busy} onClick={() => send("continue")}>Draft anyway</Btn>
        <Btn kind="warn" disabled={busy} onClick={() => send("stop")}>Stop: no bid</Btn>
      </div>
      <Err msg={err} />
    </Tile>
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
