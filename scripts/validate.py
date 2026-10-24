"""
Open Laws India — Standalone Data Integrity Validator
=====================================================
Validates that all Parquet and JSONL dataset files in data/ match the
cryptographic SHA-256 checksums recorded in data/manifest.json.

Usage:
  python scripts/validate.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

try:
    import pyarrow.parquet as pq
except ImportError:
    pq = None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    manifest_path = data_dir / "manifest.json"

    if not manifest_path.exists():
        print(f"ERROR: manifest.json not found in {data_dir}")
        return 1

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    print("=" * 60)
    print("Open Laws India — Dataset Verification")
    print(f"Version:            {manifest.get('version', 'v0.1.0')}")
    print(f"Total Acts:         {manifest.get('total_acts', 0):,}")
    print(f"Total Sections:     {manifest.get('total_sections', 0):,}")
    print(f"Total Footnotes:    {manifest.get('total_footnotes', 0):,}")
    print(f"Footnotes w/ w.e.f: {manifest.get('footnotes_with_wef', 0):,}")
    print(f"Criminal Mappings:  {manifest.get('total_mappings', 0):,}")
    print("=" * 60)

    files_meta = manifest.get("files", {})
    all_ok = True

    for filename, meta in files_meta.items():
        file_path = data_dir / filename
        if not file_path.exists():
            print(f"❌ Missing file: {filename}")
            all_ok = False
            continue

        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        actual_sha = sha.hexdigest()

        if actual_sha != meta["sha256"]:
            print(f"❌ Checksum mismatch: {filename}")
            print(f"   Expected: {meta['sha256']}")
            print(f"   Actual:   {actual_sha}")
            all_ok = False
        else:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            print(f"✅ {filename} ({size_mb:.2f} MB)")

    if pq is not None:
        print("\nVerifying Parquet row counts...")
        acts_t = pq.read_table(data_dir / "indian_central_acts.parquet")
        sec_t = pq.read_table(data_dir / "indian_central_act_sections.parquet")
        fn_t = pq.read_table(data_dir / "central_act_footnotes.parquet")
        map_t = pq.read_table(data_dir / "criminal_law_mappings.parquet")

        assert acts_t.num_rows == manifest["total_acts"]
        assert sec_t.num_rows == manifest["total_sections"]
        assert fn_t.num_rows == manifest["total_footnotes"]
        assert map_t.num_rows == manifest["total_mappings"]
        print("✅ Parquet row counts strictly match manifest.")

    if all_ok:
        print("\nALL INTEGRITY CHECKS PASSED SUCCESSFULLY.")
        return 0
    else:
        print("\nDATASET VERIFICATION FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
