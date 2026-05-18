from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from pyx12.x12file import X12Reader
except ImportError as exc:  # pragma: no cover - exercised in runtime environments without pyx12
    raise RuntimeError("pyx12 is required. Install dependencies before running this tool.") from exc

SUPPORTED_TRANSACTION_TYPES = {"835", "837"}


@dataclass
class ParsedFileResult:
    file_path: str
    records: list[dict]
    transaction_counts: dict[str, int]
    creation_datetime: datetime | None
    service_datetimes: list[datetime]
    errors: list[str]
    malformed: bool


def _to_isa_datetime(date_value: str | None, time_value: str | None) -> datetime | None:
    if not date_value or not time_value:
        return None
    time_value = time_value[:4].zfill(4)
    try:
        parsed = datetime.strptime(f"{date_value}{time_value}", "%y%m%d%H%M")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _segment_values(segment: object) -> list[str]:
    return [value for _, _, _, value in segment.values_iterator()]


def _to_date_datetime(date_value: str | None) -> datetime | None:
    if not date_value:
        return None
    for date_format in ("%Y%m%d", "%y%m%d"):
        try:
            return datetime.strptime(date_value, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_service_dates(segment_id: str, segment_elements: list[str]) -> tuple[datetime | None, datetime | None]:
    if segment_id == "DTP" and len(segment_elements) >= 3:
        qualifier = segment_elements[0]
        date_format = segment_elements[1]
        date_value = segment_elements[2]
        if qualifier not in {"150", "151", "472"}:
            return None, None
        if date_format == "RD8":
            start_date, separator, end_date = date_value.partition("-")
            if not separator:
                parsed = _to_date_datetime(start_date)
                return parsed, parsed
            return _to_date_datetime(start_date), _to_date_datetime(end_date)
        parsed = _to_date_datetime(date_value)
        if qualifier == "150":
            return parsed, None
        if qualifier == "151":
            return None, parsed
        return parsed, parsed

    if segment_id == "DTM" and len(segment_elements) >= 2:
        qualifier = segment_elements[0]
        if qualifier not in {"150", "151", "472"}:
            return None, None
        parsed = _to_date_datetime(segment_elements[1])
        if qualifier == "150":
            return parsed, None
        if qualifier == "151":
            return None, parsed
        return parsed, parsed

    return None, None


def parse_edi_file(file_path: Path) -> ParsedFileResult:
    transaction_counts = {"835": 0, "837": 0}
    records: list[dict] = []
    errors: list[str] = []
    creation_datetime: datetime | None = None
    service_datetimes: list[datetime] = []
    interchange_control_number: str | None = None
    functional_group_control_number: str | None = None

    current_transaction_set: str | None = None
    current_transaction_control_number: str | None = None
    current_service_date_start: datetime | None = None
    current_service_date_end: datetime | None = None

    try:
        with file_path.open("r", encoding="utf-8") as source:
            reader = X12Reader(source)
            segment_index = 0
            for segment in reader:
                segment_id = segment.get_seg_id()
                segment_index += 1
                segment_elements = _segment_values(segment)

                if segment_id == "ISA":
                    interchange_control_number = segment.get_value("ISA13")
                    creation_datetime = _to_isa_datetime(segment.get_value("ISA09"), segment.get_value("ISA10"))
                elif segment_id == "GS":
                    functional_group_control_number = segment.get_value("GS06")
                elif segment_id == "ST":
                    current_transaction_set = segment.get_value("ST01")
                    current_transaction_control_number = segment.get_value("ST02")
                    if current_transaction_set in SUPPORTED_TRANSACTION_TYPES:
                        transaction_counts[current_transaction_set] += 1
                elif segment_id == "SE":
                    current_transaction_control_number = segment.get_value("SE02")

                segment_service_start, segment_service_end = _extract_service_dates(segment_id, segment_elements)
                if segment_service_start is not None:
                    current_service_date_start = segment_service_start
                    service_datetimes.append(segment_service_start)
                if segment_service_end is not None:
                    current_service_date_end = segment_service_end
                    service_datetimes.append(segment_service_end)

                records.append(
                    {
                        "source_file": file_path.name,
                        "segment_index": segment_index,
                        "segment_id": segment_id,
                        "segment_elements": segment_elements,
                        "transaction_set": current_transaction_set,
                        "transaction_control_number": current_transaction_control_number,
                        "interchange_control_number": interchange_control_number,
                        "functional_group_control_number": functional_group_control_number,
                        "service_date_start": (
                            current_service_date_start.isoformat() if current_service_date_start else None
                        ),
                        "service_date_end": current_service_date_end.isoformat() if current_service_date_end else None,
                    }
                )

                if segment_id == "SE":
                    current_transaction_set = None
                    current_transaction_control_number = None
                    current_service_date_start = None
                    current_service_date_end = None

            errors.extend(str(error) for error in reader.pop_errors())
    except Exception as exc:  # broad exception to capture malformed files from parser
        errors.append(str(exc))
        return ParsedFileResult(
            file_path=str(file_path),
            records=[],
            transaction_counts=transaction_counts,
            creation_datetime=None,
            service_datetimes=[],
            errors=errors,
            malformed=True,
        )

    if transaction_counts["835"] == 0 and transaction_counts["837"] == 0:
        errors.append("No supported transaction sets (835/837) found in file")

    return ParsedFileResult(
        file_path=str(file_path),
        records=records,
        transaction_counts=transaction_counts,
        creation_datetime=creation_datetime,
        service_datetimes=service_datetimes,
        errors=errors,
        malformed=False,
    )


def process_edi_batch(input_files: Iterable[Path], output_file: Path, metadata_file: Path) -> dict:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)

    files = [Path(path) for path in input_files]
    results = [parse_edi_file(path) for path in files]

    with output_file.open("w", encoding="utf-8") as sink:
        for result in results:
            for record in result.records:
                sink.write(json.dumps(record, default=str))
                sink.write("\n")

    creation_datetimes = [result.creation_datetime for result in results if result.creation_datetime is not None]
    service_datetimes = [service_date for result in results for service_date in result.service_datetimes]

    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_edi_files": len(results),
        "successfully_parsed_files": sum(1 for result in results if not result.malformed),
        "malformed_edi_files": sum(1 for result in results if result.malformed),
        "transaction_set_counts": {
            "835": sum(result.transaction_counts["835"] for result in results),
            "837": sum(result.transaction_counts["837"] for result in results),
        },
        "creation_date_range": {
            "earliest": min(creation_datetimes).isoformat() if creation_datetimes else None,
            "latest": max(creation_datetimes).isoformat() if creation_datetimes else None,
        },
        "service_date_range": {
            "earliest": min(service_datetimes).isoformat() if service_datetimes else None,
            "latest": max(service_datetimes).isoformat() if service_datetimes else None,
        },
        "files": [
            {
                "file_path": result.file_path,
                "malformed": result.malformed,
                "transaction_counts": result.transaction_counts,
                "creation_datetime": result.creation_datetime.isoformat() if result.creation_datetime else None,
                "error_count": len(result.errors),
                "errors": result.errors,
            }
            for result in results
        ],
    }

    with metadata_file.open("w", encoding="utf-8") as sink:
        json.dump(metadata, sink, indent=2)
        sink.write("\n")

    return metadata
