## 2025-05-14 - Standardizing Tooltips across App Shell
**Learning:** The app uses a custom `.viz-tooltip` CSS class for PDF concept tags to provide instant, styled feedback. Standard UI buttons in the RightPane were using native `title` attributes, creating a disjointed experience (delayed, OS-native look vs. instant, app-styled look).
**Action:** Always wrap icon-only buttons in the top bar or right pane with `TooltipChip` to ensure visual and behavioral consistency with the core "concept tag" experience.
