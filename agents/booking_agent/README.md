# AI Appointment Booking Agent (FastAPI)

Tài liệu hướng dẫn sử dụng và kiểm thử AI Appointment Booking Agent tích hợp trong hệ thống FastAPI.

## Kiến trúc & Cấu trúc thư mục

Tất cả các file logic của Booking Agent được lưu trữ phẳng trong thư mục `agents/booking_agent/` để đồng bộ với cấu trúc của dự án:

```text
agents/
  booking_agent/
    __init__.py          # Export các thành phần chính
    config.py            # Cấu hình LLM, URL Backend và Timezone (Asia/Ho_Chi_Minh)
    errors.py            # Định nghĩa custom exceptions & mapper mã lỗi HTTP
    memory_store.py      # Session store in-memory lưu trữ BookingState
    backend_client.py    # HTTP client (httpx) gọi BE API kèm retry & timeout
    appointment_tools.py # Công cụ chuẩn hóa/matching slot và lọc bác sĩ
    types.py             # Khai báo Pydantic models (BookingState, LLMOutputSchema)
    prompt.py            # System Prompt bằng tiếng Việt tối ưu cho LLM
    llm_parser.py        # Tương tác với LLM và parse cấu trúc JSON (có fallback)
    state_machine.py     # Cập nhật và reset BookingState khi các entity thay đổi
    orchestrator.py      # Bộ điều phối chính điều hành luồng hội thoại
```

---

## API Contract (Cổng Chat Đặt Lịch)

- **Endpoint**: `POST /api/ai/chat`
- **Headers**:
  - `Content-Type: application/json`
  - `Authorization: Bearer <JWT_TOKEN>` (Bắt buộc khi gọi API lấy thông tin người dùng và lưu lịch khám)

### Request Payload
```json
{
  "session_id": "session_uuid_12345",
  "message": "Tôi muốn đặt lịch khám với bác sĩ Hương ngày mai"
}
```

### Response Payload
```json
{
  "reply": "Dưới đây là danh sách khung giờ trống của bác sĩ Hương Giang vào ngày 2026-05-26. Vui lòng chọn số thứ tự khung giờ bạn muốn khám:\n1. 09:00-09:30\n2. 10:00-10:30\n3. 14:00-14:30",
  "intent": "book_appointment",
  "state": {
    "messages": [
      {"role": "user", "content": "Tôi muốn đặt lịch khám với bác sĩ Hương ngày mai"},
      {"role": "assistant", "content": "..."}
    ],
    "customerId": "cust_001",
    "customerName": "Nguyễn Văn A",
    "doctorName": "Bác sĩ Hương Giang",
    "doctorId": "doc_002",
    "specialtyName": null,
    "date": "2026-05-26",
    "timeSlot": null,
    "planId": null,
    "reason": null,
    "notes": null,
    "intent": "book_appointment",
    "doctors_list": [],
    "slots_list": ["09:00-09:30", "10:00-10:30", "14:00-14:30"],
    "is_confirmed": false,
    "last_action": null
  },
  "actions": ["select_slot"],
  "requires_user_input": true
}
```

---

## Ví dụ Kiểm thử Bằng lệnh `curl` (E2E Test)

### Bước 1: Gửi tin nhắn bắt đầu đặt lịch
Gửi tin nhắn yêu cầu đặt lịch khám với tên bác sĩ và ngày khám (sử dụng ngày tương đối "ngày mai"):

```bash
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "session_id": "test_e2e_session",
    "message": "Tôi muốn đặt lịch khám với bác sĩ Nam ngày mai"
  }'
```

*AI sẽ tự động gọi API `/api/customers/me` để nhận diện bạn, gọi API `/api/doctors/search` tìm bác sĩ Nam, gọi `/api/doctors/:id/available-slots` lấy slot trống ngày mai, và trả về danh sách các slot khám.*

### Bước 2: Chọn khung giờ khám bằng số chỉ mục
Gửi số thứ tự của khung giờ bạn muốn chọn (ví dụ: gõ "1" để chọn slot `09:00-09:30`):

```bash
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "session_id": "test_e2e_session",
    "message": "1"
  }'
```

*AI nhận diện số "1", gán slot tương ứng vào `timeSlot` và trả về tin nhắn tóm tắt lịch khám yêu cầu bạn xác nhận.*

### Bước 3: Xác nhận đặt lịch khám
Gửi từ khóa đồng ý để hoàn tất đặt lịch:

```bash
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "session_id": "test_e2e_session",
    "message": "Đồng ý"
  }'
```

*AI gọi API `POST /api/appointments` để lưu lịch khám và trả về kết quả đặt lịch thành công kèm mã lịch khám.*

### Kiểm tra tính năng Hủy lịch khám (Intent Cancel)
Gửi yêu cầu hủy lịch để kiểm tra thông báo phản hồi bắt buộc:

```bash
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_e2e_session",
    "message": "Tôi muốn hủy lịch khám đã đặt"
  }'
```

*Kết quả mong muốn: Trả về câu: `"Hiện chưa hỗ trợ hủy lịch trên hệ thống này"`.*
