# Security & Data Integrity Policy

## Reporting Security or Data Integrity Vulnerabilities

If you discover a security vulnerability or an intentional data corruption vector:

1. **Do not create a public GitHub issue.**
2. Send an email to **security@kanoonhq.in** with:
   - Description of the issue
   - Impact assessment
   - Proof of concept or reproduction steps
   - Affected release version(s) and file(s)
3. You will receive an acknowledgment within 24–48 hours.

### In scope
- Tampering with or poisoning released data: files whose contents do not match `data/manifest.json`, or statutory text that has been deliberately altered.
- Compromise of the release pipeline: GitHub Actions workflows, the `HF_TOKEN` used by `scripts/push_to_hub.py`, or the Hugging Face dataset repository.
- Vulnerabilities in repository scripts, including future crawlers and parsers that process untrusted HTML and PDF from government portals.

### Out of scope (use a public issue instead)
Ordinary data errors — a typo, a wrong `w.e.f.` date, a missing footnote or Act — are not security issues. Report them with the [Statutory Correction](https://github.com/kanoonhq/open-laws/issues/new?template=statutory_correction.yml) or [Act Request](https://github.com/kanoonhq/open-laws/issues/new?template=request_act.yml) templates.

## Supported Versions

Only the latest release receives fixes. Corrections are published as a new release; earlier releases are not modified.

## Data Verification & Checksum Auditing

All released assets (`.parquet`, `.jsonl.gz`) have SHA-256 checksums, sizes and row counts recorded in `data/manifest.json`. To verify a copy:

```bash
pip install -r requirements.txt
python scripts/validate.py --data-dir path/to/data   # checksums, sizes, row counts, schemas, references
```

or check a single file by hand:

```bash
sha256sum indian_central_act_sections.parquet   # compare with files.<name>.sha256 in manifest.json
```

`manifest.json` is not cryptographically signed. Its git history in this repository is the audit trail: a manifest on the Hugging Face Hub should match the one committed for the same release tag.

## Using the Data Safely

- **Escape before rendering.** Treat `full_text`, `heading` and footnote text as untrusted strings; HTML-escape them before displaying in a web page.
- **Untrusted input for LLMs.** When the corpus is used for retrieval or prompting, treat its text as data, not instructions.
- **Pin a revision.** Load files from a specific release tag (GitHub) or commit revision (Hugging Face) and verify checksums, rather than tracking a moving branch.
- **Not legal advice.** The dataset is a machine-readable compilation. Check provisions against the Official Gazette before relying on them.
