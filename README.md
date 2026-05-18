# edi_parsing

A minimal wrapper around `pyx12` to parse X12 835/837 EDI files and emit:

- JSON Lines segment output (`.jsonl`) suitable for Snowflake loading
- Metadata JSON with counts, creation date range, and malformed/error summaries

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
