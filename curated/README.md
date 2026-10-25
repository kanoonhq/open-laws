# Curated sources

Hand-maintained build inputs for the v0.3.0 time layer (spec #10): small CSV or
JSON files such as jurisdictions, ISO 3166-2:IN aliases and judicial events.

- Every row carries a `source_url` for the authority it was taken from.
- A value that cannot be verified is marked `unverified`, never guessed.
- Changes are reviewed like code.

Derived-table stage modules (`scripts/enrich/`) read these files through
`enrich.CURATED_DIR`.
