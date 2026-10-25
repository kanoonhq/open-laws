"""
Extract the frozen v0.1.1 build inputs (the data/ tree at release commit
7222593) into the gitignored .cache/inputs/v0.1.1/.

Usage:
  python scripts/extract_inputs.py [--commit 7222593] [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V011_COMMIT = "7222593"
DEFAULT_OUTPUT_DIR = ROOT / ".cache" / "inputs" / "v0.1.1"


def extract(commit: str, output_dir: Path) -> list[Path]:
    """Write every file under data/ at `commit` into output_dir (flattened)."""
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", commit, "data/"],
        check=True,
        capture_output=True,
    ).stdout
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            target = output_dir / Path(member.name).relative_to("data")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
            written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract the v0.1.1 build inputs.")
    parser.add_argument("--commit", default=V011_COMMIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    for path in extract(args.commit, args.output_dir):
        print(f"✅ {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
