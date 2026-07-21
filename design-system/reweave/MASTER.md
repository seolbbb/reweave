# Reweave design system

Reweave is a local-first desktop knowledge tool. Its interface should feel calm,
precise, and trustworthy rather than decorative or promotional.

## Foundations

- Use one native sans-serif stack everywhere, including headings and long-form reports:
  `"Segoe UI Variable Text", "Segoe UI", "Noto Sans KR", "Malgun Gothic", sans-serif`.
- Use a 4px base unit. Default gaps and padding should use 8, 12, 16, 24, or 32px.
- Keep page titles between 28 and 32px. Body copy is 14-15px with a 1.5-1.65 line height.
- Use sentence case. Avoid all-caps eyebrow text and decorative letter spacing.
- Keep content inside a shared 1120px page frame with 24-32px responsive gutters.

## Semantic color tokens

| Role | Value |
| --- | --- |
| App background | `#f4f6f7` |
| Surface | `#ffffff` |
| Subtle surface | `#f7f8f9` |
| Primary text | `#20262d` |
| Secondary text | `#687480` |
| Border | `#dce1e5` |
| Accent | `#315f7d` |
| Accent hover | `#284f69` |
| Accent subtle | `#eaf1f5` |
| Success | `#2f7652` |
| Danger | `#a34444` |
| Focus ring | `rgba(49, 95, 125, 0.22)` |

## Components

- Buttons and inputs are 40-42px tall with an 8px radius and 14px text.
- Use Lucide icons at 16-20px with consistent stroke weight.
- Default surfaces are flat. Use a 1px border instead of a shadow for grouping.
- Reserve shadows for floating overlays, drawers, and the report paper.
- Active navigation uses one quiet tinted background, not an outline plus a fill.
- Empty states should explain the next action in one sentence and avoid oversized artwork.
- Show visible focus rings, disabled states, and progress feedback for asynchronous actions.

## Page patterns

- Library, Import, and Settings share the same page header, gutters, section spacing,
  control heights, and card treatment.
- Search uses a stable three-column desktop shell: navigation, results, and selected sources.
- Reports use a reading workspace: outline, paper, and source rail. The report body uses the
  same sans-serif family as the rest of the product.
- At small widths, primary navigation becomes a labeled top bar and secondary rails stack
  below the main content without horizontal scrolling.

## Motion and accessibility

- Use 140-180ms color, border, and opacity transitions only.
- Do not animate layout dimensions or use decorative entrance effects.
- Respect `prefers-reduced-motion`.
- Normal text must meet WCAG AA contrast, controls must remain keyboard reachable, and
  interactive targets should be at least 40px on desktop and 44px on touch layouts.

## Avoid

- Mixed serif and sans-serif type.
- Text smaller than 12px.
- Decorative gradients, glass effects, glow, oversized radii, or floating cards everywhere.
- Uppercase labels with wide tracking.
- Multiple competing primary buttons on one surface.
- Arbitrary colors, shadows, spacing, or per-page layout widths.
