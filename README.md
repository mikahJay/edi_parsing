# edi_parsing

A minimal wrapper around `pyx12` to parse X12 835/837 EDI files and emit:

- JSON Lines segment output (`.jsonl`) suitable for Snowflake loading
- Metadata JSON with counts, creation date range, and malformed/error summaries

## Setup

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Why this is required on many Linux systems:

- Installing with system `pip` may fail with an `externally-managed-environment` error (PEP 668)
- A local virtualenv avoids that and keeps project dependencies isolated

## Run tests

```bash
. .venv/bin/activate
python -m unittest discover -s tests -v
```

## CLI

```bash
python -m edi_parsing.cli /path/to/edis --glob "*.edi" --output parsed_records.jsonl --metadata-output metadata.json
```

Or, after installation:

```bash
edi-parse /path/to/edis --glob "*.edi" --output parsed_records.jsonl --metadata-output metadata.json
```

## Using bundled test data

The repository includes sample 835 and 837 files in `test_data/`.

From the repository root, run:

```bash
python -m edi_parsing.cli ./test_data --glob "*.edi" --output parsed_records.jsonl --metadata-output metadata.json
```
