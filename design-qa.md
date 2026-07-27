# Design QA — monthly plan invoice coverage

- Source visual truth: `/var/folders/99/kyvrj9bs6wl8rx8mdxvxymwm0000gn/T/codex-clipboard-fc7813f8-a988-48c5-8972-010fa7522214.png`
- Final wide implementation: `/tmp/billing-control-design-qa/monthly-plans-qa-wide-final.jpg`
- Final notebook-width implementation: `/tmp/billing-control-design-qa/monthly-plans-qa-narrow-final.jpg`
- Expanded invoice state: `/tmp/billing-control-design-qa/monthly-plans-qa-expanded.jpg`
- Normalized source/final comparison: `/tmp/billing-control-design-qa/monthly-plans-qa-comparison.png`
- Route: `http://localhost:3000/monthly-plans`
- State: authenticated local dev seed, April 2026 plan, one part with four linked invoices, including long supplier names and paid/unpaid states

## Capture normalization

- Source pixels: 2306 × 660.
- Wide implementation viewport: 2048 × 586 CSS px; captured content: 2033 × 582 px at browser density 1.
- For the comparison artifact, the source was proportionally normalized to 2033 × 582 and stacked above the 2033 × 582 implementation capture.
- Notebook check viewport: 1440 × 800 CSS px. The content area is 1193 px wide after the sidebar.

## Full-view comparison evidence

The source shows invoice metadata and actions in one non-wrapping line. The line crosses the right edge of “Покрытие счетами” and visually collides with “Поставлено”.

The final implementation confines every invoice to the coverage column. Its first row contains invoice number, invoice date and a safely truncated supplier; its second row contains coverage, payment state and actions. The delivery column remains visually independent.

## Focused-region evidence

The focused row was tested with four linked invoices, two paid/unpaid states, and a supplier longer than the available slot. No invoice content or action crossed the column boundary. The invoice-detail disclosure was opened successfully; the full supplier and invoice metadata remained inside the card.

## Required fidelity surfaces

- Fonts and typography: existing product font stack, sizes and weights are preserved. Invoice number remains monospace; dates and semantic labels do not wrap unpredictably; supplier truncation exposes the full value through `title`.
- Spacing and layout rhythm: invoice cards use a consistent two-row structure, internal divider and action alignment. Quantity controls remain aligned. Row height expands only when invoice count or disclosed details require it.
- Colors and tokens: existing zinc, emerald, red and amber semantic tokens are preserved. No new palette or unrelated visual language was introduced.
- Image quality and assets: the inspected region contains no product imagery or custom assets; no asset substitutions were made.
- Copy and content: full Russian action labels replace the cramped abbreviations. Invoice date is explicitly shown as “от DD.MM.YYYY”; payment and coverage labels remain unambiguous.

## Comparison history

1. P1 from source: invoice metadata/actions overflowed into the delivery column.
   - Fix: replaced the single non-wrapping invoice row with a bounded two-row card; separated the disclosure button from edit/unlink buttons; added truncation and overflow containment.
   - Post-fix evidence: wide capture and normalized comparison show a clean coverage/delivery boundary.

2. P2 from first notebook-width pass: `min-width: 1360px` forced the delivery column behind horizontal scrolling at a 1440 px viewport.
   - Fix: reduced the table minimum to 1180 px after the two-row invoice layout made the narrower coverage cell safe.
   - Post-fix evidence: at 1440 × 800, every tested table container reports `clientWidth: 1193`, `scrollWidth: 1193`, page `scrollX: 0`; all six columns are visible.

## Interaction and runtime checks

- Authentication and monthly-plan loading succeeded.
- Invoice disclosure opened and exposed detailed metadata without layout overflow.
- Wide and notebook-width responsive states were captured.
- Browser console errors/warnings after the final reload: none.
- Frontend production Docker build: passed.
- Backend tests: 13 passed.

## Remaining findings

No actionable P0, P1 or P2 visual findings remain in the tested table state. The dev build reports existing Svelte dependency-version warnings and npm audit findings; they do not reproduce as runtime console failures in this flow and are outside this layout fix.

final result: passed
