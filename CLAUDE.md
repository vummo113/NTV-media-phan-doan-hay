# YouTube Clipper Web — Hướng dẫn cho Claude

## Clip Selector (tích hợp từ `/clip-selector`)

Bất cứ khi nào người dùng đưa transcript hoặc nội dung video, **tự động** phân tích và chọn đoạn đáng cắt — không cần được yêu cầu.

---

### Bước 1 — Thu thập thông tin (nếu chưa có)

**A. Mục đích đầu ra:** TikTok/Reels/Shorts · YouTube highlight · Podcast clip · Newsletter
**B. Đối tượng khán giả:** Phổ thông / Chuyên môn / Gen Z / Đầu tư / Địa chính trị

Nếu chưa rõ, hỏi ngắn gọn. Nếu đã rõ từ context, bỏ qua.

---

### Bước 2 — Phân tích transcript theo timeline

Chia thành phân đoạn khi có dấu hiệu chuyển chủ đề, chuyển loại nội dung, hoặc thay đổi nhịp. Độ dài tối thiểu: 45 giây.

Với mỗi phân đoạn ghi: timecode · chủ đề chính · loại nội dung · điểm đặc biệt.

---

### Bước 3 — Chấm điểm (5 tiêu chí)

| Tiêu chí | TikTok | YouTube | Podcast | Newsletter |
|----------|--------|---------|---------|------------|
| Hook (H) | 30 | 20 | 25 | 15 |
| Aha (A) | 25 | 25 | 30 | 35 |
| Độc lập (I) | 25 | 15 | 20 | 25 |
| Stakes (S) | 10 | 20 | 20 | 20 |
| Visual (V) | 10 | 20 | 5 | 5 |

**Ngưỡng cứng TikTok:** Độc lập < 40% → cắt ngay bất kể tổng điểm.

**Thang điểm mỗi tiêu chí:**
- **Hook:** 90–100% = hook ngay lập tức / 60–89% = cần chỉnh nhẹ / 30–59% = cần viết lại (xem Bước 3b) / 0–29% = không thể tạo hook
- **Aha:** 90–100% = phản trực giác, lật ngược nhận thức / 60–89% = góc nhìn mới / 30–59% = hữu ích nhưng không ngạc nhiên / 0–29% = đã biết rồi
- **Độc lập:** 90–100% = hiểu hoàn toàn không cần context / 60–89% = cần 1–2 câu setup / 30–59% = cần xem 5 phút trước / 0–29% = phụ thuộc hoàn toàn
- **Stakes:** 90–100% = ảnh hưởng trực tiếp (tiền, an toàn, tương lai) / 60–89% = gián tiếp / 30–59% = trí tuệ nhưng xa vời / 0–29% = thuần học thuật
- **Visual:** 90–100% = bản đồ, số liệu, so sánh trực quan / 60–89% = text overlay + b-roll / 30–59% = chủ yếu lời nói / 0–29% = trừu tượng

---

### Bước 3b — Viết lại hook (khi Hook 30–59%)

5 công thức, chọn 1 phù hợp nhất:

1. **Phản trực giác:** "Tại sao [điều ai cũng nghĩ đúng] lại hoàn toàn sai?"
2. **Con số gây sốc:** "[Con số cụ thể]. Đây là lý do tại sao [hậu quả]."
3. **Ai cũng biết nhưng không ai hỏi:** "Mọi người đều biết [X]. Nhưng không ai hỏi tại sao [điều kỳ lạ]."
4. **Stakes cá nhân:** "Nếu bạn là [nhóm cụ thể], điều này ảnh hưởng trực tiếp đến [điều họ quan tâm]."
5. **Tuyên bố táo bạo:** "[Tuyên bố mạnh]. Và đây là bằng chứng đầu tiên: [chi tiết cụ thể]."

Hook phải dùng ngôn ngữ trong transcript gốc, không bịa thông tin mới.

---

### Bước 4 — Phân loại

| Điểm | Hành động |
|------|-----------|
| 80–100 | Giữ nguyên |
| 60–79 | Rút ngắn |
| 40–59 | Cân nhắc |
| 0–39 | Cắt bỏ |

---

### Bước 5 — CẮT TỰ ĐỘNG (không cần chấm điểm)

- Quảng cáo / sponsor
- Kêu gọi subscribe / follow / like
- Giới thiệu show / chào hỏi đầu episode
- Host hỏi định nghĩa thuật ngữ cơ bản (nếu audience đã biết)
- Tóm tắt lại điều vừa nói
- Kết thúc xã giao

---

### Bước 6 — Output chuẩn

**Clip giữ nguyên (80–100):**
```
Clip #[số] — Điểm: [X]/100
Timecode: [00:00] – [00:00] · ~X phút
Tiêu đề: [...]
Hook: "[câu mở đầu]"
Lý do: [1–2 câu]
```

**Clip rút ngắn (60–79) — Dạng 1 (cắt đầu/đuôi):**
```
Clip #[số] — Điểm: [X]/100
✂ Giữ: [00:00] – [00:00]
✂ Bỏ đầu: [00:00] – [00:00] · Lý do: [...]
✂ Bỏ đuôi: [00:00] – [00:00] · Lý do: [...]
```

**Clip rút ngắn (60–79) — Dạng 2 (jump-cut):**
```
Clip #[số] — Điểm: [X]/100 · Jump-cut
✂ GIỮ A: [00:00] – [00:00]
✂ BỎ B:  [00:00] – [00:00]  ← vì: [lý do]
✂ GIỮ C: [00:00] – [00:00]
```

**Clip bị cắt:**
```
[00:00]–[00:00] — Cắt — [lý do 1 câu]
```

---

### Điều chỉnh theo audience

- **Chuyên môn:** Cắt đoạn hỏi định nghĩa cơ bản. Aha +5, Stakes -5.
- **Phổ thông:** Giữ giải thích thuật ngữ nếu <45s và có ví dụ. Stakes +5.

---

## Stack kỹ thuật

- Backend: FastAPI + SQLite
- Frontend: HTML + Tailwind CSS (CDN, không build step)
- Auth: JWT trong httpOnly cookie, bcrypt
- Progress: Server-Sent Events (SSE)
- Storage: local filesystem, clip tự xóa sau 24h
- Deploy target: Railway hoặc Render (free tier)
