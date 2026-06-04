# Reweave Product Design QA

## Visual targets

- Search: Quiet Library layout with search-first results and a persistent selected-source rail.
- Reports: Insight Studio layout with saved reports, report outline, document reading surface, and supporting-source rail.
- Shared system: Reports-style sidebar, typography, spacing, color, and controls across every destination.

## Verified states

1. Search empty state at 1280 x 720.
2. Search results for `Python` at 1280 x 720.
3. Reports document with saved-report navigation and four report sources.
4. Report source opened into the supporting-message preview.
5. Import destination with archive statistics and both import methods.
6. Settings destination with provider connection, model selection, and advanced settings.
7. Desktop layout measurements at 1440 x 1024.

## Findings

- P0: none.
- P1: none.
- P2: none.
- P3: The in-app browser tiled its screenshot after applying a temporary 1440 x 1024 viewport override. DOM measurements confirmed the app itself remained a single correctly sized layout; the normal viewport capture rendered correctly.

## Accessibility checks

- Primary navigation exposes the active page.
- Filter disclosure exposes expanded state.
- Search and source-selection controls have accessible labels.
- Keyboard focus styles are visible.
- Main action targets are at least 34px high, with primary actions at least 38px high.

## Final result

final result: passed
