# Stock Lookup

**Hiểu thị trường và cổ phiếu Việt Nam rõ hơn — bằng dữ liệu có nguồn gốc, phân tích có thể kiểm tra và những giới hạn được nói rõ.**

Stock Lookup là dự án nghiên cứu và hỗ trợ quyết định đầu tư cho cổ phiếu trên HOSE, HNX và UPCoM. Thay vì chỉ đưa ra một tín hiệu mua/bán, hệ thống giúp người đọc hiểu **điều gì đang diễn ra, bằng chứng nào ủng hộ nhận định, rủi ro nằm ở đâu và cần theo dõi điều gì tiếp theo**.

**[Khám phá Dashboard Stock Lookup](https://tungthanhnguyen2312-wq.github.io/stocklookup-dashboard/)**

## Bạn có thể khám phá những gì?

- **Tổng quan thị trường:** diễn biến phiên giao dịch, bức tranh thị trường, nhóm ngành và các điểm đáng chú ý.
- **Cơ hội nghiên cứu:** tìm hiểu từng cổ phiếu qua giá, xu hướng, tình hình doanh nghiệp, định giá tham khảo, yếu tố tích cực và rủi ro. “Đáng nghiên cứu” không đồng nghĩa “nên mua”.
- **Danh mục:** xem các vị thế do bạn tự nhập trong bối cảnh nghiên cứu và rủi ro; thông tin cá nhân của phần này được lưu trong trình duyệt.
- **Vĩ mô:** theo dõi các chỉ số kinh tế và thời điểm cập nhật, với giải thích về ý nghĩa của chúng.
- **Lịch sử:** đọc lại các báo cáo theo phiên để phân biệt thông tin ở thời điểm trước với nhận định hiện tại.

Dashboard được thiết kế để đọc **tóm tắt dễ hiểu trước, chứng cứ chi tiết sau**. Một người mới tìm hiểu chứng khoán có thể bắt đầu từ bức tranh chung mà không cần hiểu các thuật ngữ kỹ thuật bên trong hệ thống.

## Stock Lookup hình thành nhận định như thế nào?

1. **Thu thập và lưu giữ nguồn:** dữ liệu thị trường, báo cáo tài chính, công bố doanh nghiệp và những bằng chứng có liên quan.
2. **Kiểm tra dữ liệu:** xác định số liệu thuộc nguồn nào, kỳ nào, có còn phù hợp và đủ điều kiện sử dụng cho mục đích đang xét hay không.
3. **Phân tích bằng các phép tính có thể tái hiện:** kết hợp bối cảnh thị trường, kỹ thuật, tài chính, định giá và rủi ro, trong phạm vi bằng chứng cho phép.
4. **Trình bày kết quả và phản biện:** nêu điểm tích cực, điểm bất lợi, điều kiện có thể thay đổi nhận định và những gì hiện chưa biết. Lớp nghiên cứu AI hỗ trợ giải thích, không tự tạo ra số liệu hay quyền kết luận.
5. **Để con người quyết định:** kết quả nghiên cứu không phải lệnh giao dịch tự động.

**Không đủ dữ liệu cũng là một kết quả quan trọng.** Một chỉ tiêu có thể chưa tính được, chỉ phù hợp để tham khảo, hoặc không áp dụng cho loại hình doanh nghiệp đang xét. Stock Lookup cố gắng thể hiện những khác biệt đó thay vì lấp chỗ trống bằng con số phỏng đoán.

## Giới hạn cần biết

Một số dữ liệu và phương pháp hiện chỉ phù hợp cho nghiên cứu, chưa đủ căn cứ để xác định giá trị hợp lý, xác suất kịch bản hoặc quy mô giao dịch. Dữ liệu công bố ở thời điểm sau không tự động được xem là thông tin đã biết trong quá khứ.

Stock Lookup là **công cụ hỗ trợ nghiên cứu**, không cung cấp tư vấn đầu tư cá nhân hóa, không bảo đảm dự báo và không tự động đặt lệnh.

## Mã nguồn và phát triển

Stock Lookup gồm ba repository có nhiệm vụ riêng:

- **[stocklookup-engine](https://github.com/tungthanhnguyen2312-wq/stocklookup-engine)** (repository này): thu thập, kiểm tra và phân tích dữ liệu; tạo các kết quả nghiên cứu.
- **Lớp nghiên cứu AI** (repository riêng, không công khai): tổ chức hồ sơ nghiên cứu, giải thích và phản biện trên những bằng chứng được cung cấp.
- **[stocklookup-dashboard](https://github.com/tungthanhnguyen2312-wq/stocklookup-dashboard)**: giao diện web để người dùng khám phá kết quả.

**Dành cho người phát triển:** [Hướng dẫn đóng góp](CONTRIBUTING.md) · [Sơ đồ hệ thống](docs/SYSTEM_MAP.md) · [Nguyên tắc dữ liệu](docs/DATA_FIRST_DOCTRINE.md) · [Quy tắc dành cho coding agent](AGENTS.md) · [Chính sách bảo mật](SECURITY.md).

Các hướng dẫn vận hành, lộ trình máy đọc được, quyết định kiến trúc và hồ sơ lịch sử được lưu trong thư mục [docs/](docs/) để người bảo trì tra cứu; chúng không phải hướng dẫn bắt đầu dành cho người sử dụng Dashboard. Việc chạy pipeline đầy đủ cần môi trường, dữ liệu và quyền truy cập nguồn phù hợp, không phải thao tác một bước trên bản clone mới.

## Giấy phép

Mã nguồn trong repository này được phát hành theo giấy phép [MIT](LICENSE). Quyền sử dụng dữ liệu, tài liệu và dịch vụ của bên thứ ba tuân theo điều khoản của từng nguồn.