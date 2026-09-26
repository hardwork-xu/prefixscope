"""Check local links, bilingual pairs and citation metadata. / 检查链接、双语配对及引用。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    pairs = [
        ("README.md", "README_zh.md"),
        ("CONTRIBUTING.md", "CONTRIBUTING_zh.md"),
        ("SECURITY.md", "SECURITY_zh.md"),
    ]
    required = {
        "RESEARCH.md",
        "ARCHITECTURE.md",
        "EXPERIMENTS.md",
        "DEVELOPMENT.md",
        "WALKTHROUGH.md",
        "RELEASE.md",
        "RESUME.md",
    }
    english = {p.name for p in (ROOT / "docs/en").glob("*.md")}
    chinese = {p.name for p in (ROOT / "docs/zh").glob("*.md")}
    assert english == chinese and required <= english, (english, chinese)
    pairs += [(f"docs/en/{name}", f"docs/zh/{name}") for name in sorted(english)]
    for en, zh in pairs:
        assert (ROOT / en).is_file() and (ROOT / zh).is_file(), (en, zh)
        en_text, zh_text = (ROOT / en).read_text(), (ROOT / zh).read_text()
        assert len(en_text) >= 100 and re.search(r"[\u4e00-\u9fff]", zh_text), (en, zh)
        en_commands = re.findall(r"```(?:bash|sh)\n(.*?)```", en_text, re.S)
        zh_commands = re.findall(r"```(?:bash|sh)\n(.*?)```", zh_text, re.S)
        assert en_commands == zh_commands, f"bilingual commands differ: {en}"
    paths = [
        p
        for p in ROOT.rglob("*.md")
        if not any(
            part.startswith(".") or part in {"build", "dist", "data"} or part.endswith(".egg-info")
            for part in p.relative_to(ROOT).parts
        )
    ]
    links = 0
    for path in paths:
        text = re.sub(r"```.*?```", "", path.read_text(), flags=re.S)
        for link in re.findall(r"\]\(([^)]+)\)", text):
            target = link.split("#", 1)[0].split(" ", 1)[0].strip("<>")
            if not target or re.match(r"[a-z]+:", target):
                continue
            assert (path.parent / target).exists(), (
                f"broken link: {path.relative_to(ROOT)} -> {target}"
            )
            links += 1
    schema = json.loads((ROOT / "third_party/cff-1.2.0.schema.json").read_text())
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text())
    jsonschema.Draft7Validator(schema).validate(citation)
    assert citation["version"] == "0.1.0"
    en_table, zh_table = ROOT / "results/table.en.md", ROOT / "results/table.zh.md"
    if en_table.exists() and zh_table.exists():
        number_pattern = r"\d+(?:\.\d+)?"
        assert re.findall(number_pattern, en_table.read_text()) == re.findall(
            number_pattern, zh_table.read_text()
        )
    print(
        json.dumps(
            {
                "status": "passed",
                "markdown_files": len(paths),
                "local_links": links,
                "bilingual_pairs": len(pairs),
                "citation_schema": "1.2.0",
                "semantic_translation_review": "manual; automated check covers pairs, commands, numeric tables only",
            }
        )
    )


if __name__ == "__main__":
    main()
