## 2025-05-15 - Keyboard accessibility for custom interactive elements
**Learning:** Custom interactive elements using ARIA roles (e.g., `role="button"`) and `tabIndex` must implement an `onKeyDown` handler to support 'Enter' and 'Space' key activation for full keyboard accessibility. Without this, the element is focusable but cannot be triggered by keyboard-only users.
**Action:** Always check for `role="button"` on non-button elements and ensure they have both a `tabIndex` and a keyboard event handler.
