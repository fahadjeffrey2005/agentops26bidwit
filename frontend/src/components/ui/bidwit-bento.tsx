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
import { Field, Modal, Quote } from "./bidwit-modal";
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
  complied: "Standard reply",
  needs_input: "Needs input",
  human: "You decide",
  flagged: "Flagged",
  pending: "Pending",
};

function statusColor(s: ReqStatus, p: Palette) {
  return s === "cited" ? p.accent : s === "complied" ? p.accent2 : s === "needs_input" ? p.accent2 : s === "flagged" ? p.warn : p.muted;
}

/* ------------------------------------------------------------------ */
/*  Hero: greeting, requirements accounted for, one bar per requirement */
/* ------------------------------------------------------------------ */

function HeroTile({ tender, reqs, silentMisses, p, reduced }: { tender: { title: string; issuer: string; number: string }; reqs: ReqRow[]; silentMisses: number; p: Palette; reduced: boolean }) {
  const mounted = useMounted();
  const accounted = reqs.length - silentMisses;
  const shown = useCountUp(accounted, !reduced, 1100);
  const cited = reqs.filter((r) => r.status === "cited").length;
  const counts = {
    complied: reqs.filter((r) => r.status === "complied").length,
    human: reqs.filter((r) => r.status === "human").length,
    flagged: reqs.filter((r) => r.status === "flagged" || r.status === "needs_input").length,
  };

  return (
    <Tile className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-start-1">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0">
          <p className="truncate text-[22px] font-semibold leading-[1.15] tracking-[-0.02em] sm:text-[26px]">{tender.title}</p>
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">{tender.issuer}</p>
          <p className="font-mono text-[11px] text-muted-foreground">{tender.number}</p>
        </div>
        <div className="text-right">
          <p className="text-[12px] text-muted-foreground">Criteria accounted for</p>
          <p className="font-mono text-[34px] font-semibold leading-none tracking-[-0.04em] tabular-nums sm:text-[40px]">
            {Math.round(shown)}
            <span className="text-muted-foreground">/{reqs.length}</span>
          </p>
          <p className="mt-1 font-mono text-[11px] tabular-nums" style={{ color: silentMisses === 0 ? p.accent : p.warn }}>
            {silentMisses} silent misses
          </p>
        </div>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {([["Cited answers", cited, p.accent], ["Standard replies", counts.complied, p.accent2],
           ["For a person", counts.human, p.muted], ["Flagged gaps", counts.flagged, p.warn]] as [string, number, string][])
          .map(([label, nn, color]) => (
            <div key={label} className="rounded-2xl border border-border px-3 py-2">
              <dt className="text-[11px] text-muted-foreground">{label}</dt>
              <dd className="font-mono text-[20px] font-semibold tabular-nums" style={{ color }}>{nn}</dd>
            </div>
          ))}
      </dl>
      <div className="mt-5 flex flex-1 flex-col justify-end">
        <div className="flex h-3 w-full overflow-hidden rounded-full" role="img"
          aria-label={`${cited} cited, ${counts.complied} standard replies, ${counts.human} for a person, ${counts.flagged} flagged`}>
          {([[cited, p.accent], [counts.complied, p.accent2], [counts.human, p.muted], [counts.flagged, p.warn]] as [number, string][])
            .filter(([nn]) => nn > 0)
            .map(([nn, color], i) => (
              <span key={i} style={{ width: `${(nn / Math.max(reqs.length, 1)) * 100}%`, background: color,
                transition: `width 900ms ${EASE} ${i * 90}ms`, opacity: mounted ? 1 : 0 }} />
            ))}
        </div>
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
          {reqs.length} criteria · every one ends as an answer or a flagged gap · {tender.number}
        </p>
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
        <span className="line-clamp-2 text-[13px] font-bold leading-tight tracking-tight">{c.title}</span>
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
  const [detail, setDetail] = React.useState<VaultDoc | null>(null);
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
            background: "var(--card)",
            borderTop: "1px solid color-mix(in oklch, var(--foreground) 10%, transparent)",
          }}
          aria-live="polite"
        >
          <button type="button" onClick={() => setDetail(front)} className="min-w-0 pt-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <p className="line-clamp-2 font-mono text-[14px] font-semibold tracking-[0.04em]">
              {front.id} · {front.title}
            </p>
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{front.why}</p>
            <p className="mt-1 font-mono text-[10px] uppercase tracking-widest" style={{ color: p.accent }}>Open the record →</p>
          </button>
        </div>
      </div>
      <Modal open={!!detail} onClose={() => setDetail(null)} kicker={`Evidence ${detail?.id}`} title={detail?.full?.title ?? detail?.title ?? ""}
        footer={<span className="font-mono text-[11px] text-muted-foreground">{detail?.state === "blocked" ? "Blocked in code before any search" : "Quote verified in code against this text"}</span>}>
        {detail && (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Confidentiality">{detail.full?.confidentiality ?? "-"}</Field>
              <Field label="Client">{detail.full?.client ?? "none named"}</Field>
              <Field label="Dated">{detail.full?.date ?? "-"}{detail.full?.expires_on ? ` \u00b7 expires ${detail.full.expires_on}` : ""}</Field>
            </div>
            <Field label={detail.state === "blocked" ? "Why it is blocked" : "Why it is in the bid"}>{detail.why}</Field>
            <Field label="Full text">
              {detail.full?.text
                ? <Quote source={`${detail.id} \u00b7 ${detail.full.title}`}>{detail.full.text}</Quote>
                : <p className="text-muted-foreground">Restricted: the text is never loaded into the system, so there is nothing to show.</p>}
            </Field>
            {detail.full?.usedFor?.length ? (
              <Field label={`Cited for ${detail.full.usedFor.length} requirement(s)`}>
                <ul className="space-y-2">
                  {detail.full.usedFor.map((u) => (
                    <li key={u.id} className="rounded-xl border border-border p-3">
                      <p className="font-mono text-[11px] text-muted-foreground">{u.id}</p>
                      <p className="mt-0.5">{u.requirement}</p>
                      {u.quote && <p className="mt-1 text-muted-foreground">Quote used: \u201c{u.quote}\u201d</p>}
                    </li>
                  ))}
                </ul>
              </Field>
            ) : null}
          </>
        )}
      </Modal>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Judge: semicircle gauge                                            */
/* ------------------------------------------------------------------ */

function JudgeTile({ decision, reasons, total = 0, covered = 0, p }: { decision: "go" | "conditional" | "no_go"; reasons: { requirement_id: string; reason: string; fix?: string }[]; total?: number; covered?: number; p: Palette }) {
  const mounted = useMounted();
  const t = { no_go: 0.14, conditional: 0.5, go: 0.86 }[decision];
  const R = 62;
  const len = Math.PI * R;
  const angle = -90 + (mounted ? t : 0) * 180;
  const label = { no_go: "No-go", conditional: "Conditional", go: "Go" }[decision];
  const color = decision === "go" ? p.accent : decision === "conditional" ? p.accent2 : p.warn;
  const blockers = reasons; // every reason passed in is a blocking pass/fail gap
  const [open, setOpen] = React.useState(false);
  const [more, setMore] = React.useState(false);
  const verdictLine = {
    go: "Every must-meet rule is backed by company evidence. The bid can be submitted once a person signs it off.",
    conditional: "Most must-meet rules are backed by evidence, but a few are not. The bid is worth making only if those gaps are closed before the deadline.",
    no_go: "Too many must-meet rules have no evidence behind them. On these numbers the bid would be rejected at evaluation.",
  }[decision];

  return (
    <Tile title="Judge" className="lg:col-start-4 lg:row-start-1" action={<span className="font-mono text-[11px] text-muted-foreground">you can override</span>}>
      <button type="button" onClick={() => setOpen(true)} aria-label="Why this decision" className="flex flex-1 cursor-pointer flex-col items-center justify-center rounded-2xl transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
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
          {blockers.length} blocking gap{blockers.length === 1 ? "" : "s"}
          {blockers.length ? `: ${blockers.slice(0, 3).map((b) => b.requirement_id).join(", ")}` : ""}
        </p>
        <p className="mt-2 font-mono text-[10px] uppercase tracking-widest" style={{ color: p.accent }}>Why this decision →</p>
      </button>
      <div className="mt-4 flex justify-between font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>No-go</span>
        <span>Conditional</span>
        <span>Go</span>
      </div>
      <Modal open={open} onClose={() => { setOpen(false); setMore(false); }} kicker="Bid / no-bid decision" title={label}
        footer={<>
          {!more && <button type="button" onClick={() => setMore(true)} className="rounded-full border border-border px-4 py-2 text-[12px] font-semibold hover:bg-muted">More detail</button>}
          <span className="font-mono text-[11px] text-muted-foreground">Decided in code, not by the AI. You can override it.</span>
        </>}>
        <p className="text-[15px]">{verdictLine}</p>

        <div className="grid grid-cols-3 gap-2">
          {([["Must-meet criteria", total, "var(--foreground)"],
             ["Backed by evidence", covered, p.accent],
             ["Blocking gaps", blockers.length, blockers.length ? p.warn : p.accent]] as [string, number, string][])
            .map(([k, vv, c]) => (
              <div key={k} className="rounded-2xl border border-border px-3 py-2">
                <p className="text-[11px] text-muted-foreground">{k}</p>
                <p className="font-mono text-[22px] font-semibold tabular-nums" style={{ color: c }}>{vv}</p>
              </div>
            ))}
        </div>
        <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label={`${covered} of ${total} backed`}>
          <span style={{ width: `${(covered / Math.max(total, 1)) * 100}%`, background: p.accent }} />
          <span style={{ width: `${(blockers.length / Math.max(total, 1)) * 100}%`, background: p.warn }} />
        </div>

        <Field label={`Blocking gaps (${blockers.length})`}>
          {blockers.length === 0 ? <p className="text-muted-foreground">None.</p> : (
            <ul className="space-y-2">
              {(more ? blockers : blockers.slice(0, 3)).map((b) => (
                <li key={b.requirement_id} className="rounded-xl border border-border p-3">
                  <p className="font-mono text-[11px] text-muted-foreground">{b.requirement_id}</p>
                  <p className="mt-0.5">{b.reason}</p>
                  {b.fix && <p className="mt-1 text-[13px] text-muted-foreground"><span className="text-foreground">To close it:</span> {b.fix}</p>}
                </li>
              ))}
            </ul>
          )}
          {!more && blockers.length > 3 && <p className="mt-2 font-mono text-[11px] text-muted-foreground">+{blockers.length - 3} more</p>}
        </Field>
        <Field label="What happens next">
          <p className="text-muted-foreground">
            {decision === "no_go"
              ? "The run stops at the no-go gate. You either confirm it and no bid is made, or override it and the system drafts anyway."
              : decision === "conditional"
              ? "The system drafts the answers it can. Everything above goes to Gate B for you to decide before anything leaves."
              : "The system drafts every answer it can and sends them to Gate B for your review."}
          </p>
        </Field>
        {more && (
          <Field label="How the decision is made">
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>Only must-meet eligibility and technical criteria count. Prices, forms and scope duties do not.</li>
              <li>A criterion is backed when the evidence search finds company evidence that is strong enough and mentions every required term (a named standard, a certification, 24x7).</li>
              <li>0 unbacked criteria: GO. Up to 3: CONDITIONAL. More than 3: NO-GO, and the run stops for a person to decide.</li>
              <li>Restricted and expired evidence is removed before this count, so it can never prop up a decision.</li>
            </ul>
          </Field>
        )}
      </Modal>
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
  const card = reqs.find((r) => r.id === open) ?? null;

  return (
    <Tile
      title="Compliance matrix"
      className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-span-2 lg:row-start-3"
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
          return (
            <li key={r.id} style={{ opacity: mounted ? 1 : 0, transition: `opacity 400ms ease ${150 + i * 35}ms` }}>
              <button
                type="button"
                onClick={() => setOpen(r.id)}
                className="grid w-full grid-cols-[52px_1fr_auto] items-center gap-x-3 rounded-xl px-2 py-[7px] text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="font-mono text-[12px] tabular-nums text-muted-foreground">{r.id}</span>
                <span className="flex min-w-0 items-center gap-2">
                  {r.mandatory && (
                    <span className="shrink-0 rounded-[5px] border border-border px-1 font-mono text-[9px] font-semibold text-muted-foreground">MUST</span>
                  )}
                  <span className="truncate text-[13px]">{r.text}</span>
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
            </li>
          );
        })}
      </ul>
      <Modal open={!!card} onClose={() => setOpen(null)} kicker={`${card?.id ?? ""} \u00b7 page ${card?.page ?? "?"} \u00b7 ${card?.category ?? ""}`}
        title={`Requirement ${card?.id ?? ""}`}
        footer={<span className="font-mono text-[11px] text-muted-foreground">{card?.mandatory ? "Must-meet: the bid is rejected if this is not met" : "Scored or informational, not a must-meet rule"}</span>}>
        {card && (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Outcome"><span style={{ color: statusColor(card.status, p) }}>{STATUS_LABEL[card.status]}</span></Field>
              <Field label="Evidence strength">
                {card.status === "cited"
                  ? <span className="font-mono">{card.score.toFixed(2)} <span className="text-muted-foreground">(strong enough to cite)</span></span>
                  : <span className="text-muted-foreground">below the bar to cite</span>}
              </Field>
              <Field label="Category">{card.category}{card.mandatory ? " \u00b7 must-meet" : ""}</Field>
            </div>
            <Field label="Requirement text"><p className="leading-relaxed">{card.text}</p></Field>
            <Field label="What happened">{card.note || "no note"}</Field>
            {card.evidence.length > 0 && (
              <Field label="Evidence cited">
                <ul className="flex flex-wrap gap-2">
                  {card.evidence.map((e) => <li key={e} className="rounded-full border border-border px-3 py-1 font-mono text-[12px]">{e}</li>)}
                </ul>
              </Field>
            )}
            <Field label="How this was decided">
              <p className="text-muted-foreground">
                {card.status === "cited" ? "An answer was drafted from company evidence, then checked in code for the citation, the quote, every number and any overclaim."
                  : card.status === "complied" ? "No specific evidence was needed: this is a scope duty, answered with the standard compliance statement and confirmed as a group at Gate B."
                  : card.status === "human" ? "A price, a form or a signature: the system never decides these, a person does."
                  : card.status === "pending" ? "The run stopped before this one was drafted."
                  : "No company evidence was strong enough, or a required term was missing, so it is flagged rather than answered."}
              </p>
            </Field>
          </>
        )}
      </Modal>
    </Tile>
  );
}

/* ------------------------------------------------------------------ */
/*  Status split: segmented bar                                        */
/* ------------------------------------------------------------------ */

function SplitTile({ reqs, p }: { reqs: ReqRow[]; p: Palette }) {
  const mounted = useMounted();
  const parts: { key: ReqStatus; n: number }[] = (["cited", "complied", "needs_input", "human", "flagged", "pending"] as ReqStatus[])
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

const STAGE_WHAT: Record<string, string> = {
  extract: "Reads the PDF in a separate, sandboxed process: text, tables, hidden text, scanned pages. Nothing is filtered out.",
  classify: "Decides what each unit is: eligibility, technical, commercial, format, and whether it is a must-meet rule.",
  gate_a: "You confirm the must-meet checklist before any evidence is searched. The run waits here.",
  kb: "Searches the company's evidence library for each criterion. Restricted and expired records are removed first.",
  judge: "Counts must-meet criteria that have no evidence and calls it: go, conditional or no-go. Code only, no AI.",
  writer: "Drafts an answer only where the evidence is strong, citing ids and quoting the evidence word for word.",
  checker: "Verifies every answer in code: citation, quote, numbers, overclaim, blocked source, and coverage.",
  gate_b: "You review everything, riskiest first, before anything leaves the system. The run waits here.",
  package: "Writes the bid draft, the compliance matrix, the report and the audit trail.",
};

function PipelineTile({ stages, at, llmUsed, rounds, p, reduced }: { stages: readonly { key: string; label: string; detail: string }[]; at: number; llmUsed: number; rounds: { round: number; passed: number; total: number }[]; p: Palette; reduced: boolean }) {
  const mounted = useMounted();
  const [pick, setPick] = React.useState<number | null>(null);
  const last = rounds[rounds.length - 1];
  const sel = pick ?? at;
  return (
    <Tile
      title="Agent pipeline"
      className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-start-2"
      action={<span className="font-mono text-[11px]" style={{ color: p.accent }}>{at >= stages.length - 1 ? "finished" : `at ${stages[at].label}`}</span>}
    >
      <ol className="relative mt-1 space-y-0">
        {stages.map((s, i) => {
          const done = i < at;
          const cur = i === at;
          const gate = s.key.startsWith("gate");
          const on = i === sel;
          return (
            <li key={s.key} className="relative flex gap-3">
              <div className="flex w-5 shrink-0 flex-col items-center">
                <span
                  className="mt-[7px] block rounded-full transition-all"
                  style={{
                    width: gate ? 13 : 9, height: gate ? 13 : 9,
                    border: gate ? `2px solid ${cur ? p.accent : done ? "var(--foreground)" : "var(--muted-foreground)"}` : "none",
                    background: gate ? "var(--card)" : cur ? p.accent : done ? "var(--foreground)" : "var(--muted-foreground)",
                    opacity: done || cur ? 1 : 0.35,
                    animation: cur && !reduced ? "bw-pulse 1.8s ease-in-out infinite" : undefined,
                  }}
                />
                {i < stages.length - 1 && (
                  <span className="w-px flex-1" style={{ background: "var(--border)", minHeight: 18,
                    backgroundImage: done ? `linear-gradient(var(--foreground), var(--foreground))` : undefined,
                    opacity: mounted ? 1 : 0, transition: `opacity 500ms ease ${i * 60}ms` }} />
                )}
              </div>
              <button
                type="button"
                onClick={() => setPick(on ? null : i)}
                aria-expanded={on}
                className="mb-1 flex-1 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className="shrink-0 whitespace-nowrap text-[13px] font-medium" style={{ opacity: done || cur ? 1 : 0.5 }}>
                    {s.label}{gate && <span className="ml-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">you</span>}
                  </span>
                  <span className="truncate font-mono text-[11px] text-muted-foreground">{s.detail}</span>
                </span>
                {on && <span className="mt-1 block text-[12px] leading-relaxed text-muted-foreground">{STAGE_WHAT[s.key]}</span>}
              </button>
            </li>
          );
        })}
      </ol>
      <dl className="mt-3 grid grid-cols-3 gap-3 border-t border-border pt-3">
        {[
          ["AI calls", String(llmUsed)],
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
    <Tile title="Audit trail" className="sm:col-span-2 lg:col-span-2 lg:col-start-3 lg:row-start-4" action={<span className="font-mono text-[11px] text-muted-foreground">audit.jsonl</span>}>
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
  verdict: { decision: "go" | "conditional" | "no_go"; summary: string; total?: number; covered?: number; reasons: { requirement_id: string; reason: string; fix?: string }[] };
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
        <HeroTile tender={props.tender} reqs={props.requirements} silentMisses={props.silentMisses} p={p} reduced={reduced} />
        <VaultTile docs={props.vault} reduced={reduced} p={p} />
        {props.verdictPending ? (
          <Tile title="Judge" className="lg:col-start-4 lg:row-start-1">
            <p className="text-[13px] text-muted-foreground">Bid / no-bid is decided in code after the evidence search.</p>
          </Tile>
        ) : (
          <JudgeTile decision={props.verdict.decision} reasons={props.verdict.reasons} total={props.verdict.total} covered={props.verdict.covered} p={p} />
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
