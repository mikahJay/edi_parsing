import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from edi_parsing.cli import main
from edi_parsing.parser import process_edi_batch

TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "test_data"
SAMPLE_837_FILE = TEST_DATA_DIR / "sample_837.edi"
SAMPLE_835_FILE = TEST_DATA_DIR / "sample_835.edi"
SAMPLE_835_MULTIPLE_2_EDIS_FILE = TEST_DATA_DIR / "sample_835_multiple_2_edis.edi"
SAMPLE_837_MULTIPLE_3_EDIS_FILE = TEST_DATA_DIR / "sample_837_multiple_3_edis.edi"


class ParserCliTests(unittest.TestCase):
    def test_process_batch_writes_jsonl_and_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bad = tmp_path / "bad.edi"
            output = tmp_path / "records.jsonl"
            metadata_path = tmp_path / "metadata.json"

            bad.write_text("NOT_AN_EDI", encoding="utf-8")

            metadata = process_edi_batch([SAMPLE_837_FILE, SAMPLE_835_FILE, bad], output, metadata_path)

            self.assertEqual(metadata["total_edi_files"], 3)
            self.assertEqual(metadata["malformed_edi_files"], 1)
            self.assertEqual(metadata["transaction_set_counts"]["835"], 1)
            self.assertEqual(metadata["transaction_set_counts"]["837"], 1)
            self.assertIsNotNone(metadata["creation_date_range"]["earliest"])
            self.assertIsNotNone(metadata["creation_date_range"]["latest"])

            records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            txns = {record["transaction_set"] for record in records}
            self.assertIn("835", txns)
            self.assertIn("837", txns)

            metadata_file = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata_file["total_edi_files"], 3)

    def test_cli_parses_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            in_dir = tmp_path / "in"
            in_dir.mkdir()
            shutil.copy(SAMPLE_837_FILE, in_dir / "claim.edi")

            output = tmp_path / "out.jsonl"
            metadata = tmp_path / "meta.json"

            rc = main([str(in_dir), "--output", str(output), "--metadata-output", str(metadata)])

            self.assertEqual(rc, 0)
            self.assertTrue(output.exists())
            self.assertTrue(metadata.exists())

    def test_cli_parses_repository_test_data(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output = tmp_path / "out.jsonl"
            metadata_path = tmp_path / "meta.json"

            rc = main(
                [
                    str(TEST_DATA_DIR),
                    "--glob",
                    "*.edi",
                    "--output",
                    str(output),
                    "--metadata-output",
                    str(metadata_path),
                ]
            )

            self.assertEqual(rc, 0)
            self.assertTrue(output.exists())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["total_edi_files"], 4)
            self.assertEqual(metadata["malformed_edi_files"], 0)
            self.assertEqual(metadata["transaction_set_counts"]["835"], 3)
            self.assertEqual(metadata["transaction_set_counts"]["837"], 4)

    def test_process_batch_parses_multiple_edis_in_single_file(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output = tmp_path / "out.jsonl"
            metadata_path = tmp_path / "meta.json"

            metadata = process_edi_batch(
                [SAMPLE_835_MULTIPLE_2_EDIS_FILE, SAMPLE_837_MULTIPLE_3_EDIS_FILE], output, metadata_path
            )

            self.assertEqual(metadata["total_edi_files"], 2)
            self.assertEqual(metadata["malformed_edi_files"], 0)
            self.assertEqual(metadata["transaction_set_counts"]["835"], 2)
            self.assertEqual(metadata["transaction_set_counts"]["837"], 3)

            files_by_name = {
                Path(file_metadata["file_path"]).name: file_metadata for file_metadata in metadata["files"]
            }
            self.assertEqual(
                files_by_name[SAMPLE_835_MULTIPLE_2_EDIS_FILE.name]["transaction_counts"]["835"],
                2,
            )
            self.assertEqual(
                files_by_name[SAMPLE_837_MULTIPLE_3_EDIS_FILE.name]["transaction_counts"]["837"],
                3,
            )

    def test_process_batch_extracts_service_date_ranges(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edi_file = tmp_path / "service_dates.edi"
            output = tmp_path / "out.jsonl"
            metadata_path = tmp_path / "meta.json"

            edi_file.write_text(
                (
                    "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *240105*1100*^*00501*000000909*0*T*:~"
                    "GS*HC*SENDER*RECEIVER*20240105*1100*5*X*005010X222A1~"
                    "ST*837*0008~"
                    "BHT*0019*00*0123*20240105*1110*CH~"
                    "DTP*472*RD8*20240103-20240107~"
                    "DTM*150*20240102~"
                    "DTM*151*20240108~"
                    "SE*7*0008~"
                    "GE*1*5~"
                    "IEA*1*000000909~"
                ),
                encoding="utf-8",
            )

            metadata = process_edi_batch([edi_file], output, metadata_path)

            self.assertEqual(metadata["service_date_range"]["earliest"], "2024-01-02T00:00:00+00:00")
            self.assertEqual(metadata["service_date_range"]["latest"], "2024-01-08T00:00:00+00:00")

            records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            dtp_record = next(record for record in records if record["segment_id"] == "DTP")
            self.assertEqual(dtp_record["service_date_start"], "2024-01-03T00:00:00+00:00")
            self.assertEqual(dtp_record["service_date_end"], "2024-01-07T00:00:00+00:00")

            dtm_end_record = next(
                record
                for record in records
                if record["segment_id"] == "DTM" and record["segment_elements"][0] == "151"
            )
            self.assertEqual(dtm_end_record["service_date_end"], "2024-01-08T00:00:00+00:00")

    def test_process_batch_extracts_835_service_dates_from_svc_dtm_loop(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            edi_file = tmp_path / "service_dates_835.edi"
            output = tmp_path / "out.jsonl"
            metadata_path = tmp_path / "meta.json"

            edi_file.write_text(
                (
                    "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *240105*1100*^*00501*000000909*0*T*:~"
                    "GS*HP*SENDER*RECEIVER*20240105*1100*5*X*005010X221A1~"
                    "ST*835*0008~"
                    "BPR*C*1500*C*ACH*CTX*01*999999992*DA*123456789*1512345678**01*999988880*DA*987654321*20240102~"
                    "CLP*PATIENT*1*100*80*20*MC*12345*11*1~"
                    "SVC*HC:99213*100*80~"
                    "DTM*232*20240103~"
                    "SE*7*0008~"
                    "GE*1*5~"
                    "IEA*1*000000909~"
                ),
                encoding="utf-8",
            )

            metadata = process_edi_batch([edi_file], output, metadata_path)
            self.assertEqual(metadata["service_date_range"]["earliest"], "2024-01-03T00:00:00+00:00")
            self.assertEqual(metadata["service_date_range"]["latest"], "2024-01-03T00:00:00+00:00")

            records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            svc_record = next(record for record in records if record["segment_id"] == "SVC")
            self.assertEqual(svc_record["service_date_start"], "2024-01-03T00:00:00+00:00")
            self.assertEqual(svc_record["service_date_end"], "2024-01-03T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
