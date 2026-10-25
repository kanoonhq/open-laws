---
language:
- en
license: cc0-1.0
task_categories:
- text-retrieval
- question-answering
- text-classification
tags:
- law
- legal
- india
- bare-acts
- statutes
- bns
- bnss
- bsa
- ipc
- crpc
size_categories:
- 10K<n<100K
pretty_name: "Open Laws India — Canonical Statutory Corpus"
configs:
- config_name: sections
  data_files: indian_central_act_sections.parquet
  default: true
- config_name: acts
  data_files: indian_central_acts.parquet
- config_name: footnotes
  data_files: central_act_footnotes.parquet
- config_name: mappings
  data_files: criminal_law_mappings.parquet
---

# Open Laws India (`kanoonhq/open-laws`)

An open, machine-readable corpus of Indian Central legislation, maintained by [KanoonHQ](https://kanoonhq.in), and growing towards the complete, point-in-time statutory corpus of India (see [Roadmap](#roadmap)).

This dataset provides structured, versioned, machine-readable bare acts, sections, amendment footnotes, and criminal law transition mappings (IPC ↔ BNS, CrPC ↔ BNSS, Evidence Act ↔ BSA).

> **Not legal advice.** This is a machine-readable compilation of current text. Verify provisions against the Official Gazette before relying on them.

## Dataset Summary

- **Version**: v0.2.0 (see [`CHANGELOG.md`](CHANGELOG.md))
- **Total Acts**: 861 Central Acts (1838–2023)
- **Total Sections/Provisions**: 36,895
- **Statutory Amendment Footnotes**: 28,656 (22,674 with explicit `w.e.f.` dates; 49.88% linked to a section)
- **Criminal Transition Mappings**: 107 key provisions (IPC→BNS, CrPC→BNSS, IEA→BSA)
- **Coverage**: Central Acts only, current text only. Not yet included: Central Acts enacted after the 2023 criminal codes (2023–2026), the Constitution of India, State Acts, subordinate legislation, and historical versions of sections.
- **License**: [CC0 1.0 Universal (Public Domain Dedication)](https://creativecommons.org/publicdomain/zero/1.0/)

---

## File Structure

| File | Config | Description |
| :--- | :--- | :--- |
| `indian_central_acts.parquet` | `acts` | One row per Act: `work_id`, legacy `act_id`, `doc_type`, title, act number, enactment date as printed (raw text, e.g. `[6th October, 1860.]`) and parsed as `assent_date`, keyword-inferred category, repeal status (`is_repealed`, `repeal_date`, `repealed_by`, `savings_clause`). |
| `indian_central_act_sections.parquet` | `sections` | All 36,895 sections with clean text, chapter hierarchy, and canonical slugs. |
| `central_act_footnotes.parquet` | `footnotes` | 28,656 statutory amendment footnotes with parsed Amending Acts, `w.e.f.` dates and, where the evidence allows, the `section_slug` they amend. |
| `criminal_law_mappings.parquet` | `mappings` | Curated crosswalk of key provisions: IPC→BNS 2023, CrPC→BNSS 2023 and Indian Evidence Act→BSA 2023. `old_section` is null for provisions new in the 2023 codes; `new_section` is null for provisions with no successor. Each row carries `effective_from` and `applies_by`. |
| `indian_central_acts_complete.jsonl.gz` | — | Hierarchical complete archive (each line is an Act with nested sections and footnotes). |
| `manifest.json` | — | Row counts, sizes and SHA-256 checksums for every file, plus a `coverage` report (footnote linkage rate overall and per Act, links by method, Acts with an `assent_date`). |

Parquet files are zstd-compressed. On the Hugging Face Hub they sit at the repository root; in the GitHub repository they live under `data/`.

### Columns added in v0.2.0

Every v0.1.1 column is kept unchanged, including the legacy `act_id` (`A1860-45`), so existing joins keep working. New columns are null where the value is unknown.

| Table | Column | Description |
| :--- | :--- | :--- |
| `acts` | `work_id` | Jurisdiction-qualified ID, `in-central/act/{year}/{number}` with no zero-padding (e.g. `in-central/act/1860/45`). Unique; pattern `^in-[a-z]+/[a-z_]+/[0-9]{4}/[0-9A-Za-z-]+$`. |
| `acts` | `doc_type` | Instrument type. `act` for every current row. |
| `acts` | `assent_date` | ISO date parsed from `enactment_date`; the raw string is kept. |
| `acts` | `commencement_date` | Null for every Act in v0.2.0. The column exists so the schema stays stable until it is filled. |
| `acts` | `repeal_date` | ISO date of repeal, parsed from `repeal_reason` for repealed Acts. |
| `acts` | `repealed_by` | Existing column, now parsed from `repeal_reason` for repealed Acts. It always resolves to a known Act. |
| `acts` | `savings_clause` | The transition provision for pending matters, e.g. `BNSS s. 531`. |
| `footnotes` | `section_slug` | Slug of the section the footnote amends, always in the same Act; null when the footnote could not be linked. |
| `footnotes` | `linkage_method` | How the link was made: `inline_marker` (the section's inline marker matches the footnote number on the aligned page), `page_order` (the footnote sits between linked neighbours on the same section) or `act_level` (not linked; `section_slug` is null). When the evidence is unclear, no link is made. |
| `mappings` | `effective_from` | `2024-07-01` for every mapping, the date the 2023 codes came into force. |
| `mappings` | `applies_by` | Which date selects the code: `offence_date` for BNS (`A2023-45`) mappings, `proceeding_date` for BNSS and BSA mappings. |

`wef_date` is re-derived for all footnotes by a parser that tolerates irregular spacing and separators (`31-10- 2019`, `1-7-2024`, `1st July, 2024`), so fewer `w.e.f.` dates are dropped than in v0.1.1.

### Building from source

The tables are a deterministic enrichment of the frozen v0.1.1 release (the `data/` tree at commit `7222593`). From a clone of the GitHub repository:

```bash
python scripts/extract_inputs.py    # git archive 7222593 data/ -> .cache/inputs/v0.1.1/
python scripts/build_dataset.py --input-dir .cache/inputs/v0.1.1 --output-dir data \
    --timestamp 2026-01-01T00:00:00+00:00
python scripts/validate.py
```

Given the same inputs and `--timestamp`, the output is byte-identical, so anyone can reproduce the SHA-256 values in `manifest.json`. The validator checks the schemas and date formats, `work_id` uniqueness, slug collisions per `(act_id, structural_unit, language)`, that each footnote's `section_slug` resolves to a section of the same Act, that `repealed_by` resolves to a known Act, and that the manifest's `coverage` matches recomputed values.

---

## Quickstart Usage

### 1. Python (`datasets` library)
```python
from datasets import load_dataset

sections = load_dataset("kanoonhq/open-laws", "sections", split="train")
mappings = load_dataset("kanoonhq/open-laws", "mappings", split="train")

# Punishment for murder in the Bharatiya Nyaya Sanhita (BNS section 103)
bns_murder = sections.filter(
    lambda x: x["act_id"] == "A2023-45" and x["heading"] == "Punishment for murder."
)
print(bns_murder[0]["section_number"], bns_murder[0]["heading"])
```

### 2. DuckDB (SQL over the Hub, no download)
```sql
SELECT section_number, heading, full_text
FROM 'hf://datasets/kanoonhq/open-laws/indian_central_act_sections.parquet'
WHERE act_id = 'A1860-45' AND section_number = 'Section 302.';
```

### 3. Pandas (from a clone of the GitHub repository)
```python
import pandas as pd

df = pd.read_parquet("data/indian_central_act_sections.parquet")
print(f"Loaded {len(df)} sections across {df['act_id'].nunique()} acts.")
```

---

## Known Limitations

- Text of the Bharatiya Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita and Bharatiya Sakshya Adhiniyam (2023) is parsed from the Gazette of India PDFs; their Schedules are not included.
- Of the 2023 Central Acts, only the BNS, BNSS and BSA are included; no Acts from 2024–2026 are present yet.
- `category` is inferred from keywords in the title; 697 of 861 Acts fall back to `general`.
- `commencement_date` is null for every Act. Repeal dates and savings clauses are parsed only where `repeal_reason` states them.
- Footnotes that cannot be linked to a section with confidence stay at Act level (`linkage_method = act_level`, `section_slug` null) and stay anchored to India Code page numbers (`page_or_anchor`, e.g. `Page 18`).
- Sections hold the current consolidated text only; wording as it stood on earlier dates is not yet available.
- The crosswalk covers key provisions only; it is not the full official correspondence table.

---

## Roadmap

[`PROCUREMENT_PLAN.md`](PROCUREMENT_PLAN.md) sets out the expansion: refreshing Central Acts to 2026 and adding the Constitution, a point-in-time layer (amendment events, historical section versions, commencement notifications, court rulings affecting validity), State Acts and state amendments, subordinate legislation, and per-record provenance.

---

## Legal & Copyright Status

> **Pending counsel review.** Counsel has not yet reviewed this note, and it may change. It is not legal advice.

Section 52(1)(q) of the Copyright Act, 1957 is not a blanket exemption. Its four sub-clauses cover different material:
- **s. 52(1)(q)(i)** covers matter published in the Official Gazette, **except an Act of a Legislature**.
- **s. 52(1)(q)(ii)** covers an Act of a Legislature **on the condition that it is reproduced together with commentary or other original matter**.
- **s. 52(1)(q)(iii)** covers reports of government-appointed committees and commissions laid on the Table of the Legislature, unless their reproduction is prohibited.
- **s. 52(1)(q)(iv)** covers judgments and orders of courts and tribunals, unless their reproduction is prohibited.

Government works otherwise carry government copyright (s. 17(d), s. 28). The statutory text here relies on s. 52(1)(q)(ii) and is published together with original matter: structure, metadata, IDs, parsed footnotes and their section links, dates and mappings.

**CC0 1.0 Universal applies to the project's own contributions only** (structure, metadata, annotations, IDs and reconstructions). It does not license the underlying statutory text. The packaging code and schemas are licensed under the **MIT License**. See [`LICENSE`](LICENSE) and [`PROCUREMENT_PLAN.md` §9](PROCUREMENT_PLAN.md#9-licensing-note-to-be-reviewed-before-v020).

---

## Citation (BibTeX)

```bibtex
@dataset{kanoonhq_open_laws_2026,
  author       = {KanoonHQ Team},
  title        = {Open Laws India: Canonical Machine-Readable Indian Statutory Corpus},
  version      = {v0.2.0},
  year         = {2026},
  publisher    = {Hugging Face & GitHub},
  url          = {https://github.com/kanoonhq/open-laws}
}
```
