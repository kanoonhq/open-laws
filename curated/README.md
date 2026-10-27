# Curated sources

Hand-maintained build inputs for the v0.3.0 time layer (spec #10): small CSV or
JSON files such as jurisdictions, ISO 3166-2:IN aliases and judicial events.

- Every row carries a `source_url` for the authority it was taken from.
- A value that cannot be verified is marked `unverified`, never guessed.
- When a value was checked against a secondary source (a mirror of the
  authority) rather than the authority itself, `source_url` still names the
  authority and the file header says what was actually consulted, and when.
- Changes are reviewed like code.

Derived-table stage modules (`scripts/enrich/`) read these files through
`enrich.CURATED_DIR`.

## Files

- `README.md`: this file.
- `jurisdictions.csv` and `iso_aliases.csv` (ticket #13): built into
  `jurisdictions.parquet` by `scripts/enrich/jurisdictions.py`. Their headers pin
  the ISO 3166-2:IN version and the verification date; each row cites the corpus
  provisions (`legal_basis`) that establish its dates and succession links.
- `judicial_events.json` (ticket #14): the court rulings that change whether a
  provision is enforceable (the four PROCUREMENT_PLAN seed rulings), built into
  `judicial_events.parquet` by `scripts/enrich/judicial_events.py`. Each ruling
  cites its Act as `Act N of YYYY` (resolved against the acts table), the
  section slug, court, case name, citations where certain, decision date,
  effect and `source_url`.

## ISO 3166-2:IN verification

The authority for ISO 3166-2:IN codes is the ISO Online Browsing Platform
(<https://www.iso.org/obp/ui/#iso:code:3166:IN>), so every ISO-coded row of
`jurisdictions.csv` and every row of `iso_aliases.csv` cites it as `source_url`.
The codes and change history were **cross-checked via en.wikipedia
ISO_3166-2:IN on 2026-10-25** (a secondary mirror of the OBP list and its
change history; header key `iso_cross_checked_via`). The OBP itself was not
consulted directly, so `iso_status = verified` means "cross-checked via that
mirror", not direct ISO verification. Re-check against the OBP before relying
on a code for anything beyond name/code mapping.

## Jurisdiction start dates (`valid_from`)

`valid_from` is set only from a provision of an Act in this corpus
(`legal_basis`). It is left empty for units that existed before 1956-11-01
when no start date can be cited from the corpus:

- `IN-HIST-AP` starts 1953-10-01: the Andhra State Act, 1953 (A1953-30 s. 2(a)
  appointed day, s. 3 forming the State of Andhra).
- `IN-HIST-BIHAR`, `IN-HIST-UP`: continuous with the pre-Constitution
  Provinces, whose laws continued under Article 372. 1950-01-26 (the
  Constitution's commencement) is when they became States, not when the units
  began; the Constitution is not in the corpus, and a 1950 start would wrongly
  unmap earlier State Act references.
- `IN-HIST-JK`: continuous with the pre-1950 State of Jammu and Kashmir; no
  start date in a corpus Act.
- `IN-TN`: the State of Madras existed before 1950. The Madras State
  (Alteration of Name) Act, 1968 (Act 53 of 1968) renamed it, which does not
  start a new unit, and that Act is not in the corpus (the rename date is in
  `notes`).
- `IN-HP`: the row covers Himachal Pradesh as a Chief Commissioner's Province /
  Union territory as well as a State (state amendment references from 1953 map
  to it). Statehood under the State of Himachal Pradesh Act, 1970 (A1970-53)
  is on an appointed day fixed by notification (s. 2(b)), so the date
  (1971-01-25) is not citable from the corpus text, and it would not be this
  row's start in any case.
- Other current States without a `valid_from` (e.g. Assam, West Bengal,
  Rajasthan, Odisha) likewise pre-date 1956-11-01.

## Golden set format

The golden set (PROCUREMENT_PLAN §7, gate 5) is a JSON array of hand-verified
(provision, date) → text pairs, each an object matching
[`schemas/golden_pair.schema.json`](../schemas/golden_pair.schema.json):
`id` (`{act_id}:{slug}:{as_of}`), `act_id`, `slug`, `language` (`en`),
`as_of`, `expected_text`, `source_url` (the authoritative text checked
against), `verified_by` (a GitHub handle, never an email address),
`verified_on` and `notes`. When pairs are verified they go in
`curated/golden_set.json`; none ship in v0.3.0 (spec #10 adds only the format).
`tests/fixtures/golden_set/example.json` is a format example, not golden data.
