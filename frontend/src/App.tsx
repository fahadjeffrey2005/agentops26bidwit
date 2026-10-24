import * as React from "react";
import { BackgroundPaths } from "@/components/ui/background-paths";
import { BidWitBento } from "@/components/ui/bidwit-bento";
import { GateATile, GateBReviewTile } from "@/components/ui/bidwit-approvals";
import { DoneTile, LiveTile, NoGoTile, StartTile } from "@/components/ui/bidwit-live";
import { api } from "@/data/api";
import type { EvidenceRow, Health, RunRow, RunView } from "@/data/api";
import * as live from "@/data/live";

const USER = "Fahad";
const POLL_MS = 1200;

function useHashRun(): [string, (id: string) => void] {
  const read = () => decodeURIComponent(window.location.hash.replace(/^#/, ""));
  const [id, setId] = React.useState(read);
  React.useEffect(() => {
    const on = () => setId(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [id, (v: string) => (window.location.hash = v)];
}

export default function App() {
  const [runId, setRunId] = useHashRun();
  const [view, setView] = React.useState<RunView | null>(null);
  const [health, setHealth] = React.useState<Health | null>(null);
  const [evidence, setEvidence] = React.useState<EvidenceRow[]>([]);
  const [runs, setRuns] = React.useState<RunRow[]>([]);
  const [err, setErr] = React.useState("");
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    api.health().then(setHealth).catch(() => setErr("Backend not reachable on 127.0.0.1:8000. Start it with: uvicorn bidwit.api:app --port 8000"));
    api.evidence().then(setEvidence).catch(() => {});
    api.runs().then(setRuns).catch(() => {});
  }, [runId]);

  // poll the run while it is working; stop when it waits for a human or is done
  React.useEffect(() => {
    if (!runId) return;
    let stop = false;
    let timer = 0;
    const load = async () => {
      try {
        const v = await api.run(runId);
        if (stop) return;
        setView(v);
        setErr("");
        if (v.status === "running") timer = window.setTimeout(load, POLL_MS);
      } catch (e) {
        if (!stop) setErr(String((e as Error).message));
      }
    };
    load();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [runId, tick]);

  const resumed = () => setTick((t) => t + 1);
  const v = view && view.run_id === runId ? view : null;

  let top: React.ReactNode;
  if (!v) top = <LiveTile view={{ run_id: runId, status: "running", doing: "opening the run", gate: null, stopped: "", report: null, audit: [], errors: [] }} />;
  else if (v.status === "running") top = <LiveTile view={v} />;
  else if (v.gate?.gate === "A") top = <GateATile key={`${v.run_id}-A`} view={v} gate={v.gate} reviewer={USER} onSent={resumed} />;
  else if (v.gate?.gate === "no_go") top = <NoGoTile view={v} gate={v.gate} reviewer={USER} onSent={resumed} />;
  else if (v.gate?.gate === "B") top = <GateBReviewTile key={`${v.run_id}-B`} view={v} gate={v.gate} reviewer={USER} onSent={resumed} />;
  else top = <DoneTile view={v} onNew={() => setRunId("")} />;

  const empty = { decision: "conditional" as const, summary: "", reasons: [] };
  const pipe = v ? live.pipeline(v) : { stages: live.STAGES.map((s) => ({ ...s, detail: "" })), at: 0 };
  const q = v ? live.queue(v) : { by: {}, total: 0 };
  const tender = v?.report?.tender;

  const errBox = err && <p className="mb-3 rounded-2xl border border-border px-4 py-3 text-[13px]" style={{ color: "oklch(0.68 0.15 25)" }}>{err}</p>;

  if (!runId)
    return (
      <div className="dark min-h-screen w-full bg-background text-foreground">
        <BackgroundPaths
          title="BidWit"
          subtitle="Tender PDF in, evidence-backed bid draft out. Every requirement ends as a cited answer or a gap flagged for a person."
          cta="Start a run"
          onCta={() => document.getElementById("start")?.scrollIntoView({ behavior: "smooth" })}
        />
        <section id="start" className="mx-auto w-full max-w-[1120px] scroll-mt-8 px-4 pb-16 pt-8 sm:px-8">
          {errBox}
          <StartTile health={health} runs={runs} onStarted={setRunId} onOpen={setRunId} />
        </section>
      </div>
    );

  return (
    <div className="dark flex min-h-screen w-full items-start justify-center bg-background p-4 text-foreground sm:p-8">
      <BidWitBento
        user={USER}
        org="Northwind IT"
        domain="IT Infrastructure"
        tender={{ title: tender?.file ?? "No tender yet", issuer: tender ? `${tender.pages} pages · ${tender.units} text units` : "start a run above", number: v?.run_id ?? "" }}
        requirements={v ? live.requirements(v) : []}
        silentMisses={v?.report?.silent_misses_count ?? 0}
        verdict={(v && live.verdict(v)) ?? empty}
        vault={v ? live.vault(v, evidence) : []}
        queueBy={q.by}
        queueTotal={q.total}
        deadline=""
        rounds={v?.report?.rounds ?? []}
        llm={{ used: v?.report?.ai_calls ?? 0, budget: health?.ai_budget ?? 150 }}
        pipeline={pipe.stages}
        pipelineAt={pipe.at}
        audit={v ? live.audit(v) : []}
        hideGrid={!v?.report}                      // no empty dashboard: it appears once the run has real data
        verdictPending={!v || !live.verdict(v)}
        navExtra={v && <button type="button" onClick={() => setRunId("")} className="rounded-full border border-border px-3 py-1.5 text-[12px] font-medium hover:bg-muted">New run</button>}
        top={
          <>
            {errBox}
            {top}
          </>
        }
      />
    </div>
  );
}
