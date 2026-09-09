# Reweave UI/UX exploration

Status: direction A (Reading Room) selected by the owner on 2026-09-09; implementation pending. B and C remain exploration history.
Date: 2026-09-09
Repository inspected: C:\\Users\\Seongbeom\\Desktop\\Projects\\Reweave
Observed HEAD: 2303357a736b12312f02d657f288530d10a5ad64

## Intended outcome

Make saved AI conversations become a readable, connected library that helps the owner return to a decision or insight and explicitly reuse relevant context in ChatGPT or Claude. Reweave should reduce routine organization, preserve sources, distinguish observation from inference, and respect destination scope. Home is the first value surface; web-chat Use is the second. A dashboard count is not the user outcome.

## Scope of this draft

Three independent visual directions for the same populated Context Home. The brief and token candidates were prepared with the installed ui-ux-pro-max skill. Images were requested through the built-in image generation tool, using current Home and Explorer screenshots as supporting product references. No application source, canonical product contract, user archive, credentials, browser registration, or Git history is changed. The previous Goal prompt's suggested real-data-gate change has NOT been applied.

## Observed baseline

The unchanged packaged web assets were served by the current FastAPI application on an isolated loopback port, with a separate synthetic SQLite archive and an in-memory no-credential adapter. The four conversation sources are repository test fixtures. No LLM was called. The two screenshots show one synthetic Brief and four manually seeded demonstration Context Items; these are layout fixtures, not evidence of extraction quality.

- baseline-home.png: current populated Home at the browser's default 1280 x 720 viewport.
- baseline-explorer.png: current Explorer at the same viewport.
- Seven top-level destinations compete for attention: Context, Library, Audit, Search, Reports, Import, Settings.
- The Home heading and summary container consume much of the first viewport when only one Brief exists. The three-column Brief grid leaves an oversized empty region for a small archive.
- Explorer adds a second scope-navigation column alongside primary navigation, the item list and detail. The large page header further reduces available reading space.
- Confidence, schema-like labels and count chips receive prominent placement. The proposed hierarchy prioritizes the actual idea, its status and its source.
- Core Self, Personal and Work are displayed as empty navigation entries in this fixture; future handling should progressively disclose them without hiding global search.
- In this observed fixture the browser reported no captured console warnings or errors. This is not a claim about all app flows.

## What the skill contributed

The required design-system search and additional UX, typography and React searches were executed. Accepted guidance: semantic color tokens; accessible contrast and focus; logical headings; 44px controls; 4/8px spacing; one primary action; progressive disclosure; restrained 150-200ms motion; readable lines; reduced-motion support; accessible React component semantics.

The automatic search also returned marketing landing-page sections, AI-purple/pink accents and ornate academic effects. Those are not suitable product requirements for this local desktop reading tool. They are not adopted. The agent selected calmer palettes and task-oriented layouts using the actual product contract. Typography candidates are Inter/Segoe UI for controls, Newsreader for A's short reading headings, and Manrope/Inter for C. A future build should use locally bundled licensed font files or system fallbacks, not require third-party font requests at runtime.

## Direction A: Reading Room (recommended)

Warm ivory, sage, short editorial headings and a readable central document. Sections use spacing and thin dividers instead of many nested cards. A small companion column carries the open question, next step and source context.

Best fit: understanding and returning to important knowledge, even with a small archive.
Tradeoff: fewer items visible at once; Explore remains the efficient route for a large library.

## Direction B: Focus Workspace

A dark navigation rail, neutral content, restrained blue interaction states and list/detail reading. Dense information is organized through alignment, predictable rows and a generous detail pane.

Best fit: frequent retrieval and moving between many context entries.
Tradeoff: stronger work-tool character and more persistent interface structure.

## Direction C: Connected Canvas

An airy board with pale blue and warm neutral surfaces, clearly differentiated idea cards and a restrained project overview. Connections are secondary and share the same underlying context model.

Best fit: scanning several projects and seeing the relationships between recent ideas.
Tradeoff: requires careful density limits to keep long text from becoming a wall of cards. It must not become a graph-first product.

## Shared information architecture proposal

Primary navigation: Home, Explore, Sources. Persistent global Search. Settings at the bottom. Import is an action, not a primary destination. Spaces are orientation aids, not exclusive storage boundaries. Knowledge Graph becomes a secondary Explore view. Exception Review is contextual; it must not become a routine approval inbox. Removing obsolete Audit and Ask Archive surfaces requires a scoped implementation that preserves valuable existing data.

Home presents what changed and what is worth returning to. Explore supports scope and type filters, list/detail reading, links and history. Sources contains saved conversations, full-source search, import and source status. The current UI labels are not accepted changes until the design is selected and recorded in the canonical product documents.

## Core interaction proposal

1. Open Home and read one useful Brief or Context Item.
2. Open an item to see its full text and related material.
3. Follow View source to the exact supporting excerpt or retained evidence snapshot.
4. Correct an item with explicit history and undo, preserving observed/inferred/suggested distinctions.
5. For reuse, open a drafted ChatGPT or Claude request and explicitly invoke the extension. Desktop guidance must not imply automatic insertion, submission, or remote analysis.

## Required follow-on states

After visual selection, implement and verify first run; no sources; saved but not analyzed; no API key; queued, running and failed analysis; a Brief with zero Context Items; a populated library; long titles and paragraphs; filtered empty search; unavailable/deleted sources; correction and undo; sensitive and cross-scope use; backup and restore; extension popup and error states. Use the same token system across every surface.

## Verification boundary

The generated images illustrate design intent. Their exact typography, copy, contrast, layout, responsiveness and behavior are not executable acceptance evidence. Actual implementation must use components and tokens and be checked with a browser at desktop widths, the supported minimum window size, narrow responsive widths, increased text size and reduced motion. Check contrast numerically, focus order, keyboard use and source navigation. Windows shell behavior and live extension integration remain separate from browser screenshots.

## Image review and implementation corrections

All three generated images were inspected. They preserve the main idea, decision, lesson, open question, next step, source links and the reduced primary navigation. They are distinct enough for an initial visual choice, but do not exactly implement the token candidates.

- A uses serif body copy and a larger reading title than the written target. For implementation, use the body font and 16px/1.55 rules from tokens.json and keep short reading headings near 30-32px at a normal desktop viewport. Do not enlarge the title at the expense of the decision and lesson.
- A renders a prominent reuse action. It must open explicit reuse guidance or a supported provider choice; it must not inject, save, analyze or submit a conversation automatically. Prefer the action label "How to use in chat" where the desktop cannot perform the actual extension action.
- B and C render the page heading as "Context"; the proposed Home label remains governed by the chosen information architecture and owner selection.
- Source-provider logos are illustrative. Implement with verified official local assets or plain text, rather than treating an AI-generated mark as the source asset.
- The synthetic baseline's sample evidence is for rendering only; it is not a grounding evaluation. Real extraction and provenance quality must be verified separately.
- The proposed foreground/background token pairs were calculated separately: normal text, muted text, white on accent and accent on selection all exceed 4.5:1 across A, B and C. This verifies the listed token pairs, not colors sampled from the generated images.

## Recommended workflow

The owner selected A in this existing design task. Give direction-a.png, design-system/MASTER.md, this brief and tokens.json to the main Reweave Goal, using GOAL_HANDOFF_A.txt. Keep one implementation owner for shared frontend code and canonical records. The Goal carries implementation through required tests, fresh executable builds and feature-to-dev-to-main integration. B and C remain exploration history.
