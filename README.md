---
language:
- en
- hi
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
- akoma-ntoso
size_categories:
- 10K<n<100K
pretty_name: "Open Laws India — Canonical Statutory Corpus"
dataset_info:
  features:
  - name: id
    dtype: string
  - name: act_id
    dtype: string
  - name: section_number
    dtype: string
  - name: slug
    dtype: string
  - name: structural_unit
    dtype: string
  - name: heading
    dtype: string
  - name: full_text
    dtype: string
  - name: chapter_id
    dtype: string
  - name: chapter_name
    dtype: string
  - name: language
    dtype: string
  splits:
  - name: train
    num_bytes: 35000000
    num_examples: 35836
---

# Open Laws India (`kanoonhq/open-laws`)

The complete, open-source, canonical dataset of Indian statutory legislation, maintained by [KanoonHQ](https://kanoonhq.in).

This dataset provides structured, versioned, machine-readable bare acts, sections, amendment footnotes, and criminal law transition mappings (IPC ↔ BNS, CrPC ↔ BNSS, Evidence Act ↔ BSA).

## Dataset Summary

- **Total Acts**: 861 Central Acts (1855–2024)
- **Total Sections/Provisions**: 35,836
- **Statutory Amendment Footnotes**: 28,653 (22,490 with explicit `w.e.f.` commencement dates)
- **Criminal Transition Mappings**: 107 (IPC↔BNS, CrPC↔BNSS, IEA↔BSA)
- **License**: [CC0 1.0 Universal (Public Domain Dedication)](https://creativecommons.org/publicdomain/zero/1.0/)

---

## File Structure

| File | Format | Description |
| :--- | :--- | :--- |
| `indian_central_acts.parquet` | Apache Parquet (zstd) | Metadata for all 861 Central Acts (title, act ID, enactment date, category, status). |
| `indian_central_act_sections.parquet` | Apache Parquet (zstd) | All 35,836 sections with clean text, chapter hierarchy, and canonical slugs. |
| `central_act_footnotes.parquet` | Apache Parquet (zstd) | 28,653 statutory amendment footnotes with parsed Amending Acts and `w.e.f.` dates. |
| `criminal_law_mappings.parquet` | Apache Parquet (zstd) | Transition crosswalk mapping IPC sections to BNS 2023, and CrPC to BNSS 2023. |
| `indian_central_acts_complete.jsonl.gz` | Compressed JSON Lines | Hierarchical complete archive (each line is an Act with nested sections and footnotes). |

---

## Quickstart Usage

### 1. Python (`datasets` library)
```python
from datasets import load_dataset

# Load all sections
sections = load_dataset("kanoonhq/open-laws", data_files="indian_central_act_sections.parquet", split="train")
print(sections[0])

# Search for murder provision in BNS
bns_murder = sections.filter(lambda x: x["act_id"] == "A2023-45" and "murder" in (x["heading"] or "").lower())
print(bns_murder[0]["section_number"], bns_murder[0]["heading"])
```

### 2. DuckDB (Direct SQL over HTTP or local)
```sql
-- Query directly without downloading whole files
SELECT section_number, heading, full_text
FROM 'indian_central_act_sections.parquet'
WHERE act_id = 'A1860-45' AND section_number = 'Section 302.';
```

### 3. Pandas
```python
import pandas as pd

df = pd.read_parquet("indian_central_act_sections.parquet")
print(f"Loaded {len(df)} sections across {df['act_id'].nunique()} acts.")
```

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
  year         = {2026},
  publisher    = {Hugging Face & GitHub},
  url          = {https://github.com/kanoonhq/open-laws},
  doi          = {10.5281/zenodo.kanoonhq.open-laws}
}
```
