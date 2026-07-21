# Phase 0 Memory-Audit Pilot Protocol

## Purpose and status

This protocol tests whether people who use multiple AI assistants can find and
explain meaningful problems in assistant memory. It does not validate the
Phase 1 Canonical Memory Ledger, automatic delivery, or provider writes.

The first session is a one-person ChatGPT pilot. Phase 0 remains **In progress**
until 8-10 target participants complete the protocol, at least 50 real cases
are collected, at least 60% find a meaningful discrepancy or unsafe memory,
and participants can explain what an assistant remembers and why.

## Participant criteria

Recruit people who:

- use at least two AI assistants;
- have at least 100 accumulated conversations;
- work on projects or personal contexts that change over time;
- can obtain a ChatGPT or Claude memory summary;
- are willing to inspect local conversation evidence without sharing raw
  personal content with the researcher.

Exclude casual users with very small archives and anyone who cannot give
informed consent for the session.

## Data handling and consent

Before the session, explain these boundaries:

1. Conversation archives and saved audit sessions stay on the participant's
   device.
2. If AI assistance is enabled, the pasted memory summary is sent to the
   participant's configured provider for item extraction. Reweave does not save
   the original pasted block.
3. Evidence review sends only the current claim and up to five candidate
   excerpts, capped at 6,000 characters, to the configured provider.
4. AI output is a suggestion. Only the participant's saved choices count as
   findings.
5. Redacted JSON and CSV exports omit claim text, evidence text, conversation
   and message IDs, private notes, and participant identifiers.
6. The participant may stop, skip an item, or delete the local audit session at
   any time.

Record verbal or written consent outside Reweave without storing the person's
name in a committed project file.

## One-person pilot procedure

Target duration: 30-45 minutes.

### 1. Prepare

- Import the participant's ChatGPT conversation export.
- Confirm local archive search works.
- Obtain the memory summary shown by ChatGPT.
- Optionally connect an LLM profile. Manual one-item-per-line mode must remain
  available if the provider is unavailable or the participant declines it.

### 2. Start the audit

- Open **Audit** and select ChatGPT.
- Paste the memory summary.
- Use **Extract with AI**, or **Use one item per line** for the manual path.
- Confirm that the original pasted block is not present after the session is
  created.

### 3. Review each memory item

Ask the participant to think aloud and:

1. classify the item as a direct statement, model inference, or unclear;
2. search the default ChatGPT scope for evidence;
3. inspect candidate messages in the evidence drawer;
4. attach supporting, contradicting, or contextual evidence when useful;
5. choose supported, contradicted, mixed, not found, or unclear;
6. assign zero or more issue tags and a severity;
7. write an optional redacted example that is safe for research aggregation;
8. save the human review.

Do not coach the participant toward a discrepancy. A supported, harmless memory
is a valid result.

### 4. Complete and debrief

The participant may complete the pilot only after every item has a statement
type, evidence verdict, and severity. Ask them to confirm:

> I can explain each memory and the evidence behind it.

Then ask:

- Which finding mattered most, and why?
- Did direct statement versus model inference make sense?
- Did any memory feel unsafe even when accurate?
- Did the evidence change the participant's initial judgment?
- Was any search failure mistaken for proof that a memory was wrong?
- What would make the participant run a second audit?

Export only the redacted JSON or CSV summary.

## Broader 8-10 participant interview

Use the same task order and data boundaries for every participant. The
researcher should observe without accessing raw archive content unless the
participant explicitly chooses to show it.

Record these session-level measures:

- assistant source;
- total and reviewed item counts;
- confirmed issue count;
- whether a meaningful discrepancy or unsafe memory was found;
- time to first confirmed discrepancy;
- whether provenance comprehension was confirmed;
- whether the participant would run another audit;
- workflow friction recorded only in redacted language.

## Gate decision

Do not mark P0 complete unless all conditions hold:

- 8-10 eligible participants completed the protocol;
- at least 50 confirmed real-world cases were collected;
- at least 60% found a meaningful discrepancy or unsafe memory;
- participants could answer what each reviewed assistant remembered and why;
- the problem repeated across participants rather than appearing as isolated
  edge cases.

If the gate fails, keep P0 in progress or defer the product direction. Record a
new Decision Log entry instead of rewriting prior decisions.
