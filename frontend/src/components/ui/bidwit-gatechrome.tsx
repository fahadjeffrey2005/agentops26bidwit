/* Shared chrome that tells the two gates apart at a glance.

   RunRibbon  where you are in the run, on both gates.
   GateHeader each gate gets its own identity:
              A = paper (white), "the tender asks"  -> you are reading the buyer's document
              B = ink (dark) + a risk strip, "your bid answers" -> you are checking what we send back
*/
import * as React from "react";
import { cx } from "./bidwit-bento";

const PAPER = "oklch(0.97 0 0)";
const INK = "oklch(0.145 0 0)";
const WARN = "oklch(0.68 0.15 25)";

const STEPS = ["Tender", "Gate A", "Evidence", "Judge", "Gate B", "Outputs"] as const;

export function RunRibbon({ at, company, tender }: { at: "Gate A" | "Judge" | "Gate B"; company?: string; tender?: string }) {
  const i = STEPS.indexOf(at);
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-2xl border border-border px-4 py-2.5">
      <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1 font-mono text-[11px] uppercase tracking-widest">
        {STEPS.map((s, n) => (
          <li key={s} className="flex items-center gap-1.5">
            <span className={cx(n === i && "rounded-full px-2 py-0.5 font-semibold")}
              style={n === i ? { background: PAPER, color: INK } : { color: n < i ? "var(--foreground)" : "var(--muted-foreground)", opacity: n < i ? 0.8 : 0.45 }}>
              {s}
            </span>
            {n < STEPS.length - 1 && <span className="text-muted-foreground opacity-40">›</span>}
          </li>
        ))}
      </ol>
      {(company || tender) && (
        <p className="font-mono text-[11px] text-muted-foreground">
          {company}{company && tender ? " · " : ""}{tender}
        </p>
      )}
    </div>
  );
}

export function GateHeader({ gate, kicker, title, lede, stat, statLabel, strip, meta }: {
  gate: "A" | "B";
  kicker: string;
  title: string;
  lede: string;
  stat: React.ReactNode;
  statLabel: string;
  strip?: { label: string; value: number; color?: string }[];
  meta?: React.ReactNode;
}) {
  const paper = gate === "A";
  const total = Math.max(1, (strip ?? []).reduce((a, b) => a + b.value, 0));
  return (
    <div
      className={cx("relative overflow-hidden rounded-3xl p-6 sm:p-7", !paper && "border border-border")}
      style={paper ? { background: PAPER, color: INK } : { background: "var(--muted)" }}
    >
      {paper && (
        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-25" style={{
          backgroundImage: "repeating-linear-gradient(45deg, #808080 0px 1px, transparent 1px 10px)",
          maskImage: "radial-gradient(ellipse 70% 60% at 100% 0%, #000 60%, transparent 110%)",
          WebkitMaskImage: "radial-gradient(ellipse 70% 60% at 100% 0%, #000 60%, transparent 110%)",
          contain: "paint",
        }} />
      )}
      <div className="relative flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 max-w-2xl">
          <span className="inline-block rounded-full px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-widest"
            style={paper ? { background: "oklch(0.145 0 0 / 0.1)" } : { background: "oklch(1 0 0 / 0.1)" }}>
            {kicker}
          </span>
          <h2 className="mt-4 text-[28px] font-semibold leading-[1.1] tracking-[-0.03em] sm:text-[36px]">{title}</h2>
          <p className={cx("mt-3 text-[14px] leading-relaxed", paper ? "opacity-70" : "text-muted-foreground")}>{lede}</p>
        </div>
        <div className="text-right">
          <p className="font-mono text-[52px] font-semibold leading-none tracking-[-0.05em] tabular-nums sm:text-[64px]">{stat}</p>
          <p className={cx("mt-1 font-mono text-[11px] uppercase tracking-widest", paper ? "opacity-60" : "text-muted-foreground")}>{statLabel}</p>
        </div>
      </div>

      {strip && strip.length > 0 && (
        <div className="relative mt-6">
          <div className="flex h-2.5 w-full overflow-hidden rounded-full" style={{ background: paper ? "oklch(0.145 0 0 / 0.08)" : "var(--card)" }}>
            {strip.filter((s) => s.value > 0).map((s) => (
              <span key={s.label} title={`${s.label}: ${s.value}`} style={{ width: `${(s.value / total) * 100}%`, background: s.color ?? (paper ? INK : "var(--foreground)") }} />
            ))}
          </div>
          <ul className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px]">
            {strip.map((s) => (
              <li key={s.label} className="flex items-center gap-1.5" style={{ opacity: s.value ? 1 : 0.4 }}>
                <span className="size-2 rounded-full" style={{ background: s.color ?? (paper ? INK : "var(--foreground)") }} />
                <span className="tabular-nums">{s.value}</span>
                <span className={paper ? "opacity-60" : "text-muted-foreground"}>{s.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {meta && <div className={cx("relative mt-5 border-t pt-4 text-[13px]", paper ? "border-black/10" : "border-border")}>{meta}</div>}
    </div>
  );
}

export const GATE_WARN = WARN;
