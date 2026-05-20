"""
Utility script to extract all .zip files in a source directory to an output directory.

Usage:
    python extract_zips.py <input_dir> <output_dir>
"""

import argparse
import sys
import zipfile
from pathlib import Path


def extract_zips(input_dir: Path, output_dir: Path) -> None:
    """Extract all .zip files in input_dir to output_dir."""
    zip_files = sorted(input_dir.glob("*.zip"))

    if not zip_files:
        print(f"No .zip files found in '{input_dir}'.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    for zip_path in zip_files:
        print(f"Processing: {zip_path.name} ...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(output_dir)
        print(f"  Extracted to: {output_dir}")

    print(f"\nDone. {len(zip_files)} file(s) extracted.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract all .zip files in a directory to an output directory."
    )
    parser.add_argument("input_dir", help="Directory containing .zip files")
    parser.add_argument("output_dir", help="Directory to extract files into")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        print(f"Error: input directory '{input_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    extract_zips(input_dir, output_dir)


if __name__ == "__main__":
    main()
