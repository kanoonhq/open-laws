# Security & Data Integrity Policy

## Reporting Security or Data Integrity Vulnerabilities

If you discover a security vulnerability (such as script injection in scrapers, malicious dataset tampering, or API security issues) or an intentional data corruption vector:

1. **Do not create a public GitHub issue.**
2. Send an email to **dev@kanoonhq.com** with:
   - Description of the issue
   - Impact assessment
   - Proof of concept or reproduction steps
3. You will receive an acknowledgment within 24–48 hours.

## Data Verification & Checksum Auditing

All released assets (`.parquet`, `.jsonl.gz`) are sealed with cryptographic SHA-256 checksums recorded in `data/manifest.json`. Maintainers verify hashes against published releases on both GitHub and Hugging Face.
