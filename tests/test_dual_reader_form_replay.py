"""Offline replay inventory tests; no retained issuer artifacts are mutated."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.replay_dual_reader_form_support import replay


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sealed, self.neutral = self.root / "sealed", self.root / "neutral"
        image, pdf = b"owned image", b"owned PDF fixture"
        (self.neutral / "pages").mkdir(parents=True)
        (self.neutral / "originals").mkdir()
        (self.neutral / "pages/ssi.png").write_bytes(image)
        (self.neutral / "originals/ssi.pdf").write_bytes(pdf)
        page = {"key": "SSI_2025", "source_page": 17,
            "image_sha256": hashlib.sha256(image).hexdigest(),
            "document_sha256": hashlib.sha256(pdf).hexdigest(),
            "image": "pages/ssi.png", "original_pdf": "originals/ssi.pdf"}
        _write(self.neutral / "packages/SSI_earnings_basis/input_manifest.json", {"pages": [page]})
        _write(self.neutral / "packages/EVF_material_credit_funding/input_manifest.json", {"pages": []})
        index = {"readers": []}
        for family in ("claude", "gemini"):
            raw = {"model_family": family, "recorded_at": None,
                "input": {"image_sha256": page["image_sha256"]},
                "table": {"form_reference_literal": "B02-CTCK/HN", "scope_literal": "HỢP NHẤT",
                    "columns": [{"column_id": "c1", "label_literal": "Năm nay", "role": "current_period"}],
                    "rows": [{"line_code_literal": "200", "row_label_literal": "XI. LỢI NHUẬN KẾ TOÁN SAU THUẾ TNDN",
                        "cells": [{"column_id": "c1", "raw_value_literal": "123", "sign_literal": "unsigned", "uncertainty": []}]}]}}
            package = self.sealed / family / "SSI_earnings_basis"
            digest = _write(package / "output/page_01.json", raw)
            seal_digest = _write(package / "SEAL.json", {"output_files": {"output/page_01.json": {"sha256": digest}}})
            index["readers"].append({"family": family, "package_id": "SSI_earnings_basis",
                "seal_path": f"{family}/SSI_earnings_basis/SEAL.json", "seal_sha256": seal_digest})
        _write(self.sealed / "SEALED_READER_INDEX.json", index)

    def test_no_proof_never_admits_identical_values_and_replay_is_deterministic(self):
        first = replay(self.sealed, self.neutral)
        assert first == replay(self.sealed, self.neutral)
        assert first["counts"] == {"REFUSE": 1}
        assert first["cells"][0]["candidate_metric"] == "securities_profit_after_tax"
        assert "DUAL_READER_RETAINED_PROOF_UNAVAILABLE" in first["cells"][0]["reason_codes"]
        assert first["missing_proof_inputs"]

    def test_tampered_reader_is_an_integrity_error(self):
        (self.sealed / "gemini/SSI_earnings_basis/output/page_01.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "REPLAY_SEALED_HASH_MISMATCH"):
            replay(self.sealed, self.neutral)

    def test_tampered_image_is_an_integrity_error(self):
        (self.neutral / "pages/ssi.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "REPLAY_SEALED_HASH_MISMATCH"):
            replay(self.sealed, self.neutral)

    def test_reader_paths_cannot_escape_the_package(self):
        index_path = self.sealed / "SEALED_READER_INDEX.json"
        index = json.loads(index_path.read_bytes())
        seal_path = self.sealed / index["readers"][0]["seal_path"]
        pin = json.loads(seal_path.read_bytes())["output_files"]["output/page_01.json"]
        index["readers"][0]["seal_sha256"] = _write(seal_path, {
            "output_files": {"output/page_../../../../../escape.json": deepcopy(pin)}})
        _write(index_path, index)
        with self.assertRaisesRegex(ValueError, "REPLAY_PATH_ESCAPE"):
            replay(self.sealed, self.neutral)


if __name__ == "__main__":
    unittest.main()
