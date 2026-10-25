# Changelog

All notable changes to Open Laws India are recorded here. Versions follow the dataset release tags.

## v0.2.0 (unreleased)

A deterministic enrichment of the v0.1.1 corpus. All v0.1.1 columns are kept unchanged, including the legacy `act_id`, so existing joins keep working. Counts marked `<...>` are filled in when the release is built.

### Added

- **Acts**: `work_id` (`in-central/act/{year}/{number}`, e.g. `in-central/act/1860/45`), `doc_type` (`act`), `assent_date` (ISO, parsed from `enactment_date`), `repeal_date`, `savings_clause` (e.g. `BNSS s. 531`) and `commencement_date` (null for every Act in this release).
- **Footnotes**: `section_slug` (the section in the same Act that the footnote amends, or null) and `linkage_method` (`inline_marker`, `page_order` or `act_level`). Footnotes that cannot be linked with confidence stay at Act level.
- **Mappings**: `effective_from` (`2024-07-01`) and `applies_by` (`offence_date` for BNS, `proceeding_date` for BNSS and BSA).
- **Manifest**: a `coverage` report with the footnote linkage rate overall and per Act, link counts by method, and the number of Acts with an `assent_date`.
- **Build**: `scripts/build_dataset.py` regenerates every table, the jsonl archive and the manifest from the frozen v0.1.1 inputs (`scripts/extract_inputs.py`). The output is byte-identical for the same inputs and `--timestamp`.
- **CI**: the pytest suite runs on every pull request.

### Changed

- `repealed_by` is now parsed from `repeal_reason` for repealed Acts.
- The README licensing note now states s. 52(1)(q)(i)–(iv) of the Copyright Act, 1957 precisely and says that CC0 covers only the project's own contributions. The note is pending counsel review.

### Fixed

- The `w.e.f.` parser now tolerates irregular spacing and separators inside dates (`31-10- 2019`, `1-7-2024`, `1st July, 2024`), and `wef_date` is re-derived for all footnotes. Footnotes with a `w.e.f.` date: 22,490 → `<WEF_COUNT>`.

### Validator

New checks in `scripts/validate.py`:

- `work_id` is unique;
- no slug collisions per `(act_id, structural_unit, language)`;
- every footnote `section_slug` resolves to a section of the same Act;
- every `repealed_by` resolves to a known Act;
- date columns are ISO-formatted;
- the manifest's `coverage` matches values recomputed from the tables.

### Coverage

| Metric | Value |
| :--- | :--- |
| Acts | `<ACT_COUNT>` |
| Sections | `<SECTION_COUNT>` |
| Footnotes | `<FOOTNOTE_COUNT>` |
| Footnotes with a `w.e.f.` date | `<WEF_COUNT>` |
| Footnote linkage rate | `<LINKAGE_RATE>` |
| Links by method (`inline_marker` / `page_order` / `act_level`) | `<INLINE_MARKER>` / `<PAGE_ORDER>` / `<ACT_LEVEL>` |
| Acts with an `assent_date` | `<ASSENT_DATE_COUNT>` |

## v0.1.1

- Full BNS, BNSS and BSA text, schema-checked validation, and a single source for the Hugging Face sync.

## v0.1.0

- Initial release: 861 Central Acts, 35,836 sections and 28,653 amendment footnotes.
