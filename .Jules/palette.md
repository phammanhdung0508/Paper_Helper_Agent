## 2026-06-24 - [Keyboard Accessibility for Custom Buttons]
**Learning:** Custom interactive elements using ARIA roles (e.g., 'role=button') and 'tabIndex' must implement an 'onKeyDown' handler to support 'Enter' and 'Space' key activation. Mouse-only event handlers (like 'onClick') exclude keyboard-only and screen reader users.
**Action:** Always pair 'onClick' with 'onKeyDown' for non-semantic interactive elements, ensuring they respond to 'Enter' and 'Space'.
