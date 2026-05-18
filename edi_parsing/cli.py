from __future__ import annotations

import argparse
from pathlib import Path

from .parser import process_edi_batch


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse 835/837 EDI files into Snowflake-ingestible JSONL + metadata")
    parser.add_argument("input_path", type=Path, help="Input EDI file or directory")
    parser.add_argument(
        "--glob",
        default="*.edi",
        help="Glob for files when input_path is a directory (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("parsed_records.jsonl"),
        help="Output JSONL file path (default: %(default)s)",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=Path("metadata.json"),
        help="Output metadata JSON file path (default: %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.input_path.is_dir():
        input_files = sorted(path for path in args.input_path.glob(args.glob) if path.is_file())
    else:
        input_files = [args.input_path]

    if not input_files:
        raise SystemExit(f"No input files found for: {args.input_path}")

    metadata = process_edi_batch(input_files=input_files, output_file=args.output, metadata_file=args.metadata_output)

    print(
        "Processed {total} file(s). Malformed: {malformed}. 835: {count_835}. 837: {count_837}.".format(
            total=metadata["total_edi_files"],
            malformed=metadata["malformed_edi_files"],
            count_835=metadata["transaction_set_counts"]["835"],
            count_837=metadata["transaction_set_counts"]["837"],
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
