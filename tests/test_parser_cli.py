import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from edi_parsing.cli import main
from edi_parsing.parser import process_edi_batch

SAMPLE_837 = (
    "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *240101*1253*^*00501*000000905*0*T*:~"
    "GS*HC*SENDER*RECEIVER*20240101*1253*1*X*005010X222A1~"
    "ST*837*0001~"
    "BHT*0019*00*0123*20240101*1319*CH~"
    "SE*3*0001~"
    "GE*1*1~"
    "IEA*1*000000905~"
)

SAMPLE_835 = (
    "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *240102*0900*^*00501*000000906*0*T*:~"
    "GS*HP*SENDER*RECEIVER*20240102*0900*2*X*005010X221A1~"
    "ST*835*0002~"
    "BPR*C*1500*C*ACH*CTX*01*999999992*DA*123456789*1512345678**01*999988880*DA*987654321*20240102~"
    "SE*3*0002~"
    "GE*1*2~"
    "IEA*1*000000906~"
)


class ParserCliTests(unittest.TestCase):
    def test_process_batch_writes_jsonl_and_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_837 = tmp_path / "a.edi"
            file_835 = tmp_path / "b.edi"
            bad = tmp_path / "bad.edi"
            output = tmp_path / "records.jsonl"
            metadata_path = tmp_path / "metadata.json"

            file_837.write_text(SAMPLE_837, encoding="utf-8")
            file_835.write_text(SAMPLE_835, encoding="utf-8")
            bad.write_text("NOT_AN_EDI", encoding="utf-8")

            metadata = process_edi_batch([file_837, file_835, bad], output, metadata_path)

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
            (in_dir / "claim.edi").write_text(SAMPLE_837, encoding="utf-8")

            output = tmp_path / "out.jsonl"
            metadata = tmp_path / "meta.json"

            rc = main([str(in_dir), "--output", str(output), "--metadata-output", str(metadata)])

            self.assertEqual(rc, 0)
            self.assertTrue(output.exists())
            self.assertTrue(metadata.exists())


if __name__ == "__main__":
    unittest.main()
