from __future__ import annotations

from pathlib import Path


def read_pg_service_conf(path: Path, preferred_section: str | None = None) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    current: str | None = None
    sections: dict[str, dict[str, str]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            sections.setdefault(current, {})
            continue
        if "=" in line and current is not None:
            k, v = line.split("=", 1)
            key = k.strip().lower()
            val = v.strip()
            if key:
                sections[current][key] = val

    if not sections:
        return {}

    if preferred_section and preferred_section in sections:
        return sections[preferred_section]

    first = next(iter(sections.values()))
    return first

