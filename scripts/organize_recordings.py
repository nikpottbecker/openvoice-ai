#!/usr/bin/env python3
from pathlib import Path
import shutil


RECORDINGS = Path("/opt/phone-agent/recordings")


def call_id_for(path: Path) -> str | None:
    if path.name.startswith("sim-") or "-reply" in path.name:
        return None
    if "-" not in path.stem:
        return None
    return path.stem.split("-", 1)[0]


def main() -> int:
    moved = 0
    for path in sorted(RECORDINGS.glob("*.wav")):
        call_id = call_id_for(path)
        if not call_id:
            continue
        target_dir = RECORDINGS / call_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / path.name
        if target.exists():
            continue
        shutil.move(str(path), str(target))
        moved += 1
    print(f"moved={moved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
