# November 13 reviewed evidence to conditional investment research

The existing offline case builder accepts the [39-row reviewed packet](FINANCIAL_EVIDENCE_PACKET_20261113.json). It verifies the caller-pinned packet digest and all eight original document digests. The local source map is a JSON object keyed by document SHA-256 with absolute paths or paths relative to the map. Document locators and issuer URLs remain in the packet. Output identities omit machine-specific source paths. An identical run to fresh output paths produces identical bytes.

The packet retains native text, visually reviewed scanned rows, and OCR or carried candidates. Calculations use reviewed numeric inputs known by the cutoff. A date-only time is available at the end of that Vietnam day. Signing dates and retained knowledge times carry distinct meanings. The reviewed path is offline, non-voting, and carries no official fact admission, strict valuation or Daily authority.

| Issuer | Conditional result | Remaining evidence limit |
|---|---|---|
| HPG | Parent profit VND 23,582,361,859,679 for 9M26 versus VND 11,589,090,380,691 for 9M25. Audited FY25 plus the independently image-read YTD columns gives conditional TTM VND 27,446,445,485,211. Cash flow over parent profit is 0.8878× and derived September equity is VND 148,795,417,583,205. | Annual and interim presentation differ. Q3 assurance, the lease split, later share continuity and a monetarily verified session close remain open. |
| KBC | Native FY25 parent profit VND 2,103,625,414,463 against negative operating cash flow VND 17,343,896,115,028. Cash flow over parent profit is −8.2448×, cash over printed borrowing lines is 0.2922× and derived parent equity is VND 24,801,125,998,273. | The KBC Q3 original matches its full SHA-256. OCR candidates and Circular 99 reclassification prevent the proposed TTM. The printed borrowing lines do not establish net debt. |
| FPT | FY25 parent profit VND 9,376,127,629,501, operating cash flow VND 10,136,043,915,911 and cash after the printed purchases line VND 5,038,124,566,055. Code 400 VND 43,748,040,747,539 equals code 410 plus code 430 budget funds of VND 2,750,000,000. Code 410 less code 429 NCI yields VND 36,480,193,944,772 of derived parent equity. | The shift from fully consolidated FPT Telecom to the later equity-method basis prevents an FY25/Q3 bridge. The derived equity carries no printed parent book or strict P/B authority. |

All three issuer cases keep market capitalization, P/E, P/B and EV/EBITDA empty. The HPG and FPT structural levels retain their price-unit uncertainty and remain context only. Existing historical CLI modes remain available.

```powershell
python -B tools/build_conditional_research_cases.py --reviewed-packet docs/internal/FINANCIAL_EVIDENCE_PACKET_20261113.json --packet-sha256 ae5f06f70d15318951aaaff2073aae7019c85fd0d6d09152aadd53b2e35a8c4c --source-map <local-source-map.json> --out-json <fresh-output.json> --out-md <fresh-output.md>
```
