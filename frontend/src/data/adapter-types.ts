/* Shapes the bento dashboard renders. */
export type ReqStatus = "cited" | "needs_input" | "flagged" | "human" | "pending";

export interface ReqRow {
  id: string;
  text: string;
  page: number | null;
  mandatory: boolean;
  category: string;
  status: ReqStatus;
  evidence: string[];
  score: number; // best evidence score (0 if none)
  note: string;
}

export interface VaultDoc {
  id: string;
  title: string;
  meta: string;
  state: "cited" | "blocked";
  why: string;
  color: string;
  color2: string;
  ink: string;
}

export interface AuditItem {
  id: string;
  kind: "blocked" | "fail" | "fixed" | "flagged" | "approved" | "decision";
  title: string;
  detail: string;
  status: string;
  step: string;
}
