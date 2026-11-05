# Lead review 05/11/2026 — logic công việc sắp tới, phản biện ChatGPT, đặc tả prompt cho agent

Tác giả: Claude (Tech Lead, chương trình `STOCKLOOKUP_SUSTAINABILITY_PROGRAM_V1`). Ngày 2026-11-05, 08:30, trước Daily 05/11.
Người đọc: Owner và ChatGPT (người sẽ viết prompt cho Grok/Codex).
Cách lập: mọi số dưới đây đều đọc trực tiếp từ máy Owner hoặc từ receipt đã commit. Ngoặc vuông ghi nguồn.

## 0. Tóm tắt một đoạn

Có **hai đồng hồ** nhưng mức nghiêm trọng khác nhau:
- **Ổ T: là đồng hồ cứng.** Khi chạm sàn 160 GiB, host preflight BLOCKED và **cả Daily không chạy**. Theo số liệu hiện có, còn khoảng 9 phiên, tức khoảng 17–18/11.
- **T+ là đồng hồ mềm.** Timeout chỉ làm T+ thành UNAVAILABLE, Daily vẫn PASS. Ở đường chạy thường ngày, M1b đã đạt **mọi gate của contract**.

Vì vậy thứ tự đúng là:
1. Đẩy M1b vào Production theo contract hiện hành, **không** chờ tối ưu discovery.
2. **Bắt đầu ngay chuỗi dung lượng D3 → M2 → khôi phục thử → D4/D5**, vì đây là đường găng thực sự.

Discovery/R2 tách thành bước tiếp theo M1c, làm khi rảnh.

## 1. Tự sửa: hai chỗ báo cáo trước của tôi (05/11 sáng) sai

| Tôi đã nói | Đúng là | Nguồn |
|---|---|---|
| "T+ chạm 1.200 s khoảng 13/11, M1b phải release trước 12/11" | Con số 44 phiên / 13/11 là mô hình **R2 worst-case** (mọi partition bị vô hiệu), receipt ghi rõ: *"Offline worst-case all-invalidated model, not a measured historical Daily crossing"*. Đường thường ngày (thêm 1 T0) của M1b là 563 s. Với M1 đang chạy Production, ước tính trước đây là chạm khoảng giữa tháng 12. | receipt `TPLUS_INCREMENTAL_COST_V2_M1B_REHEARSAL_20261104.json` → `measured_growth_projection.interpretation` |
| "Chống trùng lặp cho phiên mới không cần D4" | **Sai.** Contract đặt "verified duplicate consolidation" vào M3 và ghi M3 needs D4. Invariant của M1 cũng cấm hardlink. Muốn làm forward-only thì Owner phải duyệt một phạm vi D4 hẹp (gọi là **D4a**: chỉ phiên mới). | `docs/tplus_incremental_cost_v2_contract.md` §Program order, §Invariants |
| "giảm tăng trưởng ≈30%" | 4,7 / 19 ≈ **25%**. ChatGPT đúng. | — |

## 2. Phản biện ChatGPT (bản trả lời 05/11)

| # | ChatGPT nói | Đánh giá | Lý do / bằng chứng |
|---|---|---|---|
| C1 | "D3 chưa xác nhận đủ nội dung — không phê duyệt quyền xóa, di chuyển, retention" | **Hiểu nhầm D3.** | D3 trong REPORT.md 03/11 là: *"Backup ngay (vận hành, không cần code). Chạy vault incremental hiện có cho các phiên từ 19/10 đến 03/11 sang W:, kèm receipt."* D3 chỉ là **copy**, không xóa, không di chuyển. Đây chính là việc "Backup W:" mà ChatGPT cũng khuyến nghị. → **Duyệt D3**, mở rộng đến phiên mới nhất. Xóa/di chuyển là D4/D5, chưa duyệt. |
| C2 | "Contract ghi warm stage ≤600 s… nên cho R2 ≤900 s là đổi tiêu chí nghiệm thu" | **Sai đối tượng.** | Gate của contract là: *warm stage with one new T0 ≤ 600 s* (= add, M1b đo **563 s ĐẠT**), *pre + post ≤ 900 s* (**769 s ĐẠT**), parity (ĐẠT), child ≤ 2 GiB (1,28 GB ĐẠT). "R2 ≤ 600" và "discovery ≤ 60" **không có trong contract**; đó là mục tiêu kéo dãn tôi đặt trong prompt round 2. Vì vậy D7 kiểu "nới R2 lên 900" là **không cần**. M1b được release theo contract nguyên văn, còn R2/discovery thành mục tiêu của M1c. |
| C3 | "M2 triển khai sau khi M1b có checkpoint ổn định" | **Không đồng ý về thứ tự.** | Dung lượng là lỗi cứng (chặn cả Daily) và có hạn khoảng 17–18/11. Đường găng dung lượng (backup → khôi phục thử → D5 tiering) mất khoảng 1–2 tuần. Nếu chờ M1b xong mới bắt đầu thì không kịp. M2 là ledger, phần lớn read-only, sửa file khác M1b → chạy song song được. Ràng buộc thật chỉ là **không chạy IO nặng cùng lúc với benchmark hoặc Daily**, chứ không phải tuần tự hóa toàn bộ. |
| C4 | "R2 đang tiến gần deadline 1.200 s, cần xử lý trước nâng cấp phân tích" | Một phần đúng. | R2 = 1.058 s chỉ xảy ra khi context_key đổi trên toàn bộ (vd. đổi evaluator). Khi đó việc seed chạy **ngoài Daily** (exit 33, bước kích hoạt). R2 > 1.200 là rủi ro về độ bền, chưa phải sự cố vận hành. Để vào M1c. |
| C5 | Tiết kiệm từ chống trùng lặp khoảng 25% chứ không phải 30% | **Đúng.** | Xem §1. |
| C6 | RAM: không mở milestone mới; 1,28 GB không thay cho headroom toàn Daily | **Đúng.** | Peak RSS một tiến trình Daily 04/11 là 5,47 GB (đã có số đo). Tiếp tục ghi lại mỗi Daily, chưa sửa. |
| C7 | D-S1 dọn sau khi kiểm tra dependency, không đụng M1b/oracle/retained | **Đúng.** | Danh sách cụ thể ở §5 P-0. |
| C8 | D6 "đúng hai module đã xác định ở HANDOFF" | Cần nêu tên. | Receipt `discovery_proposal`: (a) `prospective_decision_outcome_feedback._source_fingerprint` — 105,47 s (full SHA mọi legacy source); (b) `prospective_decision_retention._original_reuse_reasons` — 43,69 s; (c) `prospective_decision_retention.discover_snapshots → catalog path qualification` — 46,91 s, có rủi ro parity cao ("silently admit an unqualified restored copy"). Hai module là `prospective_decision_outcome_feedback.py` và `prospective_decision_retention.py`. Khuyến nghị: duyệt (a)+(b), **không** duyệt (c) trong M1c. |

## 3. Logic đúng của công việc sắp tới

### 3.1 Hai đồng hồ

| | Ổ T: | T+ |
|---|---|---|
| Khi vượt ngưỡng | Preflight BLOCKED → **không có Daily** | T+ UNAVAILABLE, Daily vẫn PASS |
| Số hiện tại | 340,19 GiB trống; sàn 160 GiB | M1 Prod 04/11: pre 700 s, post 680 s; M1b rehearsal: add 563, add+post 769 |
| Tốc độ | ≈19 GiB/phiên (1 mẫu: 04/11; retained-evidence +20,81 GiB trừ seed một lần ≈1,75) | evaluate ≈15–22 s/phiên tùy đường chạy |
| Hạn ước tính | ≈9 phiên → **17–18/11** | M1 thường ngày: khoảng giữa tháng 12; R2 worst-case đã > 1.000 s |
| Đòn bẩy & thời gian | D-S1 +11 GiB (ngay) · D4a forward-only −4,7 GiB/phiên (vài ngày + D4a) · D5 tiering phiên cũ sang W: (lớn nhất, cần D3+khôi phục thử, 1–2 tuần) | M1b release (vài ngày) · M1c discovery (sau) |

Kết luận: **dung lượng là đường găng.** M1b chỉ cần đưa vào Production cho sạch, không cần tối ưu thêm trước.

### 3.2 Chuỗi phụ thuộc

```
Daily 05/11 ──► P-0 dọn scratch (D-S1) ──► P-1 nghiệm thu, có mẫu tăng thứ 2
                                     │
 Dung lượng (đường găng): D3 backup W: ──► khôi phục thử 1 phiên ──► D5 tiering phiên cũ
                          M2 ledger + disk probe ───────────────┘      (Owner quyết dựa trên ledger)
                          D4a chống trùng forward-only (sau M2, cần Owner duyệt)
 T+:  M1b rebase lên 63c92f48 ──► đo lại code cuối ──► PR/CI/merge ──► kích hoạt (seed+scrub) trước 1 Daily ──► nghiệm thu
      M1c discovery (a)+(b) — sau khi M1b chạy ổn 2 Daily
```

### 3.3 Ràng buộc tài nguyên host (lý do không chạy hết cùng lúc)

- Chỉ có 1 laptop, 16 GB RAM, và T: là 1 ổ ngoài. Các việc **IO nặng trên T:** gồm vault backup (đọc vài trăm GiB), benchmark T+ (đọc khoảng 35 GiB), seed/scrub và Daily. Mỗi lúc chỉ được chạy **một** việc thuộc nhóm này.
- Các việc **nhẹ** chạy song song được với nhau: viết code, unit test, CI trên GitHub, review read-only.
- Mỗi bộ file chỉ có một writer. M1b/M1c sửa `prospective_decision_*`. M2 sửa `owner_daily_progress.py` và thêm tool ledger. Hai bên không giao nhau.
- **Khóa sàn của rehearsal M1b là 340 GiB, T: hiện 340,19 GiB** → phải làm P-0 (dọn scratch) trước khi Grok chạy bất kỳ phép đo corpus nào.

## 4. Quyết định Owner (bản đã sửa)

| Mã | Nội dung | Khuyến nghị |
|---|---|---|
| D1, D2 | Đã duyệt 03/11 | Giữ nguyên |
| **D3** | Vault incremental **copy-only** lên W: cho các phiên 16/10 → mới nhất, có receipt; không xóa, không di chuyển | **Duyệt ngay** |
| **D-S1** | Xóa `T:\StockLookup\scratch\tplus-v2-rehearsal-20261104` (10,71 GiB) và `scratch\wt-tplus-incremental-v2-baseline-20261104`, sau khi copy receipt/HANDOFF/proof vào `recovery-checkpoints\` và kiểm tra không còn worktree/tham chiếu | **Duyệt** |
| ~~D7~~ | Không cần: M1b release theo gate contract nguyên văn; R2 ≤ 600 và discovery ≤ 60 chuyển thành mục tiêu M1c | **Bỏ** |
| **D6** | M1c được sửa đúng 2 hàm (a) `_source_fingerprint` và (b) `_original_reuse_reasons`, trong 2 module nêu ở C8; cấm (c) catalog qualification | Duyệt, nhưng chỉ bắt đầu sau khi M1b chạy ổn 2 Daily |
| D4a | Chống trùng IID/full-universe/valuation **chỉ cho phiên mới**, giữ byte identity và seal | Quyết sau khi M2 có ledger (khoảng 10/11) |
| D4, D5 | Relink lịch sử; tiering hot/warm/cold sang W: | Quyết sau D3 + khôi phục thử (khoảng 12–14/11) |

## 5. Đặc tả cho ChatGPT viết prompt

Quy ước chung cho mọi prompt:
- Mỗi prompt ghi rõ: worktree, base commit, file được sửa, file cấm, gate định lượng, nơi ghi HANDOFF.
- Mỗi prompt phải kết thúc bằng **"không push/merge/deploy/xóa ngoài phạm vi"**, trừ khi đã ghi quyền cụ thể.
- Không chạy job IO nặng khi Daily đang chạy. Phải kiểm tra không còn writer trước khi bắt đầu.
- Kết quả là số đo kèm đường dẫn file kết quả, không chỉ là tóm tắt.

### P-0 — Dọn scratch (D-S1) · Agent: Codex · Sau Daily 05/11 · ≈20 phút
- Trước khi xóa: kiểm tra `git worktree list` của các repo; đảm bảo không có process nào đang mở file trong thư mục.
- Copy `*-result.json`, `*-host.json`, `*proof*.json`, `HANDOFF*.md`, `PROMPT*.md` vào `production-v1\recovery-checkpoints\20261105-scratch-retire\`, kèm manifest SHA-256.
- Xóa đúng 2 đường dẫn trong D-S1. Với `wt-tplus-incremental-v2-baseline-20261104`, dùng `git worktree remove` (không `rm`).
- **Cấm** đụng: `tplus-m1b-rehearsal-20261104`, `wt-tplus-m1b-20261104`, `preseal-producer-seal-20261026-r8/-r10` (chúng vừa được ghi lại sau 04/11, chưa rõ lý do → chỉ báo cáo ai/khi nào ghi), `production-v1\*`.
- Gate: T: trống ≥ 350 GiB; manifest; báo cáo.

### P-1 — Nghiệm thu Daily 05/11 · Agent: Claude (read-only)
Đọc journal, T+ pre/post (giây, trạng thái, số dòng, identity), peak RSS, delta T: theo thư mục. Kết quả là mẫu tăng thứ hai.

### P-2 — M1b release candidate · Agent: Grok · Ngay sau P-0 · Worktree `T:\StockLookup\scratch\wt-tplus-m1b-20261104`, nhánh `fix/tplus-incremental-cost-v2-m1b`, từ `3a9cc727`
1. Đưa nhánh lên `origin/main` = `63c92f48` (merge hoặc rebase, ghi rõ chọn cách nào). Giải conflict, không đổi ngữ nghĩa.
2. Toàn bộ test focused (200+) và test liên quan PASS.
3. Đo lại **trên code cuối**, corpus thật: cold parity với oracle (62.271 dòng, artifact `28b9c2af…`), add (1 T0 mới), post, R2 (chỉ để tham khảo).
4. Scratch dùng thêm ≤ 8 GiB, tự dọn có manifest, không hạ sàn 340 GiB.
- Gate bắt buộc, theo contract nguyên văn: parity byte; add ≤ 600 s; add + post ≤ 900 s; child ≤ 2 GiB. R2 ghi lại, không phải gate.
- Cấm: sửa discovery (`_source_fingerprint`, `_original_reuse_reasons`, catalog), sửa roadmap, push.
- Output: HANDOFF + cập nhật receipt M1b. Claude review trước khi chuyển sang P-3.

### P-3 — Release + kích hoạt M1b · Agent: Codex · Sau khi Claude chấp nhận P-2
- Push nhánh, mở PR, chờ CI xanh. Merge chỉ khi Owner đã ghi quyền trong prompt (standing authority 04/11 đã bao gồm M1b).
- Viết `m1b-activation\Invoke-M1bActivation.ps1` theo mẫu `m1-activation\Invoke-M1Activation.ps1`: preflight (RAM, writer, sàn T:) → ff-only deploy → registry hash guard → `--seed-state-only` (mong đợi exit 33) → `--scrub-sources` (mong đợi exit 0) → receipt `recovery-checkpoints\<date>-m1b-activation\`. Dùng `--root` = `--state-root` = `T:\StockLookup\production-v1\retained-evidence`. Đọc file bằng ReadAllText, không Get-Content -Raw.
- Owner tự chạy script foreground **trước** Daily, sau khi đã đóng Claude/Grok/Codex. Agent không tự chạy.

### P-4 — D3 vault backup lên W: · Agent: Codex (script) + Owner (chạy) · Chạy khi không có Daily/benchmark, ví dụ ban đêm
- Dùng cơ chế Vault V1 hiện có (`docs/vault_incremental_snapshot_contract.md`), **copy-only**, cho các phiên từ phiên có receipt cuối (16/10) đến phiên sealed mới nhất.
- Trước khi chạy: kiểm tra danh tính volume W:; ước tính số byte; dung lượng trống W: ≥ 3 lần lượng cần copy.
- Output: receipt vault + verify offline PASS.
- Sau đó **khôi phục thử 1 phiên** vào scratch: verify byte và ghi lại fingerprint (volume ID/file ID) thay đổi thế nào. Đây là đầu vào cho D5.

### P-5 — M2 ledger + disk probe · Agent: Grok (worktree mới từ `63c92f48`) · Song song P-2, nhưng phép quét đĩa không chạy cùng benchmark/Daily
- Tool read-only: dung lượng theo nhóm (retained-evidence theo loại artifact và phiên, T+ store + sidecar, IID, bản trùng vật lý theo hash + nlink, scratch, recovery-checkpoints).
- Tốc độ tăng/phiên từ 03, 04, 05/11 trở đi. Runway theo phiên và theo 30/90 ngày. Khớp ±2% với dung lượng trống của volume.
- Sửa `owner_daily_progress.py` (probe hard-code `C:\`) để đo ổ chứa output_root. Thêm cảnh báo khi runway < 10 phiên và chặn mềm khi < 5.
- Cấm: xóa, hardlink, di chuyển. Không đụng `prospective_decision_*`.
- Output: PR riêng (Codex hỗ trợ release), ledger JSON, và đề xuất D4a có số liệu (byte tiết kiệm/phiên, thiết kế giữ seal/identity).

### P-6 — M1c discovery (D6) · Agent: Grok · Chỉ sau khi M1b chạy ổn 2 Daily
Sửa đúng (a)+(b), giữ đường full-SHA khi receipt thiếu hoặc lệch. Gate: parity + discovery giảm ≥ 100 s + R2 ≤ 900 s (mục tiêu 600). Không đụng (c).

## 6. Lịch dự kiến (ngày giao dịch)

| Ngày | Việc | Tài nguyên IO nặng trên T: |
|---|---|---|
| Thứ 5, 05/11 | Daily → P-0 → P-1; Owner duyệt D3, D-S1, D6 | Daily |
| 05–06/11 (tối) | P-4 backup (chạy 1 lượt) | Vault |
| Thứ 6, 06/11 | P-2 code/test (ban ngày), Daily; P-5 code | Daily |
| 07–08/11 (cuối tuần) | P-2 đo corpus; khôi phục thử P-4 | Benchmark → Restore (tuần tự) |
| 09–10/11 | Claude review P-2; P-3 PR/CI; P-5 ledger chạy thật → đề xuất D4a | Daily |
| 10 hoặc 11/11 | Owner chạy kích hoạt M1b trước Daily | Seed/scrub → Daily |
| 11–13/11 | Nghiệm thu M1b (2 Daily); Owner quyết D4a/D5 | Daily |
| 13–17/11 | Triển khai D4a/D5 (milestone M3/M4) trước khi T: chạm sàn | — |

Điểm kiểm tra: nếu ledger P-5 cho thấy runway (sau P-0) **< 7 phiên**, thì D5 tiering phiên cũ lên trước M1b release, và P-6 hoãn.

## 7. Phân công

- **Grok:** writer chính cho P-2, P-5, P-6. Owner tự khởi chạy (auto-mode chặn Claude khởi chạy agent `--always-approve`).
- **Codex:** P-0, P-3, script P-4, hỗ trợ release PR của P-5.
- **Claude:** P-1, review HANDOFF của P-2/P-5/P-6 (đối chiếu file kết quả). Không làm writer.
- **Owner:** duyệt D-x, chạy foreground kích hoạt/backup, chạy Daily.
