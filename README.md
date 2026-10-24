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

The complete, open-source, canonical dataset of Indian statutory legislation, maintained by [KanoonHQ](https://kanoonhq.in).

This dataset provides structured, versioned, machine-readable bare acts, sections, amendment footnotes, and criminal law transition mappings (IPC ↔ BNS, CrPC ↔ BNSS, Evidence Act ↔ BSA).

## Dataset Summary

- **Version**: v0.1.1
- **Total Acts**: 861 Central Acts (1838–2023)
- **Total Sections/Provisions**: 36,895
- **Statutory Amendment Footnotes**: 28,656 (22,490 with explicit `w.e.f.` commencement dates)
- **Criminal Transition Mappings**: 107 key provisions (IPC→BNS, CrPC→BNSS, IEA→BSA)
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
- `category` is inferred from keywords in the title.
- The crosswalk covers key provisions only; it is not the full official correspondence table.

---

## Legal & Copyright Status

Under **Section 52(1)(q) of the Indian Copyright Act, 1957**, the reproduction or publication of:
- Any Act of a Legislature;
- Any matter published in the Official Gazette;
- Any judicial judgment or court order;
**does not constitute infringement of copyright**.

The statutory text and public domain metadata are dedicated to the public domain under **CC0 1.0 Universal**. The packaging code and schemas are licensed under the **MIT License**.

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
