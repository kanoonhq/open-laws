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
- config_name: versions
  data_files: indian_act_section_versions.parquet
- config_name: events
  data_files: amendment_events.parquet
- config_name: judicial_events
  data_files: judicial_events.parquet
- config_name: jurisdictions
  data_files: jurisdictions.parquet
- config_name: state_amendments
  data_files: state_amendments.parquet
---

# Open Laws India (`kanoonhq/open-laws`)

An open, machine-readable corpus of Indian Central legislation, maintained by [KanoonHQ](https://kanoonhq.in), and growing towards the complete, point-in-time statutory corpus of India (see [Roadmap](#roadmap)).

This dataset provides structured, versioned, machine-readable bare acts, sections, amendment footnotes, and criminal law transition mappings (IPC ↔ BNS, CrPC ↔ BNSS, Evidence Act ↔ BSA).

> **Not legal advice.** This is a machine-readable compilation of statutory text. Verify provisions against the Official Gazette before relying on them, and always read `text_status` and `status` on a point-in-time result (see [Time layer](#time-layer-v030)).

## Dataset Summary

- **Version**: v0.3.0 (see [`CHANGELOG.md`](CHANGELOG.md))
- **Total Acts**: 861 Central Acts (1838–2023)
- **Total Sections/Provisions**: 36,895
- **Statutory Amendment Footnotes**: 28,656 (22,674 with explicit `w.e.f.` dates; 47.84% linked to a section)
- **Criminal Transition Mappings**: 107 key provisions (IPC→BNS, CrPC→BNSS, IEA→BSA)
- **Time layer (v0.3.0)**: 28,659 amendment events, 64,172 section-version slices, 4 judicial events, 47 jurisdictions and 617 state amendments. Most history before the current text is `unknown`/`unavailable` until gazette sources arrive; see [Time layer](#time-layer-v030).
- **Coverage**: Central Acts only. Not yet included: Central Acts enacted after the 2023 criminal codes (2023–2026), the Constitution of India, State Acts, subordinate legislation, and the historical wording of most sections.
- **License**: [CC0 1.0 Universal (Public Domain Dedication)](https://creativecommons.org/publicdomain/zero/1.0/)

---

## File Structure

| File | Config | Description |
| :--- | :--- | :--- |
| `indian_central_acts.parquet` | `acts` | One row per Act: `work_id`, legacy `act_id`, `doc_type`, title, act number, enactment date as printed (raw text, e.g. `[6th October, 1860.]`) and parsed as `assent_date`, keyword-inferred category, repeal status (`is_repealed`, `repeal_date`, `repealed_by`, `savings_clause`). |
| `indian_central_act_sections.parquet` | `sections` | All 36,895 sections with clean text, chapter hierarchy, and canonical slugs. |
| `central_act_footnotes.parquet` | `footnotes` | 28,656 statutory amendment footnotes with parsed Amending Acts, `w.e.f.` dates and, where the evidence allows, the `section_slug` they amend. |
| `criminal_law_mappings.parquet` | `mappings` | Curated crosswalk of key provisions: IPC→BNS 2023, CrPC→BNSS 2023 and Indian Evidence Act→BSA 2023. `old_section` is null for provisions new in the 2023 codes; `new_section` is null for provisions with no successor. Each row carries `effective_from` and `applies_by`. |
| `indian_act_section_versions.parquet` | `versions` | Bi-temporal slices of every section: the wording (or its absence) valid over `[valid_from, valid_to)`, with `status`, `text_status`, `confidence` and provenance. 64,172 slices covering all 36,895 sections. |
| `amendment_events.parquet` | `events` | One row per amending operation (28,659), built from the footnotes and Act-level repeals. |
| `judicial_events.parquet` | `judicial_events` | Curated rulings that strike down, stay or read down a provision (4 seed rows). |
| `jurisdictions.parquet` | `jurisdictions` | The Union, 28 States, 8 UTs and 10 historical units (47 rows) with validity intervals, succession links and ISO 3166-2:IN codes and aliases. |
| `state_amendments.parquet` | `state_amendments` | 617 state amendments to Central Acts, parsed from the 353 STATE AMENDMENT blocks in section text. |
| `indian_central_acts_complete.jsonl.gz` | — | Hierarchical complete archive (each line is an Act with nested sections and footnotes). |
| `manifest.json` | — | Row counts, sizes and SHA-256 checksums for every file, plus a `coverage` report (footnote linkage; events by operation; slices by `status` and `text_status`; judicial events by effect; jurisdiction and state-amendment counts). |

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
| `acts` | `repealed_by` | Existing v0.1.1 column, kept unchanged. The validator checks that it resolves to a known Act. |
| `acts` | `savings_clause` | The transition provision for pending matters, e.g. `BNSS s. 531`. |
| `footnotes` | `section_slug` | Slug of the section the footnote amends, always in the same Act; null when the footnote could not be linked. |
| `footnotes` | `linkage_method` | How the link was made: `inline_marker` (the section's inline marker matches the footnote number on the aligned page), `page_order` (the footnote sits between two `inline_marker` links to the same section on the same page) or `act_level` (not linked; `section_slug` is null). When the evidence is unclear, no link is made. |
| `mappings` | `effective_from` | `2024-07-01` for every mapping, the date the 2023 codes came into force. |
| `mappings` | `applies_by` | Which date selects the code: `offence_date` for BNS (`A2023-45`) mappings, `proceeding_date` for BNSS and BSA mappings. |

`wef_date` is re-derived for all footnotes by a parser that tolerates irregular spacing and separators (`31-10- 2019`, `1-7-2024`, `1st July, 2024`), so fewer `w.e.f.` dates are dropped than in v0.1.1.

## Time layer (v0.3.0)

v0.3.0 adds a point-in-time layer, built offline from the v0.2.0 tables plus small curated inputs in [`curated/`](curated/). Nothing in it is guessed: where the wording or a date cannot be shown from the sources, the row says so.

> **Honest caveat.** The only verbatim text the corpus has is the v0.1.1 snapshot of today's consolidated wording. Earlier wording is recovered only where a footnote quotes it and the edit reverses unambiguously (31 slices). For most sections, the history before the current text is `status = unknown` with `text_status = unavailable` (27,243 slices), and 22,447 sections can be asserted verbatim only from the build's `as_of` date (2026-01-01), because their Act has an undated amendment. This will improve once gated sources (India Code version history and the e-Gazette) are recorded with the crawler. A point-in-time query that returns `unknown` or `unavailable` means "not known from this dataset", not "not in force".

### Tables

**`indian_act_section_versions`** (config `versions`): one row per slice of a section, valid over `[valid_from, valid_to)`. `valid_to` is null on the open-ended last slice. Slices never overlap per `(act_id, slug, language)`, and the chain has no gaps, so a date returns at most one row. Each row has `id` (`{act_id}:{slug}:{valid_from}`), `version_number`, `heading`, `full_text`, `status`, `text_status`, `confidence`, and `amendment_event_ids` (the events or rulings that opened the slice). It also has provenance: `source_url`, `source_sha256`, `retrieved_at`, `parser_version`, and `recorded_from`/`recorded_to` (`v0.3.0`/null on first publication; a later correction supersedes a row instead of editing it).

**`amendment_events`** (config `events`): one row per amending operation. Each row has an `operation` (`substitution`, `insertion`, `omission`, `renumbering`, `extension`, `repeal`, `other`), the `amending_citation` (e.g. `Act 13 of 2013, s. 9`) and `amending_instrument_id` when that Act is in the corpus, `wef_date`, the quoted `old_text` when the footnote quotes exactly one span, `footnote_ids`, and `provisions_affected` (`[slug]` for a linked footnote, `[]` for an Act-level one, so no change is lost). `publication_date` and `commencement_date` are null until gazette sources exist, and `is_retrospective` is null unless both of its dates are known. IDs are deterministic, e.g. `A1860-45:ev:A2013-13:s9`, with a numeric suffix on collision.

**`judicial_events`** (config `judicial_events`): the four seed rulings in PROCUREMENT_PLAN §2.2. `struck_down` (IT Act s. 66A from 2015-03-24; IPC s. 497 from 2018-09-27) and `stayed` (IPC s. 124A from 2022-05-11) split a section's slices at `decision_date`. They persist on every later slice: a strike-down is final, and a stay lasts until a `stay_lifted` ruling. `read_down` (IPC s. 377) and `upheld` are recorded but never change `status`, so the enacted wording stays in force.

### Reading `status` and `text_status`

| `text_status` | `confidence` | Meaning |
| :--- | :--- | :--- |
| `verbatim_source` | 1.0 | The v0.1.1 text, verbatim. Asserted only from a date at which it can be shown to stand. |
| `reconstructed` | 0.8 | Reverse-reconstructed from one footnote that quotes the replaced wording (`Subs. … for "…"`, an `Ins.` span removed, or a `***` omission restored). One level back only. |
| `unavailable` | 0.0 | The wording for this interval is not known. `full_text` and `heading` are null. |

| `status` | Meaning |
| :--- | :--- |
| `in_force` | The provision is in force over the interval. |
| `unknown` | The interval comes before the first date from which the section's wording can be asserted: an amendment of the Act, linked or not, or undated, may have changed it. Always paired with `unavailable`. |
| `struck_down`, `stayed` | A ruling in `judicial_events` affects the provision. |
| `repealed` | The Act was repealed (e.g. IPC, CrPC and Evidence Act from 2024-07-01). The slice keeps the last verbatim text. |

The schema also reserves `not_commenced`, `omitted`, `expired` and `ordinance_lapsed`; no v0.3.0 row uses them. Consumers must surface both columns: `reconstructed` text is labelled, `unavailable` returns no text, and `unknown` is not evidence that the provision was in force.

### Point-in-time query (PROCUREMENT_PLAN §3)

Dates are stored as ISO `YYYY-MM-DD` strings, so cast them (or compare as strings) in DuckDB:

```sql
-- IPC s. 376 as of 15 August 2000
SELECT act_id, section_number, heading, full_text,
       status, text_status, confidence, amendment_citation
FROM 'hf://datasets/kanoonhq/open-laws/indian_act_section_versions.parquet'
WHERE act_id = 'A1860-45'
  AND slug = '376'
  AND CAST(valid_from AS DATE) <= DATE '2000-08-15'
  AND (valid_to IS NULL OR CAST(valid_to AS DATE) > DATE '2000-08-15')
  AND recorded_to IS NULL            -- latest dataset assertion
ORDER BY valid_from DESC
LIMIT 1;
```

On the v0.3.0 data this returns one row: `status = unknown`, `text_status = unavailable` over [1860-10-06, 2024-07-01), because the IPC's footnotes carry undated amendments. Using the same query, IT Act s. 66A (`A2000-21`, slug `66a`) on 2016-01-01 is `struck_down`, and IPC s. 124A (slug `124a`) on 2023-01-01 is `stayed`.

### Jurisdictions and state amendments

**`jurisdictions`** has one row per code: `IN-CENTRAL`, the current States and UTs under their ISO 3166-2:IN codes (e.g. `IN-MH`), and historical units such as Bombay State, undivided Punjab, UP, MP, Bihar and Andhra Pradesh, and the State of J&K (`IN-HIST-…`). `valid_from`/`valid_to` bound each unit; `valid_from` is null for units that existed before 1956-11-01 with no start date citable from the corpus (earlier history is not modelled); the State of Andhra starts 1953-10-01 (Andhra State Act, 1953). `successor_of` and `inherited_laws_from` follow the reorganisations (Bombay 1960, Punjab 1966, the 2000 splits, AP/Telangana 2014, J&K 2019), and `legal_basis` cites the corpus provisions behind each row. `iso_aliases` resolves former or alternate codes (e.g. `IN-TG` → `IN-TS`, `IN-CT` → `IN-CG`). The pinned ISO version and the verification date are in `iso_version` and `iso_verified_on`; codes cite the ISO Online Browsing Platform as `source_url` but were cross-checked via a secondary mirror (en.wikipedia ISO_3166-2:IN), not the OBP directly. `iso_status` is `unverified` where a code could not be checked.

**`state_amendments`** has one row per state entry in a section's STATE AMENDMENT block: `central_act_id`, the host `section_id`/`section_slug`, the amended `section_number` where it is stated, `state_name` as printed and its `state_jurisdiction` code, the `[Vide …]` `state_act_reference`, `amendment_type` (`substitution`, `insertion`, `omission`, `proviso`) and `amended_text`. 560 of the 617 rows are fully parsed. The other 57 keep their `raw_text` with a null type or state code (mostly entries that make several kinds of change at once). `valid_to` is the central Act's `repeal_date`, so CrPC, IPC and Evidence Act state amendments (121 rows) end on 2024-07-01 and do not carry over to the 2023 codes. A state name maps only to the unit that existed for the whole year of its reference (e.g. "Madhya Pradesh Act 21 of 1995" → `IN-HIST-MP`). The STATE AMENDMENT text also stays in the section text, unchanged.

### Recording portal snapshots (crawler)

The portals (India Code, e-Gazette) block the build environment, so the gated sources are captured with a polite, resumable recorder that a maintainer runs from a machine that can reach them. It uses only the standard library and follows PROCUREMENT_PLAN §6. Each host gets at most 2 connections and at least 500 ms (plus 200–500 ms of jitter) between requests. It honours robots.txt, backs off 10 s → 30 s → 60 s on 429/503/504, and sends an honest User-Agent naming this repository; a browser User-Agent is refused, never spoofed. Check the portal's terms before crawling it.

```bash
# urls.txt: one URL per line; blank lines and # comments are ignored
python scripts/crawlers/record.py --portal indiacode --urls urls.txt \
    [--cache-root .cache] [--user-agent "open-laws-crawler/0.3.0 (+https://github.com/kanoonhq/open-laws)"] [--workers 2]
```

The output goes to `.cache/{portal}/` (gitignored):

- `responses/{request sha256}.json`: the response metadata.
- `bodies/{body sha256}`: the raw response bodies.
- `warc/{sha256}.warc.gz`: WARC/1.1 request and response records, one gzip member each.
- `index.jsonl`: one line per URL, with `status`, `source_sha256`, `retrieved_at` and `warc_file`.

A re-run makes no repeat requests for URLs already cached, so an interrupted crawl resumes where it stopped. The command exits non-zero if any URL failed. Portal-specific parsers will come once recorded snapshots exist.

### Building from source

The tables are a deterministic enrichment of the frozen v0.1.1 release (the `data/` tree at commit `7222593`). From a clone of the GitHub repository:

```bash
python scripts/extract_inputs.py    # git archive 7222593 data/ -> .cache/inputs/v0.1.1/
python scripts/build_dataset.py --input-dir .cache/inputs/v0.1.1 --output-dir data \
    --timestamp 2026-01-01T00:00:00+00:00
python scripts/validate.py
```

Given the same inputs and `--timestamp` (default: `SOURCE_DATE_EPOCH`, else the input manifest's `export_timestamp`; never the current time), the output is byte-identical, so anyone can reproduce the SHA-256 values in `manifest.json`. The validator checks the schemas and date formats, `work_id` uniqueness, slug collisions per `(act_id, structural_unit, language)`, that each footnote's `section_slug` resolves to a section of the same Act, that `repealed_by` resolves to a known Act, and that the manifest's `coverage` matches recomputed values. For v0.3.0 it also enforces the time-layer invariants: per `(act_id, slug, language)`, slices satisfy `valid_from ≤ valid_to` with no overlap or gap; `text_status = unavailable` exactly when `full_text` is null; every later slice is opened by a known event, and every event has a source; no slice is `in_force` after a strike-down or during a stay; and every Act, section and jurisdiction code (including the ISO aliases) resolves.

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
- Sections hold the current consolidated text. In `indian_act_section_versions`, only 31 earlier slices have reconstructed wording; most earlier intervals are `unknown`/`unavailable`, and 22,447 sections are asserted verbatim only from 2026-01-01 (the build's `as_of`), until gazette and India Code version sources are recorded.
- `amendment_events` has no `publication_date` or `commencement_date` yet, so `is_retrospective` is always null. `judicial_events` holds only the four seed rulings.
- `state_amendments.source_url` cites the frozen v0.1.1 sections-table row the entry was parsed from (the corpus records no per-section portal URL), and `effective_date` is set only where a `(w.e.f. …)` date is printed with the reference (20 rows).
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
  version      = {v0.3.0},
  year         = {2026},
  publisher    = {Hugging Face & GitHub},
  url          = {https://github.com/kanoonhq/open-laws}
}
```
