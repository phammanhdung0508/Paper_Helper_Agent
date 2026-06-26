
## 2026-06-26 - [Accessible Hover Actions in ChatView]
**Learning:** Using Tailwind's 'invisible' class for hover-only actions (like a delete button) makes them inaccessible to keyboard users as they are removed from the accessibility tree.
**Action:** Use 'opacity-0' combined with 'focus-visible:opacity-100' and 'group-hover:opacity-100' to maintain visual intent while ensuring keyboard accessibility.
