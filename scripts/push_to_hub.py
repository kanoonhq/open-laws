"""
Open Laws India — Hugging Face Hub Sync
=======================================
Uploads README.md (the dataset card), CHANGELOG.md, data/manifest.json and exactly the data
files listed in the manifest to the Hugging Face dataset repo, in one commit.

Usage:
  HF_TOKEN=... python scripts/push_to_hub.py
  python scripts/push_to_hub.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPO_ID = "kanoonhq/open-laws"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the dataset to the Hugging Face Hub.")
    parser.add_argument("--repo-id", default=REPO_ID)
    parser.add_argument("--dry-run", action="store_true", help="List the upload without sending it")
    args = parser.parse_args()

    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    # Data files sit at the Hub repo root, matching the dataset card's configs
    # The dataset card links CHANGELOG.md, so it ships alongside README.md.
    uploads = {"README.md": ROOT / "README.md", "CHANGELOG.md": ROOT / "CHANGELOG.md",
               "manifest.json": DATA_DIR / "manifest.json"}
    uploads |= {name: DATA_DIR / name for name in manifest["files"]}

    for path_in_repo, local in uploads.items():
        print(f"{local.relative_to(ROOT)} -> {args.repo_id}/{path_in_repo}")
    if args.dry_run:
        return 0

    from huggingface_hub import CommitOperationAdd, HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(repo_id=args.repo_id, repo_type="dataset", exist_ok=True)
    api.create_commit(
        repo_id=args.repo_id,
        repo_type="dataset",
        operations=[
            CommitOperationAdd(path_in_repo=path_in_repo, path_or_fileobj=str(local))
            for path_in_repo, local in uploads.items()
        ],
        commit_message=f"Sync {manifest['version']}",
    )
    print(f"Synced {manifest['version']} to https://huggingface.co/datasets/{args.repo_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
