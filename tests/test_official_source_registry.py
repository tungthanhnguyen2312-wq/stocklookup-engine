"""Offline admission coverage for Owner-approved statement acquisition expansion."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from stocklookup_core.evidence import official_source_registry as registry

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)
STATEMENT_TYPES = (
    "audited_annual_financial_statements",
    "reviewed_interim_financial_statements",
)
NEW_ISSUER_STATEMENT_URLS = (
    # HL-20261125-GEM1-06-VN30-EXPANSION/GEM1-06_vn30_income_lines.csv row 2 (MSN).
    'https://www.masangroup.com/wp-content/uploads/2026/03/77067939a0036755d23278e7a9435867.pdf',
    # HL-20261125-GEM1-06-VN30-EXPANSION/GEM1-06_vn30_income_lines.csv row 32 (PLX).
    'https://files.petrolimex.com.vn/files/6783dc1271ff449e95b74a9520964169/application=pdf/0cef52a84ed140c4853adea8c1e23de6/20260331%20-%20PLX%20-%20Bao%20cao%20tai%20chinh%20hop%20nhat%20nam%202025%20sau%20kiem%20toan.pdf',
    # HL-20261125-GEM1-06-VN30-EXPANSION/GEM1-06_vn30_income_lines.csv row 47 (SAB).
    'https://www.sabeco.com.vn/Data/Sites/1/media/co%20dong/bao%20cao%20tai%20chinh/2026/2026-03-26/2025FS-CONSO-VN.pdf',
    # HL-20261125-GEM1-06-VN30-EXPANSION/GEM1-06_vn30_income_lines.csv row 62 (VIC).
    'https://ircdn.vingroup.net/storage/Uploads/0_Baocaotaichinh/Nam%202025/2025_Bao%20cao%20tai%20chinh%20hop%20nhat%20kiem%20toan.pdf',
    # HL-20261125-GEM1-06-VN30-EXPANSION/GEM1-06_vn30_income_lines.csv row 92 (VJC).
    'https://ir.vietjetair.com/File_Upload/thong-tin-tai-chinh/bao-cao-tai-chinh-kiem-toan/2025/20260330%20-%20VJC%20-%20BCTC%20Hop%20nhat%202025%20VN%20seal.pdf',
    # HL-20261125-GEM1-06-VN30-EXPANSION/GEM1-06_vn30_income_lines.csv row 107 (GVR).
    'https://vrg.vn/wp-content/uploads/2026/03/20260330-GVR-Bao-cao-tai-chinh-hop-nhat-nam-2025.pdf?x48994',
    # HL-20261125-GEM1-06-VN30-EXPANSION/GEM1-06_vn30_income_lines.csv row 122 (BCM).
    'https://becamex.com.vn/wp-content/uploads/2026/03/BAO-CAO-TAI-CHINH-HOP-NHAT-KIEM-TOAN-2025.pdf',
    # HL-20261125-GEM1-06-VN30-EXPANSION/GEM1-06_vn30_income_lines.csv row 137 (DGC).
    'https://ducgiangchem.vn/wp-content/uploads/2026/06/20260620-DGC-BCTC-hop-nhat-kiem-toan-2025.pdf',
    # HL-20261125-GEM1-08-COVERAGE-BATCH2/GEM1-08_batch2_income_lines.csv row 2 (REE).
    'https://www.reecorp.com/wp-content/uploads/2026/03/20260312-ree-bctc-hop-nhat-kiem-toan-nam-2025.pdf',
    # HL-20261125-GEM1-08-COVERAGE-BATCH2/GEM1-08_batch2_income_lines.csv row 17 (DPM).
    'https://dpm.vn/public_folder/files_upload/202604/bctc-hop-nhat-nam-2025viepdf1776753461.pdf',
    # HL-20261125-GEM1-08-COVERAGE-BATCH2/GEM1-08_batch2_income_lines.csv row 32 (DCM).
    'https://www.pvcfc.com.vn/Data/Sites/1/media/bao-cao-tai-chinh/2025/20260228%20-%20DCM%20-%20Bao%20cao%20tai%20chinh%20hop%20nhat%202025%20da%20kiem%20toan.pdf',
    # HL-20261125-GEM1-08-COVERAGE-BATCH2/GEM1-08_batch2_income_lines.csv row 47 (KDH).
    'https://www.khangdien.com.vn/wp-content/uploads/2026/03/20260327-kdh-bctc-hop-nhat-kiem-toan-nam-2025-giai-trinh-sign.pdf',
    # HL-20261125-GEM1-08-COVERAGE-BATCH2/GEM1-08_batch2_income_lines.csv row 62 (NLG).
    'https://www.namlongvn.com/uploads/2026/03/20260318-NLG-CBTT-Bao-cao-tai-chinh-nam-2025-da-kiem-toan-Hop-nhat-VN.pdf',
    # HL-20261125-GEM1-08-COVERAGE-BATCH2/GEM1-08_batch2_income_lines.csv row 80 (HSG).
    'https://hoasengroup.vn/wp-content/uploads/2025/12/20251229-hsg-bctc-hop-nhat-ndtc-2024-2025-da-kiem-toan.pdf',
    # HL-20261125-GEM1-08-COVERAGE-BATCH2/GEM1-08_batch2_income_lines.csv row 98 (VHC).
    'https://www.vinhhoan.com/wp-content/uploads/2026/03/VHC-_BCTC-hop-nhat-kiem-toan-2025_VN.pdf',
    # HL-20261125-GEM1-08-COVERAGE-BATCH2/GEM1-08_batch2_income_lines.csv row 113 (FRT).
    'https://cdn.frt.vn/cms/20260326_FRT_BCTC_Hop_nhat_da_kiem_toan_nam_2025_signed_1a099dc8af.pdf',
    # HL-20261125-GEM1-09-BATCH3/gem1-09_batch3.csv row 2 (GEX).
    'https://gelex.vn/wp-content/uploads/2026/03/20260303-GEX-BCTC-hop-nhat-nam-2025.pdf',
    # HL-20261125-GEM1-09-BATCH3/gem1-09_batch3.csv row 17 (PDR).
    'https://www.phatdat.com.vn/wp-content/uploads/2026/03/20260331-PDR-BCTC-Hop-nhat-nam-2025-sau-kiem-toan.pdf',
    # HL-20261125-GEM1-09-BATCH3/gem1-09_batch3.csv row 32 (DIG).
    'https://www.dic.vn/uploads/files/2026/03/30/20260330-DIG-BCTC-hop-nhat-kiem-toan-nam-2025.pdf',
    # HL-20261125-GEM1-09-BATCH3/gem1-09_batch3.csv row 62 (HAH).
    'https://haiants.vn/files/Quan_he_co_dong/Bao_cao_tai_chinh/2026-0223-HAH-Bao-cao-tai-chinh-hop-nhat-da-duoc-kiem-toan-cho-nam-tai-chinh-ket-thuc-ngay-31-12-2025.pdf',
    # HL-20261125-GEM1-09-BATCH3/gem1-09_batch3.csv row 77 (GMD).
    'https://www.gemadept.com.vn/wp-content/uploads/2026/03/20260330-GMD-BCTC-Hop-nhat-Kiem-toan-nam-2025.pdf',
    # HL-20261125-GEM1-09-BATCH3/gem1-09_batch3.csv row 92 (PVS).
    'https://www.ptsc.com.vn/Data/Sites/1/media/codong/2026/397%20PTSC-BTK.pdf',
    # HL-20261125-GEM1-09-BATCH3/gem1-09_batch3.csv row 108 (BWE).
    'https://www.biwase.com.vn/Data/Sites/1/media/quan-he-co-dong/dinh-ky/bao-cao-tai-chinh/2026/20260227-bwe-bctchn-nam-2025-da-kiem-toan-signed.pdf',
    # HL-20261125-GEM1-09-BATCH3/gem1-09_batch3.csv row 123 (DGW).
    'https://digiworld.com.vn/assets/site/investor/20260324-DGW-BCTC-Hop-nhat-2025_Kiem-toan.pdf',
)


def admission(source_id, url, document_type):
    return registry.admit(
        source_id, url, document_type,
        registry=registry.load_registry(ROOT / "config/official_source_registry.json"),
        now=NOW,
    )


@pytest.mark.parametrize("url", NEW_ISSUER_STATEMENT_URLS)
@pytest.mark.parametrize("document_type", STATEMENT_TYPES)
def test_expansion_issuer_statement_hosts_are_admitted(url, document_type):
    assert admission("issuer_ir", url, document_type)["decision"] == registry.ADMITTED


@pytest.mark.parametrize("url", NEW_ISSUER_STATEMENT_URLS)
@pytest.mark.parametrize("document_type", ["annual_report", "corporate_action_notice", "issuer_ir_index_page"])
def test_expansion_hosts_remain_limited_to_statements(url, document_type):
    result = admission("issuer_ir", url, document_type)
    assert result["decision"] == registry.REFUSED
    assert result["reason"] == registry.REASON_DOCUMENT_TYPE_NOT_ALLOWED_FOR_HOST


@pytest.mark.parametrize("host", [
    "vietstock.vn", "finance.vietstock.vn", "cafef.vn", "vndirect.com.vn",
    "fireant.vn", "simplize.vn", "investing.com",
    "cdnv2.tgdd.vn", "bhxcdn.vn", "gelex.vn.example.org", "cdn.gelex.vn",
])
@pytest.mark.parametrize("document_type", STATEMENT_TYPES)
def test_aggregators_unresolved_cdns_and_unlisted_siblings_remain_refused(host, document_type):
    result = admission("issuer_ir", f"https://{host}/statement.pdf", document_type)
    assert result["decision"] == registry.REFUSED
    assert result["reason"] == registry.REASON_HOST_NOT_ALLOWED


@pytest.mark.parametrize("host", ["www.hsx.vn", "hsx.vn", "staticfile.hsx.vn"])
@pytest.mark.parametrize("document_type", STATEMENT_TYPES)
def test_hose_statement_types_mirror_hnx(host, document_type):
    assert admission("hnx", "https://owa.hnx.vn/statement.pdf", document_type)["decision"] == registry.ADMITTED
    assert admission("hose", f"https://{host}/statement.pdf", document_type)["decision"] == registry.ADMITTED
