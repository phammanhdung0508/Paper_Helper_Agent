## 2025-05-15 - Improving Keyboard Accessibility for Custom Interactive Elements
**Learning:** Custom interactive elements (like `div` drop zones) with `tabIndex={0}` must implement an `onKeyDown` handler for `Enter` and `Space` keys to be truly accessible to keyboard users. Focus visibility is also critical for these elements to guide the user.
**Action:** Always pair `onClick` with `onKeyDown` and add `focus-visible` ring styles to any non-native interactive component.
