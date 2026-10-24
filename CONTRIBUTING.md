# Contributing to Open Laws India (`kanoonhq/open-laws`)

Thank you for your interest in contributing to **Open Laws India**! This project aims to build the open, canonical, machine-readable statutory corpus of India.

Because legal practitioners, courts, AI systems, and scholars rely on this data, **accuracy, provenance, and data integrity are non-negotiable**.

---

## Code of Conduct

By participating, you agree to uphold a welcoming, respectful, and collaborative environment. Be thoughtful, constructive, and adhere to high standards of verification.

---

## Sourcing and Provenance Requirements

Every addition, amendment, or correction **MUST** be backed by an authoritative government source:
1. **Gazette of India** (`egazette.gov.in`) or respective **State Government Gazette**.
2. **India Code** (`indiacode.nic.in`) official publication.
3. Official Legislative Assembly / Parliamentary Act notification.

> [!WARNING]
> Secondary sources (blogs, unverified aggregators, student study portals) are **strictly prohibited** as sole citations.

---

## Types of Contributions

### 1. Reporting an Error or Typo
If you find a typographical error, missing footnote, or incorrect commencement date (`w.e.f.`):
- Open an issue using the [Statutory Correction Template](https://github.com/kanoonhq/open-laws/issues/new?template=statutory_correction.yml).
- Provide the Act ID (e.g. `A1860-45`), Section number, the incorrect text, the corrected text, and the official Gazette citation.

### 2. Requesting a Missing Act
If an Act is missing:
- Open an issue using the [Act Request Template](https://github.com/kanoonhq/open-laws/issues/new?template=request_act.yml).
- State whether it is a Central or State Act, the Act number/year, and link the India Code DSpace handle.

### 3. Submitting Code or Data via Pull Request
- All contributions must pass the local integrity validator:
  ```bash
  python scripts/validate.py
  ```
- Any new or modified records must conform to the corresponding JSON Schema in `schemas/`.
- Python code must pass Ruff linting:
  ```bash
  ruff check scripts/
  ```

---

## Pull Request Guidelines

1. **One Focus Per PR**: Keep PRs focused (e.g., adding a specific State Act or fixing footnotes for one Act). Do not bundle unrelated modifications.
2. **Deterministic IDs**: Always follow the project's ID formats (e.g. `A{YEAR}-{NUMBER}` for acts, `A{YEAR}-{NUMBER}:{SECTION_SLUG}` for sections).
3. **Squash Merges**: We squash-merge PRs to keep the Git history linear and clean. Your PR title should be descriptive (e.g., `fix(A1860-45): correct w.e.f. date for Section 376 footnote 4`).

---

## Dataset License

All data contributed to this repository is permanently dedicated to the public domain under the [CC0 1.0 Universal License](https://creativecommons.org/publicdomain/zero/1.0/). By submitting a pull request, you agree that your contribution is free of any proprietary copyright or restrictions.
