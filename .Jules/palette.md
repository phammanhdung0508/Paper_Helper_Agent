## 2025-05-15 - Interactive Role Accessibility
**Learning:** Custom interactive elements using ARIA roles (e.g., `role="button"`) and `tabIndex={0}` must implement an `onKeyDown` handler (supporting `Enter` and `Space`) and clear `focus-visible` styles to be fully keyboard accessible.
**Action:** Always pair `onClick` with `onKeyDown` and add focus rings to non-native interactive elements.
