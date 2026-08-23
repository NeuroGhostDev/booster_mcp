from booster_home.context.diagnostic import Diagnostic, DiagnosticLifecycle


def test_diagnostic_change_and_reappearance_are_distinguished() -> None:
    lifecycle = DiagnosticLifecycle()
    first = Diagnostic(source="ruff", code="E1", file="a.py", line=4, message="old")
    changed = Diagnostic(source="ruff", code="E1", file="a.py", line=4, message="new")
    assert lifecycle.update([first])["appeared"] == [first.fingerprint]
    assert lifecycle.update([changed])["changed"] == [first.fingerprint]
    assert lifecycle.update([])["resolved"] == [first.fingerprint]
    assert lifecycle.update([changed])["reappeared"] == [first.fingerprint]
