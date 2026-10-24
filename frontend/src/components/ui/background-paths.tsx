/* Landing hero from the supplied "background-paths" template. Same paths, title animation and glass button;
   motion is done with CSS (stroke-dashoffset + keyframes) instead of framer-motion, so no extra dependencies. */
import * as React from "react";
import { LogoMark } from "./bidwit-logo";

function FloatingPaths({ position }: { position: number }) {
  const paths = React.useMemo(
    () =>
      Array.from({ length: 36 }, (_, i) => ({
        id: i,
        d: `M-${380 - i * 5 * position} -${189 + i * 6}C-${380 - i * 5 * position} -${189 + i * 6} -${312 - i * 5 * position} ${216 - i * 6} ${
          152 - i * 5 * position
        } ${343 - i * 6}C${616 - i * 5 * position} ${470 - i * 6} ${684 - i * 5 * position} ${875 - i * 6} ${684 - i * 5 * position} ${875 - i * 6}`,
        width: 0.5 + i * 0.03,
        duration: 20 + ((i * 7919) % 100) / 10, // 20-30 s, deterministic
      })),
    [position],
  );
  return (
    <div className="pointer-events-none absolute inset-0" style={{ contain: "strict" }}>
      <svg className="h-full w-full text-white" viewBox="0 0 696 316" fill="none" aria-hidden>
        {paths.map((p) => (
          <path
            key={p.id}
            d={p.d}
            stroke="currentColor"
            strokeWidth={p.width}
            strokeOpacity={0.1 + p.id * 0.03}
            className="bw-path motion-reduce:[animation:none]"
            style={{ animationDuration: `${p.duration}s` }}
          />
        ))}
      </svg>
    </div>
  );
}

export function BackgroundPaths({ title, subtitle, cta, onCta, children }: { title: string; subtitle?: React.ReactNode; cta: string; onCta: () => void; children?: React.ReactNode }) {
  const words = title.split(" ");
  return (
    <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-neutral-950">
      <style>{`
        .bw-path { stroke-dasharray: 600 900; animation: bw-flow linear infinite; }
        @keyframes bw-flow { 0% { stroke-dashoffset: 0; opacity: .3 } 50% { opacity: .6 } 100% { stroke-dashoffset: -3000; opacity: .3 } }
        .bw-letter { display: inline-block; animation: bw-rise .9s cubic-bezier(.2,.9,.25,1.15) backwards; }
        @keyframes bw-rise { from { opacity: 0; transform: translateY(100px) } to { opacity: 1; transform: none } }
        .bw-fade { animation: bw-in 1.2s ease backwards }
        @keyframes bw-in { from { opacity: 0 } to { opacity: 1 } }
        @media (prefers-reduced-motion: reduce) { .bw-letter, .bw-fade { animation: none; opacity: 1; transform: none } }
      `}</style>
      <div className="absolute inset-0">
        <FloatingPaths position={1} />
        <FloatingPaths position={-1} />
      </div>

      <div className="bw-fade relative z-10 mx-auto w-full max-w-4xl px-4 text-center md:px-6">
        <LogoMark title="BidWit" className="mx-auto mb-7 h-16 w-auto text-white sm:h-20" />
        <h1 className="mb-6 text-5xl font-bold tracking-tighter sm:text-7xl md:text-8xl">
          {words.map((word, wi) => (
            <span key={wi} className="mr-4 inline-block last:mr-0">
              {word.split("").map((letter, li) => (
                <span key={li} className="bw-letter bg-gradient-to-r from-white to-white/80 bg-clip-text text-transparent" style={{ animationDelay: `${wi * 0.1 + li * 0.03}s` }}>
                  {letter}
                </span>
              ))}
            </span>
          ))}
        </h1>
        {subtitle && <p className="mx-auto mb-10 max-w-2xl text-lg text-white/60">{subtitle}</p>}

        <div className="group relative inline-block overflow-hidden rounded-2xl bg-gradient-to-b from-white/10 to-black/10 p-px shadow-lg transition-shadow duration-300 hover:shadow-xl">
          <button
            type="button"
            onClick={onCta}
            className="inline-flex items-center rounded-[1.15rem] border border-white/10 bg-black/95 px-8 py-4 text-lg font-semibold text-white transition-all duration-300 group-hover:-translate-y-0.5 hover:bg-black hover:shadow-md hover:shadow-neutral-800/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
          >
            <span className="opacity-90 transition-opacity group-hover:opacity-100">{cta}</span>
            <span className="ml-3 opacity-70 transition-all duration-300 group-hover:translate-x-1.5 group-hover:opacity-100">→</span>
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default BackgroundPaths;
