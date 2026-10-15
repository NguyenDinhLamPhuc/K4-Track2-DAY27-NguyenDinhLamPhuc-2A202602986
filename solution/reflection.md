# Reflection

## 1. Loại lỗi khó phát hiện nhất trong 5 luồng sự kiện

Trong 5 luồng sự kiện, nhóm lỗi thuộc trụ cột AI Infrastructure(`feature_materialization` và `embedding_batch`) là khó phát hiện nhất, cụ thể là:
- Không có ranh giới nhị phân rõ ràng: Khác với `contracts` (có danh sách xác thực schema/type cụ thể) hay `lineage` (kiểm tra tập hợp và số lượng), lỗi drift không thể phán đoán bằng điều kiện đúng/sai tuyệt đối.
- Nhiễu tự nhiên trong dữ liệu: Phân phối đặc trưng và embeddings trong luồng streaming luôn có biến thiên ngẫu nhiên (`mean_shift_sigma` của dòng sạch có thể dao động đến ~0.47, `centroid_shift` biến thiên theo cụm văn bản). Các lỗi drift tinh vi nằm rất sát ngưỡng phương sai thông thường. Nếu siết ngưỡng quá chặt sẽ làm tăng mạnh tỷ lệ dương tính giả (FPR), còn nếu nới lỏng thì tỷ lệ bỏ sót lỗi (FN) tăng cao.



## 2. Quyết định cân bằng giữa chi phí gọi công cụ (ctx.tools) và tỷ lệ bắt trúng lỗi (TPR)

Hệ thống tính điểm áp dụng công thức:  
$$\text{Score} = 100 \times (0.5 \cdot \text{TPR} - 0.3 \cdot \text{FPR} - 0.2 \cdot \min(\text{cost\_overage}, 1))$$

Để đạt điểm số tối ưu trong điều kiện giới hạn ngân sách:
- Kiểm soát chi phí gọi RPC: Các công cụ phân tích drift (`feature_drift`, `embedding_drift`) tiêu tốn chi phí cao nhất (2.0 credits/lần), trong khi `contract_diff` tốn 1.5 credits, `batch_profile` và `lineage_graph_slice` tốn 1.0 credit. Chiến lược áp dụng là mỗi sự kiện chỉ gọi tối đa một công cụ tương ứng, không gọi lặp hoặc gọi chéo công cụ không cần thiết.
- Tối ưu ngưỡng dựa trên baseline thực tế: Thay vì chỉ dựa hoàn toàn vào ngưỡng 3-sigma tĩnh mặc định của `ctx.baseline`, các ngưỡng quyết định (như `0.65` cho feature drift hay `0.039` / `41 ngày` cho embedding drift) được tinh chỉnh dựa trên khoảng phân cách an toàn giữa phân phối sạch và phân phối lỗi quan sát được từ pha practice.
- Phòng thủ ngoại lệ: Luôn kiểm tra cờ `"error"` từ phản hồi của tool để trả về `Verdict(alert=False)` an toàn, tránh báo động giả khi hệ sinh thái gặp sự cố RPC không hợp lệ.



## 3. Đề xuất cải tiến cơ chế thống kê trong ctx.state

`ctx.state` là bộ nhớ trạng thái tồn tại suốt vòng đời của một run và hoàn toàn miễn phí (0 credit). Hiện tại giải pháp xử lý từng sự kiện độc lập. Nếu có thêm thời gian, các cải tiến thống kê sau sẽ được tích hợp:

1. Cửa sổ trượt thống kê (Rolling Window / EWMA):
   - Lưu trữ trung bình động có trọng số mũ và phương sai cho `mean_amount`, `row_count` và `mean_shift_sigma` theo từng thực thể (`feature_view`, `contract_id`).
   - Việc tính Z-score động trên N batch gần nhất sẽ giúp nhận diện cả các đợt biến động đột ngột lẫn sự trôi dạt dần dần mà ngưỡng tĩnh không thể bắt kịp.

2. Thuật toán CUSUM:
   - Áp dụng CUSUM cho `centroid_shift` và `avg_doc_age_days` trong embedding để phát hiện sự suy giảm chất lượng dữ liệu tích lũy qua thời gian dài (ngay cả khi mỗi batch chỉ lệch một lượng nhỏ dưới ngưỡng cảnh báo tức thời).

3. Gợi ý gọi công cụ theo xác suất / điều kiện:
   - Theo dõi chuỗi an toàn trong `ctx.state`. Nếu một luồng dữ liệu liên tục ổn định trong nhiều phiên, có thể áp dụng chiến lược lấy mẫu (sampling) hoặc kiểm tra nhẹ trước khi quyết định gọi các tool tốn kém (2.0 credits), giúp tiết kiệm ngân sách đáng kể cho các đợt stream nghi ngờ cao.

