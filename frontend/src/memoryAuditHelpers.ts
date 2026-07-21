export type DraftAuditClaim = {
  claim_text: string;
  llm_statement_kind?: string;
  llm_evidence_verdict?: string;
  llm_issue_tags?: string[];
  llm_severity?: string;
  llm_rationale?: string;
  search_queries?: string[];
};

export type AuditReviewFields = {
  user_statement_kind: string;
  user_evidence_verdict: string;
  user_severity: string;
};

export function manualClaimsFromText(value: string): DraftAuditClaim[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 100)
    .map((claim) => ({ claim_text: claim, search_queries: [claim.slice(0, 500)] }));
}

export function isAuditItemReviewed(item: AuditReviewFields) {
  return Boolean(item.user_statement_kind && item.user_evidence_verdict && item.user_severity);
}
