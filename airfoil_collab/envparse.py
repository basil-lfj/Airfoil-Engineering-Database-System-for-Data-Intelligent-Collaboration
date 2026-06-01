from __future__ import annotations

from pathlib import Path


def load_loose_env(env_path: Path) -> dict[str, str]:
    text = env_path.read_text(encoding="utf-8", errors="ignore")
    out: dict[str, str] = {}

    pending_section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            pending_section = line.lstrip("#").strip().lower() or None
            continue

        if "=" in line:
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip()
            if key:
                out[key] = val
            continue

        if ":" in line and "=" not in line:
            k, v = line.split(":", 1)
            key = k.strip()
            val = v.strip()
            if key:
                out[key] = val
            continue

        if " " in line and "=" in raw_line:
            continue

        if pending_section == "postgresql" and "PGHOST" not in out and "host" not in out:
            out["PGHOST"] = line
            continue

    for k, v in list(out.items()):
        kl = k.strip().lower()
        if kl == "port":
            out.setdefault("PGPORT", v)
        if kl == "password":
            out.setdefault("PGPASSWORD", v)
        if kl == "host":
            out.setdefault("PGHOST", v)

    return out

