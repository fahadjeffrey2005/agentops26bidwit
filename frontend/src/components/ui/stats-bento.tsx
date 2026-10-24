/* Stats bento (from the supplied template), made data-driven for the approval screens.
   Layout kept: 6 columns; primary stat 3x2 with the diagonal stripe pattern; secondary 3x1 with bars;
   two tertiary cards (1 and 2 columns). Colours come from BidWit's theme instead of shadcn's --primary. */
import * as React from "react";

export interface StatsBentoProps {
  primary: { label: string; value: React.ReactNode; caption: React.ReactNode };
  secondary: { label: string; value: React.ReactNode; bars: { label: string; value: number; color?: string }[] };
  small: { value: React.ReactNode; label: string };
  wide: { icon: React.ReactNode; value: React.ReactNode; label: string };
  accent?: string;
  ink?: string;
}

export function StatsBento({ primary, secondary, small, wide, accent = "oklch(0.89 0.2 128)", ink = "oklch(0.24 0.06 135)" }: StatsBentoProps) {
  const max = Math.max(1, ...secondary.bars.map((b) => b.value));
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-6 md:grid-rows-2">
      <div className="relative flex flex-col justify-between overflow-hidden rounded-3xl p-7 md:col-span-3 md:row-span-2" style={{ background: accent, color: ink }}>
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-30"
          style={{
            backgroundImage: "repeating-linear-gradient(45deg, #808080 0px 1px, transparent 1px 10px)",
            maskImage: "radial-gradient(ellipse 80% 50% at 100% 0%, #000 70%, transparent 110%)",
            WebkitMaskImage: "radial-gradient(ellipse 80% 50% at 100% 0%, #000 70%, transparent 110%)",
          }}
        />
        <div className="relative">
          <span className="mb-5 inline-block rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-widest" style={{ background: "oklch(0.24 0.06 135 / 0.1)", opacity: 0.75 }}>
            {primary.label}
          </span>
          <div className="font-mono text-6xl font-semibold tracking-tighter tabular-nums">{primary.value}</div>
        </div>
        <p className="relative mt-6 max-w-sm text-sm opacity-70">{primary.caption}</p>
      </div>

      <div className="flex items-center justify-between gap-4 rounded-3xl border border-border bg-muted p-6 md:col-span-3">
        <div className="min-w-0">
          <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-muted-foreground">{secondary.label}</p>
          <p className="text-3xl text-foreground">{secondary.value}</p>
        </div>
        <div className="flex h-16 shrink-0 items-end gap-2.5" role="img" aria-label={secondary.bars.map((b) => `${b.label} ${b.value}`).join(", ")}>
          {secondary.bars.map((b) => (
            <div key={b.label} className="flex flex-col items-center gap-1" title={`${b.label}: ${b.value}`}>
              <div className="w-3 rounded-full" style={{ height: `${Math.max(8, (b.value / max) * 40)}px`, background: b.color ?? "var(--foreground)" }} />
              <span className="font-mono text-[9px] text-muted-foreground">{b.value}</span>
              <span className="max-w-[44px] truncate text-[8px] uppercase tracking-wide text-muted-foreground">{b.label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-col justify-center rounded-3xl border border-border bg-card p-5 text-center md:col-span-1">
        <p className="font-mono text-2xl text-foreground">{small.value}</p>
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{small.label}</p>
      </div>

      <div className="flex items-center gap-4 rounded-3xl bg-muted p-5 md:col-span-2">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-background text-foreground shadow-sm">{wide.icon}</div>
        <div className="min-w-0">
          <p className="text-sm leading-none text-foreground">{wide.value}</p>
          <p className="mt-1 text-xs font-semibold text-muted-foreground">{wide.label}</p>
        </div>
      </div>
    </div>
  );
}

export default StatsBento;
