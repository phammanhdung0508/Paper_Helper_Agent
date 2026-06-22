## 2025-06-22 - [Keyboard Accessibility for Custom Interactive Elements]
**Learning:** Custom elements with `role="button"` and `tabIndex={0}` are not automatically accessible via keyboard in React. They require an explicit `onKeyDown` handler to support `Enter` and `Space` keys, along with `focus-visible` styles for visual feedback.
**Action:** Always implement `onKeyDown` and `focus-visible` ring classes when using `role="button"` on non-interactive elements like `div` or `span`.
