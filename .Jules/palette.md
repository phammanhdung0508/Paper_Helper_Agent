## 2025-05-14 - [Icon-only Buttons & Form Accessibility]
**Learning:** Found several patterns of missing ARIA labels on icon-only buttons (pagination, send, feedback) and form inputs lacking explicit labels connected via `htmlFor` and `id`. This makes the application significantly less accessible to screen reader users.
**Action:** Always ensure icon-only buttons have `aria-label` and all form inputs have associated `<label>` elements. Use CSS like `sr-only` to hide labels while keeping them accessible.
