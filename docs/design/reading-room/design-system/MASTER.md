# Reweave: Reading Room design system

Status: A selected by the owner on 2026-09-09; implementation pending.
Visual source: ../direction-a.png
Tokens: ../tokens.json (shared + candidates.A)
Supporting rationale: ../DESIGN_BRIEF.md

## Product intent

A warm, readable personal Context Library that helps the owner return to important ideas and their sources, with minimal routine organization. Preserve explicit Save/Use, local ownership, provenance, scope protection and the Product Spec.

## Visual system

- Canvas #F7F6F2; surface #FFFFFF; ink #242A28; secondary text #5E6762.
- Sage action #31584B with white text; selection #E9F0EB; divider #DCDDD6; danger #A63434.
- Inter or locally available Segoe UI for body and controls: 16px / 1.55 line height.
- Newsreader or readable serif fallback for short headings only. Reading titles normally 30-32px.
- Spacing 4, 8, 12, 16, 24, 32, 48px; radii 6-10px; restrained borders and shadows.
- Controls at least 44px high; 8px gaps; visible 2px focus outlines.
- Consistent outline icons; verified official local provider assets or plain text.
- Motion 180ms where useful; support reduced motion. Bundle licensed fonts locally.

## Information architecture

Primary Home, Explore, Sources; persistent Search; Settings at the bottom; Import as an action. Spaces provide orientation across shared data and are not exclusive silos. A central reading document leads, with a smaller contextual column on wide displays. Stack supporting content when width is insufficient. Avoid oversized counts, confidence metrics, duplicate navigation rails and fixed empty grids.

Explore can use a more efficient list/detail layout with the same Reading Room tokens. Do not import B's dark sidebar. Graph is a secondary Explore view, not the primary reading surface. Review is for exceptions, not ordinary approval work.

## Interaction and trust

Place evidence links near the claims they explain. Keep observed, inferred and suggested labels legible. Desktop reuse guidance must not imply automatic context injection or submission. Prefer 'How to use in chat' when the button opens instructions; the extension performs the explicit Use action.

Correct image artifacts in implementation: A's body should use the sans-serif body rule, and its large headline should follow the written size target. Preserve source data when retiring old Audit/Ask Archive UI. No source, queued work, no key, failure and offline states must explain what is saved and what happens next.

## Verification

Calculated token contrast: ink/canvas 13.52, secondary/canvas 5.41, white/accent 7.99, accent/selection 6.90. These values do not verify colors in generated images. Implement and measure actual responsive layouts, text scaling, keyboard access, focus, evidence navigation and reduced motion. Use isolated data and browser environments.

## Delivery ownership

Use this accepted A direction in the main Reweave Goal. Record it in the canonical decision log before product implementation. The Goal owns the full functionality, tests, fresh Windows executable builds and repository integration. The draft did not change application source, real data or canonical product gates.

