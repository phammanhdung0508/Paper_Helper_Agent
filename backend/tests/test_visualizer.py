import pytest
from app.visualizer import get_color_for_score

@pytest.mark.parametrize(
    "score, expected_color",
    [
        (0, "#b6b6ba"),  # Grey (unstarted)
        (1, "#7e9bc8"),  # Blue (familiar)
        (24, "#7e9bc8"), # Blue (familiar)
        (25, "#8b78d9"), # Violet (developing)
        (49, "#8b78d9"), # Violet (developing)
        (50, "#4fae84"), # Light green (competent)
        (74, "#4fae84"), # Light green (competent)
        (75, "#16a06d"), # Deep emerald (mastered)
        (100, "#16a06d") # Deep emerald (mastered)
    ]
)
def test_get_color_for_score_boundaries(score, expected_color):
    """Test boundary values for get_color_for_score."""
    assert get_color_for_score(score) == expected_color
