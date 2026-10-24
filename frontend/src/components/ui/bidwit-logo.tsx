/* BidWit logo: the mark alone, or the mark with the wordmark. Inherits currentColor, so it works on
   the dark app chrome and on the white header bands without a second file. */
import * as React from "react";

export function LogoMark({ className, title, style }: { className?: string; title?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 58 68" className={className} style={style} fill="currentColor" role={title ? "img" : "presentation"} aria-label={title} aria-hidden={title ? undefined : true}>
      {title && <title>{title}</title>}
      <path d="M2 9a7 7 0 0 1 7-7h19c13 0 22 7 22 17 0 7-5 13-13 16L24 40 2 31Z" />
      <path d="M2 38l22 9 16-6c10 3 17 9 17 17 0 8-8 12-20 12H9a7 7 0 0 1-7-7Z" />
    </svg>
  );
}

export function Logo({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <span className={className} style={{ display: "inline-flex", alignItems: "center", gap: size * 0.42 }}>
      <LogoMark title="BidWit" style={{ height: size }} className="w-auto" />
      <span style={{ fontSize: size * 0.95, letterSpacing: "-0.035em", lineHeight: 1 }}>
        <span style={{ fontWeight: 400 }}>Bid</span><span style={{ fontWeight: 700 }}>Wit</span>
      </span>
    </span>
  );
}
