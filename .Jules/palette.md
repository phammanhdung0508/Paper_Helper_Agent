## 2025-05-14 - [Standardizing Interactive Elements]
**Learning:** In this project, custom interactive elements with `role="button"` and `tabIndex` were found to lack keyboard event handlers, creating an accessibility gap. Additionally, a custom `TooltipChip` component was available but underutilized in favor of native `title` attributes.
**Action:** Always implement `onKeyDown` handlers for non-semantic buttons and prefer `TooltipChip` for consistent, instant-render tooltips across the UI.
