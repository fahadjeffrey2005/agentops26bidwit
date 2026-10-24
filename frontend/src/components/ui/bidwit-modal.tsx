/* One modal for every "click a tile, see the detail" case. Same language as the rest: near-black sheet,
   rounded-3xl, hairline border, mono labels. Escape and the backdrop close it; focus returns to the opener. */
import * as React from "react";
import { X } from "lucide-react";
import { cx } from "./bidwit-bento";

export function Modal({ open, onClose, title, kicker, children, footer, wide }: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  kicker?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  const sheet = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sheet.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 sm:p-8" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={sheet}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        className={cx("my-auto w-full rounded-3xl border border-border bg-card p-6 shadow-2xl outline-none", wide ? "max-w-3xl" : "max-w-2xl")}
      >
        <header className="mb-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            {kicker && <p className="mb-1 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">{kicker}</p>}
            <h2 className="text-[20px] font-semibold leading-tight tracking-[-0.01em]">{title}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="shrink-0 rounded-full border border-border p-2 hover:bg-muted"><X className="size-4" /></button>
        </header>
        <div className="space-y-4 text-[14px] leading-relaxed">{children}</div>
        {footer && <div className="mt-5 flex flex-wrap items-center justify-end gap-2 border-t border-border pt-4">{footer}</div>}
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

export function Quote({ children, source }: { children: React.ReactNode; source?: React.ReactNode }) {
  return (
    <blockquote className="rounded-2xl border border-border bg-muted p-4">
      <p className="text-[14px] leading-relaxed">{children}</p>
      {source && <footer className="mt-2 font-mono text-[11px] text-muted-foreground">{source}</footer>}
    </blockquote>
  );
}
