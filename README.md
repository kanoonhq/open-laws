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

- **Version**: v0.1.1
- **Total Acts**: 861 Central Acts (1838–2023)
- **Total Sections/Provisions**: 36,895
- **Statutory Amendment Footnotes**: 28,656 (22,490 with explicit `w.e.f.` commencement dates)
- **Criminal Transition Mappings**: 107 key provisions (IPC→BNS, CrPC→BNSS, IEA→BSA)
- **Coverage**: Central Acts only, current text only. Not yet included: Central Acts enacted after the 2023 criminal codes (2023–2026), the Constitution of India, State Acts, subordinate legislation, and historical versions of sections.
- **License**: [CC0 1.0 Universal (Public Domain Dedication)](https://creativecommons.org/publicdomain/zero/1.0/)

---

## File Structure

| File | Config | Description |
| :--- | :--- | :--- |
| `indian_central_acts.parquet` | `acts` | One row per Act: title, act number, enactment date as printed (raw text, e.g. `[6th October, 1860.]`), keyword-inferred category, repeal status (`is_repealed`, `repealed_by`). |
| `indian_central_act_sections.parquet` | `sections` | All 36,895 sections with clean text, chapter hierarchy, and canonical slugs. |
| `central_act_footnotes.parquet` | `footnotes` | 28,656 statutory amendment footnotes with parsed Amending Acts and `w.e.f.` dates. |
| `criminal_law_mappings.parquet` | `mappings` | Curated crosswalk of key provisions: IPC→BNS 2023, CrPC→BNSS 2023 and Indian Evidence Act→BSA 2023. `old_section` is null for provisions new in the 2023 codes; `new_section` is null for provisions with no successor. |
| `indian_central_acts_complete.jsonl.gz` | — | Hierarchical complete archive (each line is an Act with nested sections and footnotes). |
| `manifest.json` | — | Row counts, sizes and SHA-256 checksums for every file. |

Parquet files are zstd-compressed. On the Hugging Face Hub they sit at the repository root; in the GitHub repository they live under `data/`.

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
- Repeal status is a boolean (`is_repealed`, `repealed_by`) without repeal or commencement dates or savings clauses.
- Footnotes are anchored to India Code page numbers (`page_or_anchor`, e.g. `Page 18`), not to sections.
- Sections hold the current consolidated text only; wording as it stood on earlier dates is not yet available.
- The crosswalk covers key provisions only; it is not the full official correspondence table.

---

## Roadmap

[`PROCUREMENT_PLAN.md`](PROCUREMENT_PLAN.md) sets out the expansion: refreshing Central Acts to 2026 and adding the Constitution, a point-in-time layer (amendment events, historical section versions, commencement notifications, court rulings affecting validity), State Acts and state amendments, subordinate legislation, and per-record provenance.

---

## Legal & Copyright Status

Under **Section 52(1)(q) of the Indian Copyright Act, 1957**, it is not an infringement of copyright to reproduce or publish:
- (i) any matter published in an Official Gazette, **except an Act of a Legislature**;
- (ii) an Act of a Legislature, **provided it is reproduced together with commentary or other original matter**;
- (iii) reports of government-appointed committees and commissions laid on the Table of the Legislature, unless prohibited;
- (iv) judgments and orders of courts, tribunals and other judicial authorities, unless prohibited.

Statutory text here is reproduced in reliance on these provisions, alongside original matter (metadata, structure, parsed footnotes, mappings). KanoonHQ's own contributions are dedicated to the public domain under **CC0 1.0 Universal**; the packaging code and schemas are licensed under the **MIT License**. See [`LICENSE`](LICENSE) and [`PROCUREMENT_PLAN.md` §9](PROCUREMENT_PLAN.md#9-licensing-note-to-be-reviewed-before-v020). This is not legal advice.

---

## Citation (BibTeX)

```bibtex
@dataset{kanoonhq_open_laws_2026,
  author       = {KanoonHQ Team},
  title        = {Open Laws India: Canonical Machine-Readable Indian Statutory Corpus},
  version      = {v0.1.1},
  year         = {2026},
  publisher    = {Hugging Face & GitHub},
  url          = {https://github.com/kanoonhq/open-laws}
}
```
