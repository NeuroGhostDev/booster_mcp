from skill_installer import list_bundled_skills


def test_bundled_skills_are_discoverable() -> None:
    skills = list_bundled_skills()

    assert "booster-onboard" in skills
    assert "booster-review" in skills
    assert len(skills) >= 12
