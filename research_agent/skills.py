"""Load two fixed, versioned project skills; never LLM-selected filesystem paths."""
from research_agent.settings import PROJECT_ROOT

SKILL_NAMES = ("ashare-data-audit", "walk-forward-review")


def skill_context():
    parts = []
    for name in SKILL_NAMES:
        path = PROJECT_ROOT / ".agents" / "skills" / name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        # Include the instructions, not discovery metadata, in the system context.
        body = text.split("---", 2)[-1].strip()
        parts.append(f"项目研究 Skill：{name}\n{body}")
    return "\n\n".join(parts)
