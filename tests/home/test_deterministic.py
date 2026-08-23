from booster_home.context.deterministic import (
    collapse_duplicate_lines,
    collapse_progress,
    deterministic_normalize,
    strip_ansi,
)
from booster_home.models import ContextCategory


def test_ansi_duplicates_and_progress_are_compacted() -> None:
    assert strip_ansi("\x1b[31merror\x1b[0m") == "error"
    assert "repeated 3x" in collapse_duplicate_lines("Retrying\nRetrying\nRetrying")
    assert "progress: 1% -> 100%" in collapse_progress("1%\n2%\n50%\n100%")


def test_structured_json_remains_json_and_unicode_survives() -> None:
    result = deterministic_normalize('{"message": "ошибка", "line": 4}', ContextCategory.DIAGNOSTIC)
    assert result == '{"line":4,"message":"ошибка"}'
