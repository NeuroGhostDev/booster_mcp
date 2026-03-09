import json
import shutil
import sys
from pathlib import Path


BUNDLED_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
DEFAULT_TARGET_DIR = Path.home() / ".agents" / "skills"


def list_bundled_skills() -> list[str]:
    """Возвращает список встроенных скилов, упакованных вместе с MCP."""
    if not BUNDLED_SKILLS_DIR.exists():
        return []

    return sorted(
        skill_dir.name
        for skill_dir in BUNDLED_SKILLS_DIR.iterdir()
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists()
    )


def install_bundled_skills(
    target_dir: str | Path | None = None,
    *,
    overwrite: bool = True,
) -> dict:
    """Копирует встроенные скилы в директорию агента.

    По умолчанию синхронизирует содержимое в ~/.agents/skills.
    """
    skill_names = list_bundled_skills()
    destination_root = Path(target_dir).expanduser(
    ) if target_dir else DEFAULT_TARGET_DIR
    destination_root.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []

    for skill_name in skill_names:
        source_dir = BUNDLED_SKILLS_DIR / skill_name
        destination_dir = destination_root / skill_name

        if not destination_dir.exists():
            shutil.copytree(source_dir, destination_dir)
            installed.append(skill_name)
            continue

        changed = False
        for source_file in source_dir.rglob("*"):
            if source_file.is_dir():
                continue

            relative_path = source_file.relative_to(source_dir)
            destination_file = destination_dir / relative_path
            destination_file.parent.mkdir(parents=True, exist_ok=True)

            source_text = source_file.read_text(encoding="utf-8")
            destination_text = (
                destination_file.read_text(encoding="utf-8")
                if destination_file.exists()
                else None
            )

            if destination_text == source_text:
                continue

            if overwrite:
                destination_file.write_text(source_text, encoding="utf-8")
                changed = True
            else:
                changed = changed or False

        if changed:
            updated.append(skill_name)
        else:
            skipped.append(skill_name)

    manifest = {
        "installed": installed,
        "updated": updated,
        "skipped": skipped,
        "target_dir": str(destination_root),
        "bundled_skills": skill_names,
    }
    (destination_root / ".booster-skills.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def auto_install_bundled_skills() -> dict:
    """Пытается установить встроенные скилы и не роняет сервер при сбое."""
    try:
        result = install_bundled_skills()
        print(
            "[booster] skills sync: "
            f"installed={len(result['installed'])}, "
            f"updated={len(result['updated'])}, "
            f"skipped={len(result['skipped'])}",
            file=sys.stderr,
        )
        return {"success": True, **result}
    except Exception as exc:
        print(f"[booster] skills sync failed: {exc}", file=sys.stderr)
        return {"success": False, "error": str(exc)}
