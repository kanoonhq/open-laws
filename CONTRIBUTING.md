# Contributing to Open Laws India (`kanoonhq/open-laws`)

Thank you for your interest in contributing to **Open Laws India**! This project aims to build the open, canonical, machine-readable statutory corpus of India. The roadmap is in [`PROCUREMENT_PLAN.md`](PROCUREMENT_PLAN.md).

Because legal practitioners, courts, AI systems, and scholars rely on this data, **accuracy, provenance, and data integrity are non-negotiable**.

---

## Code of Conduct

By participating, you agree to uphold a welcoming, respectful, and collaborative environment. Be thoughtful, constructive, and adhere to high standards of verification.

---

## Setup

```bash
pip install -r requirements.txt ruff
python scripts/validate.py   # checksums, row counts, schemas, cross-references
ruff check scripts/
```

---

## Sourcing and Provenance Requirements

Every addition, amendment, or correction **MUST** be backed by an authoritative government source. In order of precedence:
1. **Gazette of India** (`egazette.gov.in`) or the respective **State Government Gazette** — the authoritative publication.
2. **As-enacted texts** published by the Legislative Department (`legislative.gov.in`) or a State Legislative / Law Department.
3. **India Code** (`indiacode.nic.in`) — an official compilation of the current text.

If sources disagree, the Gazette prevails: cite it and note the discrepancy with India Code in the issue or PR. Authoritative texts in Hindi or another official language (e.g. Hindi texts of Central Acts, State Acts enacted in a regional language) are valid sources; say which language you used.

> [!WARNING]
> Secondary sources (blogs, unverified aggregators, student study portals) are **strictly prohibited** as sole citations.

> [!WARNING]
> Do not submit statutory text produced by an LLM, or OCR output you have not checked word for word against the source. Every character of statutory text must be traceable to an official document.

---

## Change in Law vs Data Error

Say which one your report is, because they are recorded differently:

- **Change in law** — the statute itself changed (an amendment, repeal, commencement notification, or court ruling striking down a provision). Provide the amending instrument (e.g. `Act 13 of 2013, s. 9`), the Gazette notification number, and the **date it took effect**. Earlier wording stays in the dataset as a historical version; it is not overwritten.
- **Data error** — the dataset misrepresents the law as it stood (a typo, wrong `w.e.f.` date, missing footnote). Provide the incorrect value, the correct value and the source. The fix is listed in the release notes of the next version.

---

## Types of Contributions

### 1. Reporting an Error or Typo
If you find a typographical error, missing footnote, or incorrect commencement date (`w.e.f.`):
- Open an issue using the [Statutory Correction Template](https://github.com/kanoonhq/open-laws/issues/new?template=statutory_correction.yml).
- Provide the Act ID (e.g. `A1860-45`), Section number, the incorrect text, the corrected text, and the official Gazette citation.

### 2. Requesting a Missing Act
If an Act is missing:
- Open an issue using the [Act Request Template](https://github.com/kanoonhq/open-laws/issues/new?template=request_act.yml).
- State whether it is a Central or State Act, the Act number/year, and link the India Code DSpace handle or Gazette notification.

### 3. Submitting Code or Documentation via Pull Request
- Data files under `data/` are sealed by checksums in `data/manifest.json`, and the build script that regenerates them is not yet in the repository. Until it is, **data corrections go through issues** and maintainers apply them; pull requests should change code, schemas or documentation only.
- All contributions must pass the local integrity validator:
  ```bash
  python scripts/validate.py
  ```
- Any new or modified schemas must remain valid JSON Schema (Draft 2020-12), and records must conform to the corresponding schema in `schemas/`.
- Python code must pass Ruff linting:
  ```bash
  ruff check scripts/
  ```

---

## Pull Request Guidelines

1. **One Focus Per PR**: Keep PRs focused (e.g., one parser fix or one schema change). Do not bundle unrelated modifications.
2. **Deterministic IDs**: Follow the project's current ID formats (`A{YEAR}-{NUMBER}` for Central Acts, no zero padding, e.g. `A1908-5`; `A{YEAR}-{NUMBER}:{SECTION_SLUG}` for sections). Jurisdiction-qualified IDs for State Acts and other instruments are planned in [`PROCUREMENT_PLAN.md` §2.1](PROCUREMENT_PLAN.md); do not invent IDs for State Acts before that scheme lands. Published IDs are never reused.
3. **Squash Merges**: We squash-merge PRs to keep the Git history linear and clean. Your PR title should be descriptive (e.g., `fix(A1860-45): correct w.e.f. date for Section 376 footnote 4`).

---

## Dataset License

By submitting a contribution, you dedicate your data contributions — corrections, metadata, annotations, mappings — to the public domain under the [CC0 1.0 Universal License](https://creativecommons.org/publicdomain/zero/1.0/), and confirm it is free of any proprietary copyright or restrictions. Code contributions are licensed under the MIT License. Statutory text itself is reproduced under Section 52(1)(q) of the Copyright Act, 1957; see [`LICENSE`](LICENSE).
