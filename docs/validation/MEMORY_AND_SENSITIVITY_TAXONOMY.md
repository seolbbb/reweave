# Phase 0 Memory and Sensitivity Taxonomy

## Classification authority

LLM labels are suggestions. The participant's saved decision is authoritative
for Phase 0 research. Missing search evidence is not proof that a claim is
false.

## Memory content types

These types guide interviews and later ledger design; the Phase 0 UI does not
persist them as canonical memory types.

| Type | Definition | Example shape |
|---|---|---|
| Identity | A relatively stable fact about the person | Role, location, language |
| Preference | A preferred style, tool, or behavior | Concise answers, editor choice |
| Project fact | Current state of a named effort | Stack, owner, milestone |
| Decision | A choice made at a specific time | Selected approach or rejected option |
| Constraint | A rule or boundary that affects work | Budget, policy, compatibility |
| Reusable asset | Material intended for reuse | Template, prompt, checklist |
| Open loop | Unfinished work or unresolved question | Follow-up, blocker, pending choice |

## Statement origin

| Label | Use when |
|---|---|
| Direct statement | The user explicitly stated the substance of the memory |
| Model inference | The assistant derived, generalized, or psychologically inferred it |
| Unclear | Available evidence cannot distinguish the origin |

Paraphrasing a direct statement can remain direct when the meaning is faithful.
A stronger claim, generalization, diagnosis, or motive is an inference.

## Evidence verdict

| Verdict | Definition |
|---|---|
| Supported | Available evidence materially supports the current claim |
| Contradicted | Available evidence directly conflicts with the claim |
| Mixed | Credible evidence supports different versions or time periods |
| Not found | Search did not reveal adequate evidence |
| Unclear | Evidence exists but does not permit a confident judgment |

## Issue tags

Tags are independent and may be combined.

| Tag | Apply when |
|---|---|
| Stale | The memory was once plausible but is no longer current |
| Wrong | The claim is materially false, not merely incomplete |
| Conflicting | Multiple remembered or evidenced versions disagree |
| Unsupported | No adequate provenance supports the memory; do not infer wrongness solely from a search miss |
| Sensitive | The content or inference creates meaningful privacy or safety risk |
| Overshared | The memory may be valid but is too broad for the current destination or context |

## Severity

| Level | Definition |
|---|---|
| Low | Minor inconvenience or low-risk correction |
| Medium | Likely to mislead future assistance or expose private context |
| High | Could cause material harm, discrimination, major privacy exposure, or unsafe action |
| Unclear | The participant cannot judge impact yet |

## Sensitivity categories

Review these categories conservatively:

- credentials, authentication data, and security details;
- health, disability, psychological state, or inferred diagnosis;
- finances, debt, salary, or investment position;
- precise location, routines, and physical safety information;
- legal disputes or immigration status;
- sexuality, religion, politics, and other protected or intimate attributes;
- client, employer, or confidential project information;
- relationship history and information about third parties;
- inferred personality, motives, capability, or employability.

Accuracy does not remove sensitivity. A true personal memory can still be
overshared or unsafe in a work profile.

## Privacy threat model

### Protected assets

- raw conversation evidence;
- pasted assistant memory summaries;
- claim text and private reviewer notes;
- links between claims and source messages;
- participant identity;
- redacted research outputs.

### Threats and controls

| Threat | Phase 0 control |
|---|---|
| Raw summary retained unintentionally | Do not store the pasted block; store only extracted or manually entered items |
| Full archive sent to an LLM | Search locally; send one claim and at most five excerpts capped at 6,000 characters |
| Prompt injection inside memory or evidence | Mark all pasted and retrieved content as untrusted data in model prompts |
| AI suggestion mistaken for a finding | Keep LLM and user fields separate; count only saved human decisions |
| Deleted archive content retained in audit evidence | Persist references, not quote snapshots; show Source unavailable after deletion |
| Research export leaks personal content | Exclude claims, excerpts, IDs, names, and private notes by default |
| Search miss treated as falsity | Use Not found and state that absence is not contradiction |
| Premature product schema commitment | Keep the Phase 0 database separate from the archive and future ledger |

## Research consistency rules

- Do not combine wrong and stale without recording why both apply.
- Use conflicting when two credible versions differ; use mixed for the evidence
  verdict.
- Use unsupported for provenance risk, not as a synonym for wrong.
- Use overshared relative to a context or destination, even if the memory is
  supported and nonsensitive in another context.
- Redacted examples must describe the pattern without names, exact quotes,
  message IDs, unique project identifiers, or unnecessary dates.
