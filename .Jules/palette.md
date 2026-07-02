## 2026-07-02 - [Upload Area Accessibility & Visual Polish]
**Learning:** Interactive elements using `role="button"` require explicit `onKeyDown` handlers for `Enter` and `Space` to be truly accessible. Transitioning from native `title` tooltips to the custom `TooltipChip` component provides a more responsive and brand-consistent feel.
**Action:** Always check for `role="button"` on non-button elements and ensure they have keyboard listeners and appropriate `aria-*` attributes. Use `TooltipChip` for all decorative/icon-only badges.
