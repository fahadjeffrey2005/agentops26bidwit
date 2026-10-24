"use client";

/* BidWit dashboard: the layout, tiles and motion of the "web3-bento" component,
   re-mapped to one tender run. Tile mapping (original -> BidWit):
     Hero + PnL strip     -> greeting + requirements accounted for, one bar per requirement
     Card stack           -> evidence vault (cited vs blocked documents)
     Gas gauge            -> Judge verdict (no-go / conditional / go)
     Portfolio chart      -> compliance matrix (filterable)
     Allocation bar       -> requirement status split
     Staking accent tile  -> Gate B: your review + deadline countdown
     Liquidity range      -> LLM call budget
     Block stream         -> agent pipeline
     Onchain activity     -> audit trail                                          */

import * as React from "react";
import { Ban, Check, Flag, RefreshCw, ShieldAlert, Scale } from "lucide-react";
import type { AuditItem, ReqRow, ReqStatus, VaultDoc } from "@/data/adapter-types";

const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

function useReducedMotion() {
  const [r, setR] = React.useState(false);
  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const u = () => setR(mq.matches);
    u();
    mq.addEventListener("change", u);
    return () => mq.removeEventListener("change", u);
  }, []);
  return r;
}

function useMounted() {
  const [on, setOn] = React.useState(false);
  React.useEffect(() => {
    const id = requestAnimationFrame(() => setOn(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return on;
}

function useCountUp(target: number, enabled: boolean, duration = 1300) {
  const [v, setV] = React.useState(enabled ? 0 : target);
  React.useEffect(() => {
    if (!enabled) return setV(target);
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      setV(target * (1 - Math.pow(1 - p, 4)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, enabled, duration]);
  return v;
}

/* ------------------------------------------------------------------ */
/*  Shell                                                              */
/* ------------------------------------------------------------------ */

export function Tile({ title, action, className, children }: { title?: React.ReactNode; action?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={cx("relative flex min-w-0 flex-col overflow-hidden rounded-[26px] border border-border bg-card p-5 text-card-foreground", className)}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h3 className="text-[13px] font-medium text-muted-foreground">{title}</h3>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Pills<T extends string>({ value, options, onChange, label }: { value: T; options: T[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full border border-border p-0.5">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          role="radio"
          aria-checked={o === value}
          onClick={() => onChange(o)}
          className={cx(
            "rounded-full px-2.5 py-1 font-mono text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            o === value ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

export interface Palette {
  accent: string; // cited / done
  accent2: string; // needs you
  muted: string; // human decides
  warn: string; // flagged
}

const STATUS_LABEL: Record<ReqStatus, string> = {
  cited: "Cited",
  needs_input: "Needs input",
  human: "You decide",
  flagged: "Flagged",
  pending: "Pending",
};

function statusColor(s: ReqStatus, p: Palette) {
  return s === "cited" ? p.accent : s === "needs_input" ? p.accent2 : s === "flagged" ? p.warn : p.muted;
}

/* ------------------------------------------------------------------ */
/*  Hero: greeting, requirements accounted for, one bar per requirement */
/* ------------------------------------------------------------------ */

function HeroTile({ user, tender, reqs, silentMisses, p, reduced }: { user: string; tender: { title: string; issuer: string; number: string }; reqs: ReqRow[]; silentMisses: number; p: Palette; reduced: boolean }) {
  const mounted = useMounted();
  const accounted = reqs.length - silentMisses;
  const shown = useCountUp(accounted, !reduced, 1100);
  const cited = reqs.filter((r) => r.status === "cited").length;
  const maxScore = Math.max(...reqs.map((r) => r.score), 1);
  const [hover, setHover] = React.useState<number | null>(null);

  return (
    <Tile className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-start-1">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0">
          <p className="text-[28px] font-semibold leading-[1.1] tracking-[-0.03em] sm:text-[34px]">
            Hi, <span style={{ color: p.accent }}>{user}</span>
          </p>
          <p className="mt-1 text-sm text-muted-foreground">{tender.title}</p>
          <p className="font-mono text-[11px] text-muted-foreground">
            {tender.issuer} · {tender.number}
          </p>
        </div>
        <div>
          <p className="text-[12px] text-muted-foreground">Requirements accounted for</p>
          <p className="font-mono text-[34px] font-semibold leading-none tracking-[-0.04em] tabular-nums sm:text-[40px]">
            {Math.round(shown)}
            <span className="text-muted-foreground">/{reqs.length}</span>
          </p>
          <p className="mt-1.5 font-mono text-[12px] tabular-nums">
            <span style={{ color: p.accent }}>{cited} cited</span>
            <span className="text-muted-foreground"> · {reqs.length - cited} flagged to you · </span>
            <span style={{ color: silentMisses === 0 ? p.accent : p.warn }}>{silentMisses} silent misses</span>
          </p>
        </div>
      </div>

      {/* one bar per requirement: height = evidence strength, colour = status */}
      <div className="mt-6 flex flex-1 flex-col">
        <div className="flex flex-1 items-end gap-[5px]" style={{ minHeight: 64 }} onPointerLeave={() => setHover(null)}>
          {reqs.map((r, i) => {
            const h = r.status === "cited" ? 30 + (r.score / maxScore) * 70 : 22;
            return (
              <button
                key={r.id}
                type="button"
                onPointerEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                aria-label={`${r.id}: ${STATUS_LABEL[r.status]}`}
                className="relative flex-1 rounded-[5px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                style={{
                  height: mounted ? `${h}%` : "6%",
                  background: statusColor(r.status, p),
                  opacity: hover === null ? (r.status === "cited" ? 0.95 : 0.75) : hover === i ? 1 : 0.25,
                  transition: `height 900ms ${EASE} ${i * 30}ms, opacity 200ms ease`,
                }}
              />
            );
          })}
        </div>
        <div className="mt-2 flex items-center justify-between gap-3 font-mono text-[11px] text-muted-foreground">
          <span>{reqs[0]?.id}</span>
          <span className="truncate text-foreground" aria-live="polite">
            {hover !== null
              ? `${reqs[hover].id} · ${STATUS_LABEL[reqs[hover].status]}${reqs[hover].evidence[0] ? ` · ${reqs[hover].evidence[0]} · score ${reqs[hover].score.toFixed(1)}` : ""}`
              : "Bar height = evidence strength"}
          </span>
          <span>{reqs[reqs.length - 1]?.id}</span>
        </div>
      </div>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Evidence vault: fanned stack, click a card to bring it forward     */
/* ------------------------------------------------------------------ */

function DocFace({ c, glare }: { c: VaultDoc; glare: number }) {
  return (
    <>
      <span
        aria-hidden
        className="absolute inset-0 overflow-hidden rounded-[12px]"
        style={{
          backgroundImage: [
            "linear-gradient(180deg, oklch(1 0 0 / 0.3) 0%, transparent 34%)",
            `radial-gradient(110% 90% at 100% 0%, ${c.color2} 0%, transparent 60%)`,
            `linear-gradient(135deg, ${c.color} 0%, ${c.color2} 100%)`,
          ].join(", "),
          boxShadow: "inset 0 1px 0 oklch(1 0 0 / 0.5), inset 0 0 0 1px oklch(1 0 0 / 0.16)",
        }}
      >
        <span
          className="absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(115deg, transparent 18%, oklch(1 0 0 / 0.25) 32%, oklch(1 0 0 / 0.4) 45%, oklch(1 0 0 / 0.25) 58%, oklch(1 0 0 / 0.1) 66%, transparent 78%)",
            backgroundSize: "260% 100%",
            backgroundPosition: `${glare}% 0`,
            mixBlendMode: "soft-light",
            transition: "background-position 700ms cubic-bezier(0.22, 1, 0.36, 1)",
          }}
        />
      </span>
      <span className="relative flex items-center justify-between gap-3 px-4 pt-4">
        <span className="truncate text-[13px] font-bold tracking-tight">{c.title}</span>
        <span className="shrink-0 font-mono text-[12px] font-semibold tabular-nums">{c.id}</span>
      </span>
      <span className="relative mt-1 block px-4 font-mono text-[10px] opacity-75">{c.meta}</span>
      {c.state === "blocked" && (
        <span
          className="absolute bottom-3 right-4 rounded-md border-2 px-2 py-0.5 font-mono text-[11px] font-bold tracking-[0.12em]"
          style={{ borderColor: "currentColor", transform: "rotate(-6deg)" }}
        >
          BLOCKED
        </span>
      )}
      {c.state === "cited" && (
        <span className="absolute bottom-3.5 right-4 flex items-center gap-1 font-mono text-[11px] font-semibold opacity-80">
          <Check size={13} strokeWidth={2.6} /> CITED
        </span>
      )}
    </>
  );
}

function VaultTile(props: { docs: VaultDoc[]; reduced: boolean; p: Palette }) {
  if (!props.docs.length)
    return (
      <Tile title="Evidence vault" className="lg:col-start-3 lg:row-start-1">
        <p className="text-[13px] text-muted-foreground">Cited and blocked evidence appears here once a run searches the library.</p>
      </Tile>
    );
  return <VaultStack key={props.docs.map((d) => d.id).join()} {...props} />;
}

function VaultStack({ docs, reduced, p }: { docs: VaultDoc[]; reduced: boolean; p: Palette }) {
  const [order, setOrder] = React.useState(() => docs.map((c) => c.id));
  const mounted = useMounted();
  const PEEK = 46;
  const depth = order.length - 1;
  const front = docs.find((c) => c.id === order[order.length - 1])!;
  const dragGlare = React.useRef(false);
  const [glare, setGlare] = React.useState(30);
  React.useEffect(() => {
    if (reduced) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      setGlare((g) => (dragGlare.current ? g : 30 + Math.sin((now - t0) / 2600) * 30));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [reduced]);
  const blocked = docs.filter((d) => d.state === "blocked").length;

  return (
    <Tile
      title={
        <span>
          Evidence vault <sup className="font-mono text-[10px]">{docs.length}</sup>
        </span>
      }
      action={<span className="font-mono text-[11px]" style={{ color: p.accent2 }}>{blocked} blocked</span>}
      className="lg:col-start-3 lg:row-start-1"
    >
      <div
        className="relative -mx-5 -mb-5 flex flex-1 flex-col justify-end overflow-hidden pt-1"
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          dragGlare.current = true;
          setGlare(((e.clientX - r.left) / r.width) * 100);
        }}
        onPointerLeave={() => (dragGlare.current = false)}
      >
        <div className="relative">
          {order.map((id, pos) => {
            const c = docs.find((x) => x.id === id)!;
            const fromFront = order.length - 1 - pos;
            const isFront = fromFront === 0;
            return (
              <button
                key={id}
                type="button"
                onClick={() => !isFront && setOrder((o) => [...o.filter((x) => x !== id), id])}
                aria-label={`${c.id} ${c.title}${isFront ? ", selected" : ", bring to front"}`}
                aria-pressed={isFront}
                className="group absolute left-1/2 block w-[calc(100%-32px)] max-w-[300px] rounded-[12px] p-0 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                style={{
                  top: (depth - fromFront) * PEEK,
                  zIndex: pos + 1,
                  transform: `translateX(-50%) scale(${1 - fromFront * 0.055}) translateY(${mounted ? 0 : 20}px)`,
                  transformOrigin: "top center",
                  opacity: mounted ? 1 : 0,
                  color: c.ink,
                  boxShadow: "0 -10px 28px -14px oklch(0 0 0 / 0.75)",
                  transition: reduced
                    ? "none"
                    : `top 650ms cubic-bezier(0.34, 1.35, 0.64, 1), transform 650ms cubic-bezier(0.34, 1.35, 0.64, 1), opacity 500ms ease ${pos * 90}ms`,
                  cursor: isFront ? "default" : "pointer",
                }}
              >
                <span className="relative block w-full" style={{ paddingTop: "63.08%" }}>
                  <span className="absolute inset-0 block">
                    <DocFace c={c} glare={glare + fromFront * 18} />
                  </span>
                </span>
              </button>
            );
          })}
          <div aria-hidden className="invisible mx-auto w-[calc(100%-32px)] max-w-[300px] shrink-0" style={{ marginTop: depth * PEEK }}>
            <div style={{ paddingTop: "30%" }} />
          </div>
        </div>

        <div
          className="relative z-10 flex shrink-0 items-end justify-between gap-3 px-5 pb-4"
          style={{
            minHeight: 88,
            background: "color-mix(in oklch, var(--card) 94%, transparent)",
            backdropFilter: "blur(18px) saturate(1.3)",
            WebkitBackdropFilter: "blur(18px) saturate(1.3)",
            borderTop: "1px solid color-mix(in oklch, var(--foreground) 10%, transparent)",
          }}
          aria-live="polite"
        >
          <div className="min-w-0 pt-3">
            <p className="truncate font-mono text-[14px] font-semibold tracking-[0.04em]">
              {front.id} · {front.title}
            </p>
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{front.why}</p>
          </div>
        </div>
      </div>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Judge: semicircle gauge                                            */
/* ------------------------------------------------------------------ */

function JudgeTile({ decision, reasons, p }: { decision: "go" | "conditional" | "no_go"; reasons: { requirement_id: string; reason: string }[]; p: Palette }) {
  const mounted = useMounted();
  const t = { no_go: 0.14, conditional: 0.5, go: 0.86 }[decision];
  const R = 62;
  const len = Math.PI * R;
  const angle = -90 + (mounted ? t : 0) * 180;
  const label = { no_go: "No-go", conditional: "Conditional", go: "Go" }[decision];
  const color = decision === "go" ? p.accent : decision === "conditional" ? p.accent2 : p.warn;
  const blockers = reasons; // every reason passed in is a blocking pass/fail gap

  return (
    <Tile title="Judge" className="lg:col-start-4 lg:row-start-1" action={<span className="font-mono text-[11px] text-muted-foreground">you can override</span>}>
      <div className="flex flex-1 flex-col items-center justify-center">
        <div className="relative" style={{ width: 150, height: 86 }}>
          <svg width="150" height="86" viewBox="0 0 150 86" aria-hidden>
            <path d="M 13 78 A 62 62 0 0 1 137 78" fill="none" strokeWidth="10" strokeLinecap="round" style={{ stroke: "var(--muted)" }} />
            <path
              d="M 13 78 A 62 62 0 0 1 137 78"
              fill="none"
              strokeWidth="10"
              strokeLinecap="round"
              strokeDasharray={len}
              style={{ stroke: color, strokeDashoffset: len * (1 - (mounted ? t : 0)), transition: `stroke-dashoffset 1100ms ${EASE}` }}
            />
            <g style={{ transform: `rotate(${angle}deg)`, transformOrigin: "75px 78px", transition: `transform 1100ms ${EASE}` }}>
              <line x1="75" y1="78" x2="75" y2="30" strokeWidth="2.5" strokeLinecap="round" style={{ stroke: "var(--foreground)" }} />
            </g>
            <circle cx="75" cy="78" r="5" style={{ fill: "var(--foreground)" }} />
          </svg>
        </div>
        <p className="mt-2 text-[24px] font-semibold leading-none tracking-[-0.02em]" style={{ color }}>
          {label}
        </p>
        <p className="mt-1.5 font-mono text-[11px] tabular-nums text-muted-foreground">
          {blockers.length} mandatory gap{blockers.length === 1 ? "" : "s"}
          {blockers.length ? `: ${blockers.map((b) => b.requirement_id).join(", ")}` : ""}
        </p>
      </div>
      <div className="mt-4 flex justify-between font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>No-go</span>
        <span>Conditional</span>
        <span>Go</span>
      </div>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Compliance matrix                                                  */
/* ------------------------------------------------------------------ */

type Filter = "All" | "Needs you" | "Must";

function MatrixTile({ reqs, p }: { reqs: ReqRow[]; p: Palette }) {
  const [filter, setFilter] = React.useState<Filter>("All");
  const [open, setOpen] = React.useState<string | null>(null);
  const mounted = useMounted();
  const rows = reqs.filter((r) => (filter === "All" ? true : filter === "Must" ? r.mandatory : r.status !== "cited"));

  return (
    <Tile
      title="Compliance matrix"
      className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-span-2 lg:row-start-2"
      action={<Pills label="Filter" value={filter} options={["All", "Needs you", "Must"]} onChange={setFilter} />}
    >
      <div className="grid grid-cols-[52px_1fr_auto] gap-x-3 border-b border-border pb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>ID</span>
        <span>Requirement</span>
        <span className="text-right">Status · evidence</span>
      </div>
      <ul className="-mx-2 mt-1 max-h-[560px] flex-1 overflow-y-auto">
        {rows.map((r, i) => {
          const c = statusColor(r.status, p);
          const isOpen = open === r.id;
          return (
            <li key={r.id} style={{ opacity: mounted ? 1 : 0, transition: `opacity 400ms ease ${150 + i * 35}ms` }}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : r.id)}
                aria-expanded={isOpen}
                className="grid w-full grid-cols-[52px_1fr_auto] items-center gap-x-3 rounded-xl px-2 py-[7px] text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="font-mono text-[12px] tabular-nums text-muted-foreground">{r.id}</span>
                <span className="flex min-w-0 items-center gap-2">
                  {r.mandatory && (
                    <span className="shrink-0 rounded-[5px] border border-border px-1 font-mono text-[9px] font-semibold text-muted-foreground">MUST</span>
                  )}
                  <span className={cx("text-[13px]", isOpen ? "whitespace-normal" : "truncate")}>{r.text}</span>
                </span>
                <span className="flex items-center justify-end gap-2">
                  {r.evidence[0] && <span className="font-mono text-[11px] tabular-nums text-muted-foreground">{r.evidence[0]}</span>}
                  <span
                    className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold"
                    style={{ background: `color-mix(in oklch, ${c} 18%, transparent)`, color: c }}
                  >
                    {STATUS_LABEL[r.status]}
                  </span>
                </span>
              </button>
              {isOpen && (
                <p className="mb-1 ml-[64px] mr-2 rounded-xl bg-muted/50 px-3 py-2 font-mono text-[11px] text-muted-foreground">
                  p.{r.page ?? "?"} · {r.category} · {r.note || "no note"}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Status split: segmented bar                                        */
/* ------------------------------------------------------------------ */

function SplitTile({ reqs, p }: { reqs: ReqRow[]; p: Palette }) {
  const mounted = useMounted();
  const parts: { key: ReqStatus; n: number }[] = (["cited", "needs_input", "human", "flagged", "pending"] as ReqStatus[])
    .map((k) => ({ key: k, n: reqs.filter((r) => r.status === k).length }))
    .filter((x) => x.n > 0);
  const total = reqs.length;
  const [hover, setHover] = React.useState<number | null>(null);

  return (
    <Tile title="Where every requirement ended up" className="lg:col-start-3 lg:row-start-2">
      <p className="font-mono text-[22px] font-semibold tabular-nums">
        {total} <span className="text-[13px] text-muted-foreground">requirements</span>
      </p>
      <div className="mt-4 flex h-9 gap-1" onPointerLeave={() => setHover(null)}>
        {parts.map((a, i) => (
          <span
            key={a.key}
            onPointerEnter={() => setHover(i)}
            className="rounded-[8px]"
            style={{
              flexBasis: mounted ? `${(a.n / total) * 100}%` : `${100 / parts.length}%`,
              background: statusColor(a.key, p),
              opacity: hover === null || hover === i ? 1 : 0.3,
              transition: `flex-basis 1000ms ${EASE} ${200 + i * 60}ms, opacity 200ms ease`,
            }}
            aria-hidden
          />
        ))}
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2">
        {parts.map((a, i) => (
          <li key={a.key} className="flex items-center justify-between gap-2 text-[12px]" onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
            <span className="flex items-center gap-2">
              <span className="size-2 rounded-full" style={{ background: statusColor(a.key, p) }} aria-hidden />
              {STATUS_LABEL[a.key]}
            </span>
            <span className="font-mono tabular-nums text-muted-foreground">{a.n}</span>
          </li>
        ))}
      </ul>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Gate B: solid accent tile                                          */
/* ------------------------------------------------------------------ */

function GateBTile({ queueBy, queueTotal, deadline, rounds, p }: { queueBy: Record<string, number>; queueTotal: number; deadline: string; rounds: { round: number; passed: number; total: number }[]; p: Palette }) {
  const ink = "oklch(0.145 0 0)";
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const left = deadline ? Math.max(0, new Date(deadline).getTime() - now) : 0;
  const d = Math.floor(left / 864e5);
  const h = Math.floor((left % 864e5) / 36e5);
  const m = Math.floor((left % 36e5) / 6e4);
  const s = Math.floor((left % 6e4) / 1e3);
  const [reviewed] = React.useState(0);
  const rows: [string, number][] = [
    ["Failed checks", queueBy["failed_check"] ?? 0],
    ["Blocking gaps", queueBy["blocking_gap"] ?? 0],
    ["Other gaps", queueBy["gap"] ?? 0],
    ["Drafted answers", (queueBy["pass_fail"] ?? 0) + (queueBy["answer"] ?? 0)],
    ["One-click groups", (queueBy["human_task"] ?? 0) + (queueBy["compliance"] ?? 0)],
  ];

  return (
    <section className="relative flex min-w-0 flex-col overflow-hidden rounded-[26px] p-5 lg:col-start-4 lg:row-span-2 lg:row-start-2" style={{ background: p.accent, color: ink }}>
      <header className="flex items-center justify-between">
        <h3 className="text-[13px] font-semibold opacity-75">Gate B · your review</h3>
        <span className="flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold" style={{ background: "oklch(0.145 0 0 / 0.12)" }}>
          <span className="size-1.5 animate-pulse rounded-full motion-reduce:animate-none" style={{ background: ink }} aria-hidden />
          {queueTotal ? "Paused" : "Not yet"}
        </span>
      </header>

      <p className="mt-5 font-mono text-[52px] font-semibold leading-none tracking-[-0.05em] tabular-nums">{queueTotal}</p>
      <p className="mt-1 text-[12px] font-medium opacity-70">items need your decision, risk first</p>

      <div className="mt-5 rounded-2xl p-3" style={{ background: "oklch(0.145 0 0 / 0.1)" }}>
        <div className="flex items-baseline justify-between text-[12px] font-semibold">
          <span className="opacity-70">Closes in</span>
          <span className="font-mono tabular-nums">
            {deadline ? `${d}d ${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s` : "no deadline set"}
          </span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full" style={{ background: "oklch(0.145 0 0 / 0.14)" }}>
          <div className="h-full rounded-full" style={{ width: `${(reviewed / queueTotal) * 100 || 2}%`, background: ink }} />
        </div>
        <p className="mt-1.5 font-mono text-[10px] opacity-60">
          Reviewed {reviewed}/{queueTotal}
        </p>
      </div>

      <dl className="mt-3 space-y-1.5 text-[12px]">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between">
            <dt className="opacity-70">{k}</dt>
            <dd className="font-mono font-semibold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-auto pt-6">
        <p className="text-[12px] font-semibold opacity-70">Checker, per round</p>
        <div className="mt-2 flex h-12 items-end gap-2" aria-hidden>
          {rounds.map((r) => (
            <span key={r.round} className="flex-1 rounded-[4px]" style={{ height: `${(r.passed / r.total) * 100}%`, background: ink, opacity: r.passed === r.total ? 0.85 : 0.35 }} />
          ))}
        </div>
        <div className="mt-1.5 flex gap-2 font-mono text-[10px] opacity-70">
          {rounds.map((r) => (
            <span key={r.round} className="flex-1">
              R{r.round} · {r.passed}/{r.total}
            </span>
          ))}
        </div>

        <button
          type="button"
          disabled={!queueTotal}
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="mt-4 w-full rounded-2xl py-3 text-sm font-semibold transition-transform active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-50"
          style={{ background: ink, color: p.accent }}
        >
          {queueTotal ? "Review above" : "Opens after drafting"}
        </button>
        <p className="mt-2 text-center font-mono text-[10px] opacity-60">Risky items one by one; groups in one click.</p>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  LLM budget: range tile                                             */
/* ------------------------------------------------------------------ */

function BudgetTile({ used, budget, p }: { used: number; budget: number; p: Palette }) {
  const mounted = useMounted();
  const pos = (v: number) => (v / (budget * 1.25)) * 100;
  const inBudget = used <= budget;
  return (
    <Tile
      title="LLM calls · this run"
      className="lg:col-start-3 lg:row-start-3"
      action={
        <span
          className="rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold"
          style={{ background: `color-mix(in oklch, ${inBudget ? p.accent : p.warn} 18%, transparent)`, color: inBudget ? p.accent : p.warn }}
        >
          {inBudget ? "Within budget" : "Over budget"}
        </span>
      }
    >
      <p className="font-mono text-[22px] font-semibold tabular-nums">
        {used} <span className="text-[13px] text-muted-foreground">of {budget}</span>
      </p>
      <p className="font-mono text-[11px] text-muted-foreground">hard cap, run stops if hit</p>

      <div className="relative mt-6 h-10" role="img" aria-label={`${used} of ${budget} calls used`}>
        <div className="absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 rounded-full bg-muted" />
        <div
          className="absolute top-1/2 h-10 -translate-y-1/2 rounded-[10px]"
          style={{
            left: 0,
            width: `${pos(budget)}%`,
            background: `repeating-linear-gradient(135deg, color-mix(in oklch, ${p.accent} 26%, transparent) 0 6px, color-mix(in oklch, ${p.accent} 12%, transparent) 6px 12px)`,
            boxShadow: `inset 0 0 0 1px color-mix(in oklch, ${p.accent} 55%, transparent)`,
          }}
        />
        <div
          className="absolute top-1/2 h-14 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground"
          style={{ left: `${mounted ? Math.max(2, pos(used)) : 0}%`, transition: `left 900ms ${EASE}` }}
        />
      </div>
      <div className="mt-2 flex justify-between font-mono text-[11px] tabular-nums text-muted-foreground">
        <span>0</span>
        <span style={{ marginRight: `${100 - pos(budget) - 3}%` }}>{budget}</span>
      </div>
      <p className="mt-auto pt-4 text-[12px] text-muted-foreground">
        Rest of the work is <span className="font-semibold text-foreground">code, not AI</span>
      </p>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Agent pipeline                                                     */
/* ------------------------------------------------------------------ */

function PipelineTile({ stages, at, llmUsed, rounds, p, reduced }: { stages: readonly { key: string; label: string; detail: string }[]; at: number; llmUsed: number; rounds: { round: number; passed: number; total: number }[]; p: Palette; reduced: boolean }) {
  const mounted = useMounted();
  const [hover, setHover] = React.useState<number | null>(null);
  const last = rounds[rounds.length - 1];
  return (
    <Tile
      title="Agent pipeline"
      className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-start-4"
      action={<span className="font-mono text-[11px]" style={{ color: p.accent }}>waiting for you at {stages[at].label}</span>}
    >
      <div className="flex flex-1 items-end gap-[5px]" style={{ minHeight: 84 }} onPointerLeave={() => setHover(null)}>
        {stages.map((s, i) => {
          const done = i < at;
          const cur = i === at;
          const gate = s.key.startsWith("gate");
          const h = gate ? 100 : 55; // gates (human stops) stand taller than agent steps
          return (
            <button
              key={s.key}
              type="button"
              aria-label={`${s.label}${s.detail ? `: ${s.detail}` : ""}`}
              onPointerEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              className="flex h-full flex-1 flex-col justify-end rounded-[4px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span
                className="block rounded-[4px]"
                style={{
                  height: mounted ? `${h}%` : "4%",
                  background: cur ? p.accent : gate ? p.accent2 : "var(--muted-foreground)",
                  opacity: hover === i ? 1 : cur ? 1 : done ? (gate ? 0.7 : 0.35) : 0.1,
                  transition: `height 800ms ${EASE} ${i * 50}ms`,
                  animation: cur && !reduced ? "bw-pulse 1.8s ease-in-out infinite" : undefined,
                }}
              />
            </button>
          );
        })}
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 font-mono text-[11px] text-muted-foreground">
        <span>{stages[0].label}</span>
        <span className="truncate text-foreground" aria-live="polite">
          {`${String((hover ?? at) + 1).padStart(2, "0")} · ${stages[hover ?? at].label}${stages[hover ?? at].detail ? ` · ${stages[hover ?? at].detail}` : ""}`}
        </span>
        <span>{stages[stages.length - 1].label}</span>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3">
        {[
          ["LLM calls", String(llmUsed)],
          ["Rewrite rounds", String(Math.max(0, rounds.length - 1))],
          ["Checks passed", last ? `${last.passed}/${last.total}` : "-"],
        ].map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-[11px] text-muted-foreground">{k}</dt>
            <dd className="mt-0.5 font-mono text-[13px] font-semibold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Audit trail                                                        */
/* ------------------------------------------------------------------ */

function KindIcon({ kind }: { kind: AuditItem["kind"] }) {
  const s = { size: 16, strokeWidth: 1.9, "aria-hidden": true } as const;
  if (kind === "blocked") return <Ban {...s} />;
  if (kind === "flagged") return <Flag {...s} />;
  if (kind === "fail") return <ShieldAlert {...s} />;
  if (kind === "fixed") return <RefreshCw {...s} />;
  if (kind === "decision") return <Scale {...s} />;
  return <Check {...s} />;
}

function AuditTile({ items, p }: { items: AuditItem[]; p: Palette }) {
  const mounted = useMounted();
  const color = (st: string) => (st === "blocked" || st === "flagged" ? p.accent2 : st === "fixed" || st === "approved" ? p.accent : "var(--muted-foreground)");
  return (
    <Tile title="Audit trail" className="sm:col-span-2 lg:col-span-2 lg:col-start-3 lg:row-start-4" action={<span className="font-mono text-[11px] text-muted-foreground">audit.json</span>}>
      <ul className="-mx-2 -my-1">
        {items.slice(0, 5).map((a, i) => (
          <li
            key={a.id}
            className="flex items-center gap-3 rounded-2xl px-2 py-1.5 transition-colors hover:bg-muted/50"
            style={{ opacity: mounted ? 1 : 0, transform: mounted ? "none" : "translateY(6px)", transition: `opacity 500ms ease ${300 + i * 70}ms, transform 500ms ${EASE} ${300 + i * 70}ms` }}
          >
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted text-foreground">
              <KindIcon kind={a.kind} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium">{a.title}</p>
              <p className="truncate text-[11px] text-muted-foreground">{a.detail}</p>
            </div>
            <div className="text-right">
              <p className="font-mono text-[11px] tabular-nums text-muted-foreground">step {a.step}</p>
              <p className="mt-0.5 font-mono text-[10px] font-semibold" style={{ color: color(a.status) }}>
                {a.status}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Dashboard                                                          */
/* ------------------------------------------------------------------ */

export interface BidWitBentoProps {
  user: string;
  org: string;
  domain: string;
  tender: { title: string; issuer: string; number: string };
  requirements: ReqRow[];
  silentMisses: number;
  verdict: { decision: "go" | "conditional" | "no_go"; summary: string; reasons: { requirement_id: string; reason: string }[] };
  vault: VaultDoc[];
  queueBy: Record<string, number>;
  queueTotal: number;
  deadline: string;
  rounds: { round: number; passed: number; total: number }[];
  llm: { used: number; budget: number };
  pipeline: readonly { key: string; label: string; detail: string }[];
  pipelineAt: number;
  audit: AuditItem[];
  palette?: Partial<Palette>;
  className?: string;
  top?: React.ReactNode; // full-width tile above the grid (live run, gates)
  hideGrid?: boolean;
  verdictPending?: boolean;
  navExtra?: React.ReactNode;
}

export function BidWitBento(props: BidWitBentoProps) {
  const reduced = useReducedMotion();
  const p: Palette = {
    accent: "oklch(0.97 0 0)",
    accent2: "oklch(0.72 0 0)",
    muted: "oklch(0.55 0 0)",
    warn: "oklch(0.68 0.15 25)",
    ...props.palette,
  };

  return (
    <div className={cx("w-full max-w-[1120px]", props.className)}>
      <style>{`@keyframes bw-pulse { 0%,100% { opacity: 1 } 50% { opacity: .55 } }`}</style>

      <nav className="mb-3 flex flex-wrap items-center justify-between gap-3 px-1" aria-label="Dashboard">
        <span className="flex items-center gap-2 text-[15px] font-semibold tracking-[-0.02em]">
          <span className="grid size-6 place-items-center rounded-lg font-mono text-[12px] font-bold" style={{ background: p.accent, color: "oklch(0.145 0 0)" }}>
            B
          </span>
          BidWit
        </span>
        <div className="flex items-center gap-2">
          {props.navExtra}
          <span className="flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-[12px] font-medium">
            <span className="size-2 rounded-full" style={{ background: p.accent }} aria-hidden />
            {props.domain}
          </span>
          <span className="rounded-full bg-foreground px-3 py-1.5 font-mono text-[12px] font-semibold text-background">{props.org}</span>
        </div>
      </nav>

      {props.top && <div className="mb-3">{props.top}</div>}
      {!props.hideGrid && <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <HeroTile user={props.user} tender={props.tender} reqs={props.requirements} silentMisses={props.silentMisses} p={p} reduced={reduced} />
        <VaultTile docs={props.vault} reduced={reduced} p={p} />
        {props.verdictPending ? (
          <Tile title="Judge" className="lg:col-start-4 lg:row-start-1">
            <p className="text-[13px] text-muted-foreground">Bid / no-bid is decided in code after the evidence search.</p>
          </Tile>
        ) : (
          <JudgeTile decision={props.verdict.decision} reasons={props.verdict.reasons} p={p} />
        )}
        <MatrixTile reqs={props.requirements} p={p} />
        <SplitTile reqs={props.requirements} p={p} />
        <GateBTile queueBy={props.queueBy} queueTotal={props.queueTotal} deadline={props.deadline} rounds={props.rounds} p={p} />
        <BudgetTile used={props.llm.used} budget={props.llm.budget} p={p} />
        <PipelineTile stages={props.pipeline} at={props.pipelineAt} llmUsed={props.llm.used} rounds={props.rounds} p={p} reduced={reduced} />
        <AuditTile items={props.audit} p={p} />
      </div>}
    </div>
  );
}

export default BidWitBento;
