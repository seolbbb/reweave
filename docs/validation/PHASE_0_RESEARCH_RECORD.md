# Phase 0 Research Record

Use this document for aggregate, non-sensitive research notes. Never commit raw
memory claims, conversation quotes, message IDs, participant names, contact
details, or private reviewer notes.

## Session record template

| Field | Value |
|---|---|
| Participant alias | P00 |
| Date | YYYY-MM-DD |
| Eligible multi-AI user | Yes / No |
| Assistant source audited | ChatGPT / Claude |
| Total items | 0 |
| Reviewed items | 0 |
| Confirmed issue cases | 0 |
| Meaningful discrepancy or unsafe memory found | Yes / No |
| Time to first discrepancy | Not found / seconds |
| Provenance comprehension confirmed | Yes / No |
| Would run a second audit | Yes / No |
| Redacted friction notes | None |

Attach the redacted JSON or CSV export outside the Git repository when it is
needed for analysis.

## Case aggregation template

Count only human-confirmed reviewed items.

| Category | Count | Redacted pattern notes |
|---|---:|---|
| Stale | 0 | |
| Wrong | 0 | |
| Conflicting | 0 | |
| Unsupported | 0 | |
| Sensitive | 0 | |
| Overshared | 0 | |
| Direct statement | 0 | |
| Model inference | 0 | |
| Unclear origin | 0 | |

One item may contribute to multiple issue-tag counts, but it counts as one real
case toward the 50-case gate.

## Gate worksheet

| Measure | Required | Observed | Pass |
|---|---:|---:|---|
| Eligible completed participants | 8-10 | 0 | No |
| Confirmed real-world cases | At least 50 | 0 | No |
| Participants finding a meaningful discrepancy or unsafe memory | At least 60% | 0% | No |
| Participants who can explain memory provenance | Must be demonstrated | 0 | No |

## Decision rule

P0 remains **In progress** while any required row fails. When evidence changes
the product direction, add a dated Decision Log entry to
`docs/PRODUCT_STRATEGY_AND_ROADMAP.md`; do not overwrite historical results.
