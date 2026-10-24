/* Step 1 of a run: who is bidding.
   CompanyPicker sits under the landing hero. CompanyProfilePage is a page of its own: a dark header band,
   headline facts, then one section per kind of evidence (certificates, experience, people, policies, blocked). */
import * as React from "react";
import { ArrowLeft, ArrowRight, Ban, BadgeCheck, Briefcase, Building2, FileText, Plus, ShieldCheck, Users } from "lucide-react";
import { Tile, cx } from "./bidwit-bento";
import { Modal, Quote } from "./bidwit-modal";
import type { Company, CompanyProfile, ProfileDoc } from "@/data/api";

const INK = "oklch(0.145 0 0)";
const PAPER = "oklch(0.97 0 0)";
const WARN = "oklch(0.68 0.15 25)";

/* ------------------------------------------------------------------ picker */
export function CompanyPicker({ companies, onPick, onAdd }: { companies: Company[]; onPick: (id: string) => void; onAdd: () => void }) {
  return (
    <Tile title="Who is bidding?" action={<span className="font-mono text-[11px] text-muted-foreground">step 1 of 2</span>}>
      <p className="text-[14px] text-muted-foreground">
        BidWit answers a tender from one company’s evidence: its certificates, case studies, staff and policies.
        Pick the company first, then give it a tender.
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {companies.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => onPick(c.id)}
            className="group flex flex-col rounded-3xl border border-border p-5 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Building2 className="size-5 text-muted-foreground" />
            <p className="mt-3 text-[17px] font-semibold leading-tight">{c.name}</p>
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">{c.city} · since {c.founded}</p>
            <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">{c.blurb}</p>
            <dl className="mt-4 flex-1 space-y-1.5">
              {(c.facts ?? []).slice(0, 3).map((f) => (
                <div key={f.label} className="flex items-baseline justify-between gap-3 border-b border-border pb-1.5 last:border-0">
                  <dt className="text-[12px] text-muted-foreground">{f.label}</dt>
                  <dd className="font-mono text-[13px] font-semibold">{f.value}</dd>
                </div>
              ))}
            </dl>
            <span className="mt-4 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-widest">
              See what it can prove <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-1" />
            </span>
          </button>
        ))}
        <button
          type="button"
          onClick={onAdd}
          className="flex flex-col rounded-3xl border border-dashed border-border p-5 text-left opacity-70 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Plus className="size-5 text-muted-foreground" />
          <p className="mt-3 text-[17px] font-semibold leading-tight">Add an organisation</p>
          <p className="mt-3 flex-1 text-[13px] leading-relaxed text-muted-foreground">
            Upload your own certificates and case studies to build an evidence library.
          </p>
          <span className="mt-4 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">Not in this build</span>
        </button>
      </div>
    </Tile>
  );
}

/* ------------------------------------------------------------------ profile page */
const SECTIONS = [
  { kind: "certificate", title: "Certifications", icon: ShieldCheck, blurb: "Standards the company holds. An expired certificate can never back an answer." },
  { kind: "case study", title: "Experience", icon: Briefcase, blurb: "Past engagements. These answer scale and track-record criteria." },
  { kind: "people", title: "People", icon: Users, blurb: "Staff numbers and named profiles, for criteria about certified engineers." },
  { kind: "policy", title: "Policies and declarations", icon: FileText, blurb: "Blacklisting, penalties, staffing and security undertakings." },
] as const;

function statusChip(d: ProfileDoc) {
  if (d.blocked_reason === "restricted") return { text: "confidential", color: WARN };
  if (d.blocked_reason === "expired") return { text: `expired ${d.expires_on}`, color: WARN };
  if (d.expires_on) return { text: `valid to ${d.expires_on}`, color: "var(--muted-foreground)" };
  return { text: "citable", color: "var(--muted-foreground)" };
}

function DocCard({ d, onOpen }: { d: ProfileDoc; onOpen: () => void }) {
  const chip = statusChip(d);
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cx("flex h-full flex-col rounded-2xl border p-4 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        d.usable ? "border-border" : "opacity-70")}
      style={d.usable ? undefined : { borderColor: WARN }}
    >
      <span className="flex items-start justify-between gap-2">
        <span className="font-mono text-[11px] text-muted-foreground">{d.id}</span>
        <span className="shrink-0 rounded-full border border-border px-2 py-0.5 font-mono text-[10px]" style={{ color: chip.color, borderColor: d.usable ? undefined : WARN }}>{chip.text}</span>
      </span>
      <span className="mt-2 block text-[14px] font-semibold leading-snug">{d.title}</span>
      <span className="mt-1.5 block line-clamp-3 flex-1 text-[13px] leading-relaxed text-muted-foreground">
        {d.text ?? "Confidential: the text is never loaded into the system."}
      </span>
      {d.client && <span className="mt-2 font-mono text-[11px] text-muted-foreground">{d.client}</span>}
    </button>
  );
}

export function CompanyProfilePage({ profile, onBack, onContinue }: { profile: CompanyProfile; onBack: () => void; onContinue: () => void }) {
  const [doc, setDoc] = React.useState<ProfileDoc | null>(null);
  const c = profile.counts;
  const overview = profile.documents.filter((d) => d.kind === "company");
  const blocked = profile.documents.filter((d) => !d.usable);
  const first = profile.name.split(" ")[0];

  return (
    <div className="min-h-screen w-full bg-background">
      {/* header band, in the landing page's language */}
      <header className="relative overflow-hidden border-b border-border" style={{ background: PAPER, color: INK }}>
        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-25" style={{
          backgroundImage: "repeating-linear-gradient(45deg, #808080 0px 1px, transparent 1px 10px)",
          maskImage: "radial-gradient(ellipse 70% 60% at 100% 0%, #000 60%, transparent 110%)",
          WebkitMaskImage: "radial-gradient(ellipse 70% 60% at 100% 0%, #000 60%, transparent 110%)",
          contain: "paint",
        }} />
        <div className="relative mx-auto w-full max-w-[1120px] px-4 py-10 sm:px-8">
          <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest opacity-70 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" style={{ background: "oklch(0.145 0 0 / 0.08)" }}>
            <ArrowLeft className="size-3.5" /> All companies
          </button>
          <h1 className="mt-5 text-[34px] font-semibold leading-[1.05] tracking-[-0.03em] sm:text-[46px]">{profile.name}</h1>
          <p className="mt-2 font-mono text-[12px] opacity-70">{profile.city} · trading since {profile.founded}</p>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed opacity-75">{profile.blurb}</p>

          <dl className="mt-8 grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-4">
            {(profile.facts ?? []).map((f) => (
              <div key={f.label}>
                <dt className="font-mono text-[10px] uppercase tracking-widest opacity-60">{f.label}</dt>
                <dd className="mt-1 font-mono text-[26px] font-semibold leading-none tracking-tight">{f.value}</dd>
                <dd className="mt-1 text-[11px] opacity-60">{f.note}</dd>
              </div>
            ))}
          </dl>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1120px] px-4 pb-28 pt-8 sm:px-8">
        <div className="grid gap-3 sm:grid-cols-3">
          {([["Records in the library", c.total], ["Can be cited", c.usable], ["Blocked in code", c.blocked]] as [string, number][]).map(([k, n], i) => (
            <div key={k} className="rounded-2xl border border-border px-4 py-3">
              <p className="text-[12px] text-muted-foreground">{k}</p>
              <p className="font-mono text-[26px] font-semibold tabular-nums" style={{ color: i === 2 && n ? WARN : undefined }}>{n}</p>
            </div>
          ))}
        </div>

        {overview.length > 0 && (
          <section className="mt-8">
            <SectionHead icon={Building2} title="The company" blurb="What the bid can say about the organisation itself." count={overview.length} />
            <div className="grid gap-3 md:grid-cols-2">
              {overview.map((d) => <DocCard key={d.id} d={d} onOpen={() => setDoc(d)} />)}
            </div>
          </section>
        )}

        {SECTIONS.map(({ kind, title, icon, blurb }) => {
          const docs = profile.documents.filter((d) => d.kind === kind);
          if (!docs.length) return null;
          return (
            <section key={kind} className="mt-8">
              <SectionHead icon={icon} title={title} blurb={blurb} count={docs.length} />
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {docs.map((d) => <DocCard key={d.id} d={d} onOpen={() => setDoc(d)} />)}
              </div>
            </section>
          );
        })}

        {blocked.length > 0 && (
          <section className="mt-8 rounded-3xl border p-5" style={{ borderColor: WARN }}>
            <SectionHead icon={Ban} title="Blocked before any search" count={blocked.length} color={WARN}
              blurb="Removed in code, so they can never be cited and never reach a model." />
            <ul className="space-y-2 text-[14px]">
              {blocked.map((d) => (
                <li key={d.id} className="flex flex-wrap items-baseline gap-x-2">
                  <b className="font-mono text-[12px]">{d.id}</b>
                  <span>{d.title}</span>
                  <span className="text-muted-foreground">
                    — {d.blocked_reason === "restricted" ? "confidential: never indexed, never sent to a model" : `expired ${d.expires_on}`}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card/95">
        <div className="mx-auto flex w-full max-w-[1120px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-8">
          <span className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <BadgeCheck className="size-4" /> <b className="text-foreground">{c.usable}</b> records can back an answer for {first}
          </span>
          <button type="button" onClick={onContinue} className="inline-flex items-center gap-1.5 rounded-full px-5 py-2.5 text-[14px] font-semibold" style={{ background: PAPER, color: INK }}>
            Bid as {first} <ArrowRight className="size-4" />
          </button>
        </div>
      </div>

      <Modal open={!!doc} onClose={() => setDoc(null)} kicker={`${doc?.id ?? ""} · ${doc?.kind ?? ""}`} title={doc?.title ?? ""}
        footer={<span className="font-mono text-[11px] text-muted-foreground">{doc?.usable ? "Can be cited in an answer" : "Blocked: can never be cited"}</span>}>
        {doc && (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <div><p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">Confidentiality</p><p className="mt-1">{doc.confidentiality}</p></div>
              <div><p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">Client</p><p className="mt-1">{doc.client ?? "none named"}</p></div>
              <div><p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">Dated</p><p className="mt-1">{doc.date}{doc.expires_on ? ` · expires ${doc.expires_on}` : ""}</p></div>
            </div>
            {doc.text ? <Quote source={`${doc.id} · ${doc.title}`}>{doc.text}</Quote>
              : <p className="text-muted-foreground">Confidential: the text is never loaded into the system, so there is nothing to show.</p>}
          </>
        )}
      </Modal>
    </div>
  );
}

function SectionHead({ icon: Icon, title, blurb, count, color }: { icon: React.ElementType; title: string; blurb: string; count: number; color?: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <h2 className="flex items-center gap-2 text-[17px] font-semibold tracking-[-0.01em]" style={color ? { color } : undefined}>
        <Icon className="size-4" /> {title}
        <span className="font-mono text-[12px] font-normal text-muted-foreground">{count}</span>
      </h2>
      <p className="text-[12px] text-muted-foreground">{blurb}</p>
    </div>
  );
}
