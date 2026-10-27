"""The dataset's file names and release constants, shared by build_dataset.py,
validate.py, extract_inputs.py, the enrich stages and the crawler."""

VERSION = "v0.3.0"  # the dataset (build) version; the crawler's User-Agent uses it too
V011_COMMIT = "7222593"  # the v0.1.1 release commit whose data/ tree is the build input
REPO_URL = "https://github.com/kanoonhq/open-laws"

ACTS = "indian_central_acts.parquet"
SECTIONS = "indian_central_act_sections.parquet"
FOOTNOTES = "central_act_footnotes.parquet"
MAPPINGS = "criminal_law_mappings.parquet"
ARCHIVE = "indian_central_acts_complete.jsonl.gz"


def v011_source_url(file: str, row_id: str) -> str:
    """Permalink to one row of a frozen v0.1.1 input table: the provenance of
    rows parsed offline from the corpus (e.g. a section's text)."""
    return f"{REPO_URL}/blob/{V011_COMMIT}/data/{file}#{row_id}"
