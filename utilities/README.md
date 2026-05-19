# Utilities

Standalone helper scripts for working with EDI data files.

---

## extract_zips.py

Extracts all `.zip` files found in a source directory into a specified output directory. Each file processed is logged to the console.

### Requirements

Python 3.x (no third-party dependencies — uses only the standard library).

### Usage

```bash
python utilities/extract_zips.py <input_dir> <output_dir>
```

| Argument | Description |
|---|---|
| `input_dir` | Path to the directory containing `.zip` files to extract |
| `output_dir` | Path to the directory where contents will be extracted |

- The output directory is created automatically if it does not already exist.
- Files are extracted in alphabetical order by zip filename.
- If no `.zip` files are found in `input_dir`, a message is printed and the script exits cleanly.

### Example

```bash
python utilities/extract_zips.py /data/raw_zips /data/extracted
```

**Console output:**

```
Processing: batch_001.zip ...
  Extracted to: /data/extracted
Processing: batch_002.zip ...
  Extracted to: /data/extracted

Done. 2 file(s) extracted.
```

### Notes

- All `.zip` files are extracted into the **same** output directory. If multiple zips contain files with identical names, later extractions will overwrite earlier ones.
- The script exits with a non-zero status code if `input_dir` does not exist.
