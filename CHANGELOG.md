# Changelog

All notable changes to Open Laws India are recorded here. Versions follow the dataset release tags.

## v0.3.0 (unreleased)

A point-in-time layer, jurisdictions, a state-amendment bootstrap and a crawler framework, built offline from the v0.2.0 tables plus curated inputs in `curated/` (spec #10). The v0.2.0 tables are unchanged byte for byte. Wording and dates are never guessed.

### Added

- **`indian_act_section_versions`** (config `versions`): bi-temporal slices of every section, valid over `[valid_from, valid_to)`, with `status`, `text_status`, `confidence`, the `amendment_event_ids` that opened each slice, and provenance (`source_url`, `source_sha256`, `retrieved_at`, `parser_version`, `recorded_from = v0.3.0`, `recorded_to = null`). Earlier wording is reverse-reconstructed (one level, confidence 0.8) only from a linked footnote that quotes it, where the edit reverses unambiguously. A new `status = unknown` marks intervals before the first date the wording can be asserted.
- **`amendment_events`** (config `events`): one row per amending operation, from footnotes (Act-level footnotes kept with empty `provisions_affected`) and Act-level repeals, with deterministic IDs.
- **`judicial_events`**: the four PROCUREMENT_PLAN §2.2 seed rulings. A strike-down (IT Act s. 66A, IPC s. 497) or a stay (IPC s. 124A) splits the slices and persists on every later one; `read_down` (IPC s. 377) never changes status.
- **`jurisdictions`**: the Union, 28 States, 8 UTs and 10 historical units, with validity intervals, `successor_of`, `inherited_laws_from`, `legal_basis`, ISO 3166-2:IN codes pinned to the 2023-11-23 change (verified 2026-10-25) and an alias table (e.g. `IN-TG` → `IN-TS`).
- **`state_amendments`**: parsed from the 353 STATE AMENDMENT blocks. Unparseable entries keep `raw_text` with a null type. `valid_to` is the central Act's `repeal_date`, so CrPC, IPC and Evidence Act rows end on 2024-07-01. Section text is unchanged.
- **Crawler** (`scripts/crawlers/`): a polite, resumable HTTP client (PROCUREMENT_PLAN §6: 2 connections per host, ≥500 ms + 200–500 ms jitter, robots.txt, 10/30/60 s backoff on 429/503/504, an honest User-Agent), a content-addressed cache, a WARC/1.1 writer, and a `record` CLI (`python scripts/crawlers/record.py --portal indiacode --urls urls.txt`) for a maintainer to run from a machine that can reach the portals. Standard library only.
- **Build**: a registry of derived tables (`scripts/enrich/registry.py`); `as_of` comes from `--timestamp`, `SOURCE_DATE_EPOCH` or the input manifest, never the clock.
- **Hugging Face**: the five new tables are uploaded (they are listed in `manifest.json`) and have dataset-card configs.
- **Manifest coverage**: events by operation, slices by `status` and `text_status`, judicial events by effect, and jurisdiction and state-amendment counts.

### Validator

New checks in `scripts/validate.py` for v0.3.0 manifests:

- per `(act_id, slug, language)`, slices satisfy `valid_from ≤ valid_to`, with no overlap and no gap;
- `text_status = unavailable` exactly when `full_text` is null;
- every non-first slice is opened by a known event, and every event has a footnote, judicial or repeal source;
- no slice is `in_force` after a strike-down, or during a stay until `stay_lifted`;
- every `act_id`, section, `central_act_id` and jurisdiction code resolves, including the ISO aliases and succession links;
- the coverage is recomputed.

### Coverage

| Metric | Value |
| :--- | :--- |
| Section-version slices | 64,172 (all 36,895 sections; 0 with no slice) |
| By `text_status` (`verbatim_source` / `reconstructed` / `unavailable`) | 36,190 / 31 / 27,951 |
| By `status` (`in_force` / `unknown` / `repealed` / `struck_down` / `stayed`) | 35,630 / 27,243 / 1,295 / 3 / 1 |
| Sections asserted verbatim only from `as_of` (2026-01-01), because of an undated amendment | 22,447 |
| Amendment events | 28,659 |
| By operation (substitution / insertion / omission / renumbering / extension / repeal / other) | 13,575 / 8,228 / 2,738 / 273 / 151 / 3 / 3,691 |
| Events linked to a section / with quoted `old_text` | 13,710 / 8,679 |
| Judicial events (`struck_down` / `stayed` / `read_down`) | 4 (2 / 1 / 1) |
| Jurisdictions (current / historical / ISO aliases) | 47 (37 / 10 / 7) |
| State amendments (parsed / raw) | 617 (560 / 57) from 353 sections |
| State amendments closed on 2024-07-01 | 121 (CrPC 102, IPC 18, Evidence Act 1) |

### Known limits

- Most history before the current text is `unknown`/`unavailable` until gated sources (India Code version history, the e-Gazette) are recorded with the crawler. In a hand check, 19 of 20 sampled reconstructed slices were correct. The exception is A1988-46 s. 10, where the wording matches its footnote but the source prints an implausible w.e.f. date, so the interval is wrong.
- `publication_date`, `commencement_date` and `is_retrospective` are null on every event.
- 4 state-amendment rows have no state code, and 4 have no `[Vide …]` reference.

## v0.2.0

A deterministic enrichment of the v0.1.1 corpus. All v0.1.1 columns are kept unchanged, including the legacy `act_id`, so existing joins keep working.

### Added

- **Acts**: `work_id` (`in-central/act/{year}/{number}`, e.g. `in-central/act/1860/45`), `doc_type` (`act`), `assent_date` (ISO, parsed from `enactment_date`), `repeal_date`, `savings_clause` (e.g. `BNSS s. 531`) and `commencement_date` (null for every Act in this release).
- **Footnotes**: `section_slug` (the section in the same Act that the footnote amends, or null) and `linkage_method` (`inline_marker`, `page_order` or `act_level`). Footnotes that cannot be linked with confidence stay at Act level.
- **Mappings**: `effective_from` (`2024-07-01`) and `applies_by` (`offence_date` for BNS, `proceeding_date` for BNSS and BSA).
- **Manifest**: a `coverage` report with the footnote linkage rate overall, linked and total footnote counts with the rate per Act, link counts by method, and the number of Acts with an `assent_date`.
- **Build**: `scripts/build_dataset.py` regenerates every table, the jsonl archive and the manifest from the frozen v0.1.1 inputs (`scripts/extract_inputs.py`). The output is byte-identical for the same inputs and `--timestamp` (default: `SOURCE_DATE_EPOCH`, else the input manifest's `export_timestamp`; never the current time).
- **CI**: the pytest suite runs on every pull request.

### Changed

- The README licensing note now states s. 52(1)(q)(i)–(iv) of the Copyright Act, 1957 precisely and says that CC0 covers only the project's own contributions. The note is pending counsel review.

### Fixed

- The `w.e.f.` parser now tolerates irregular spacing and separators inside dates (`31-10- 2019`, `1-7-2024`, `1st July, 2024`), and `wef_date` is re-derived for all footnotes. Footnotes with a `w.e.f.` date: 22,490 → 22,674.
- Four v0.1.1 footnotes carried a `wef_date` that is not a calendar date (e.g. `1959-19-01`); it is now null rather than guessed.

### Validator

New checks in `scripts/validate.py`:

- `work_id` is unique;
- no slug collisions per `(act_id, structural_unit, language)`;
- every footnote `section_slug` resolves to a section of the same Act;
- every `repealed_by` (kept unchanged from v0.1.1) resolves to a known Act;
- date columns, including footnote `wef_date`, are real ISO calendar dates;
- the manifest's `coverage` matches values recomputed from the tables.

### Coverage

| Metric | Value |
| :--- | :--- |
| Acts | 861 |
| Sections | 36,895 |
| Footnotes | 28,656 |
| Footnotes with a `w.e.f.` date | 22,674 |
| Footnote linkage rate | 47.84% (0.4784) |
| Links by method (`inline_marker` / `page_order` / `act_level`) | 13,286 / 424 / 14,946 |
| Acts with an `assent_date` | 861 |

## v0.1.1

- Full BNS, BNSS and BSA text, schema-checked validation, and a single source for the Hugging Face sync.

## v0.1.0

- Initial release: 861 Central Acts, 35,836 sections and 28,653 amendment footnotes.
