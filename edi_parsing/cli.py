from __future__ import annotations

import argparse
import csv
from collections import defaultdict
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
    parser.add_argument(
        "--metadata-csv-output",
        type=Path,
        help="Optional metadata CSV summary output path (# files, # EDIs by creation date)",
    )
    return parser


def _write_metadata_csv(metadata: dict, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)

    edi_counts_by_date: dict[str, int] = defaultdict(int)
    for file_metadata in metadata.get("files", []):
        creation_datetime = file_metadata.get("creation_datetime")
        if not creation_datetime:
            continue
        creation_date = creation_datetime.split("T", 1)[0]
        transaction_counts = file_metadata.get("transaction_counts", {})
        edi_counts_by_date[creation_date] += int(transaction_counts.get("835", 0)) + int(
            transaction_counts.get("837", 0)
        )

    with output_file.open("w", encoding="utf-8", newline="") as sink:
        writer = csv.DictWriter(sink, fieldnames=["total_files", "date", "edi_count"])
        writer.writeheader()
        if edi_counts_by_date:
            for creation_date in sorted(edi_counts_by_date):
                writer.writerow(
                    {
                        "total_files": metadata["total_edi_files"],
                        "date": creation_date,
                        "edi_count": edi_counts_by_date[creation_date],
                    }
                )
        else:
            writer.writerow({"total_files": metadata["total_edi_files"], "date": "", "edi_count": 0})


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.input_path.is_dir():
        input_files = sorted(path for path in args.input_path.glob(args.glob) if path.is_file())
    else:
        input_files = [args.input_path]

    if not input_files:
        raise SystemExit(f"No input files found for: {args.input_path}")

    metadata = process_edi_batch(input_files=input_files, output_file=args.output, metadata_file=args.metadata_output)

    if args.metadata_csv_output:
        _write_metadata_csv(metadata, args.metadata_csv_output)

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
