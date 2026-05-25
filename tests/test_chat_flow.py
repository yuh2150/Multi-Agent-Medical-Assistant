import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from agents.booking_agent.orchestrator import orchestrator
from agents.booking_agent.memory_store import session_store
from agents.booking_agent.errors import UnauthorizedError, AppointmentConflictError

@pytest.fixture(autouse=True)
def run_around_tests():
    # Clear the session before each test
    session_store.delete("test_session_123")
    yield
    session_store.delete("test_session_123")

@pytest.mark.asyncio
@patch("agents.booking_agent.orchestrator.backend_client")
async def test_successful_booking_flow(mock_backend):
    """Test full booking flow: query -> confirm -> success creation."""
    session_id = "test_session_123"
    jwt_token = "valid_jwt_token"
    
    # 1. Mock responses
    mock_backend.get_customer_me = AsyncMock(return_value={
        "customerId": "cust_abc",
        "name": "Nguyễn Văn A",
        "email": "customer@gmail.com"
    })
    mock_backend.search_doctors = AsyncMock(return_value=[
        {"id": "doc_001", "name": "Bác sĩ Nam"}
    ])
    mock_backend.get_available_slots = AsyncMock(return_value=[
        {"timeSlot": "09:00-09:30", "planId": "plan_111", "available": True},
        {"timeSlot": "10:00-10:30", "planId": "plan_222", "available": True}
    ])
    mock_backend.create_appointment = AsyncMock(return_value={
        "id": "apt_999",
        "status": "confirmed"
    })

    # Step 1: User asks for appointment with doctor, date and time
    msg_1 = "Tôi muốn đặt lịch khám với bác sĩ Nam ngày mai lúc 9h"
    res_1 = await orchestrator.handle_message(session_id, msg_1, jwt_token)
    
    assert res_1["intent"] == "book_appointment"
    assert "xác nhận" in res_1["reply"].lower()
    assert res_1["state"]["doctorName"] == "Bác sĩ Nam"
    assert res_1["state"]["doctorId"] == "doc_001"
    assert res_1["state"]["timeSlot"] == "09:00-09:30"
    assert res_1["state"]["is_confirmed"] is False
    assert res_1["requires_user_input"] is True

    # Step 2: User confirms
    msg_2 = "Đồng ý"
    res_2 = await orchestrator.handle_message(session_id, msg_2, jwt_token)
    
    assert "thành công" in res_2["reply"].lower()
    assert "apt_999" in res_2["reply"]
    # Check that temporary booking state is cleared, but messages exist
    cleared_state = session_store.get(session_id)
    assert cleared_state.doctorId is None
    assert cleared_state.date is None
    assert len(res_2["state"]["messages"]) > 0

@pytest.mark.asyncio
@patch("agents.booking_agent.orchestrator.backend_client")
async def test_multiple_doctors_resolution(mock_backend):
    """Test resolution when search returns multiple doctors."""
    session_id = "test_session_123"
    jwt_token = "valid_jwt_token"
    
    mock_backend.get_customer_me = AsyncMock(return_value={
        "customerId": "cust_abc",
        "name": "Nguyễn Văn A"
    })
    mock_backend.search_doctors = AsyncMock(return_value=[
        {"id": "doc_001", "name": "Bác sĩ Hương Giang"},
        {"id": "doc_002", "name": "Bác sĩ Hương Lan"}
    ])

    # User initiates booking
    msg_1 = "Tôi muốn khám bác sĩ Hương"
    res_1 = await orchestrator.handle_message(session_id, msg_1, jwt_token)
    
    assert "nhiều bác sĩ" in res_1["reply"].lower()
    assert len(res_1["state"]["doctors_list"]) == 2
    assert res_1["requires_user_input"] is True

    # User selects index 1 (Bác sĩ Hương Giang)
    msg_2 = "1"
    res_2 = await orchestrator.handle_message(session_id, msg_2, jwt_token)
    
    # State should update to Bác sĩ Hương Giang and clear doctors_list
    assert res_2["state"]["doctorName"] == "Bác sĩ Hương Giang"
    assert res_2["state"]["doctorId"] == "doc_001"
    assert len(res_2["state"]["doctors_list"]) == 0

@pytest.mark.asyncio
@patch("agents.booking_agent.orchestrator.backend_client")
async def test_cancel_intent(mock_backend):
    """Test that cancellation intent returns the exact static message."""
    session_id = "test_session_123"
    
    msg = "Hủy lịch khám đã đặt giúp tôi với"
    res = await orchestrator.handle_message(session_id, msg)
    
    assert res["intent"] == "cancel"
    assert res["reply"] == "Hiện chưa hỗ trợ hủy lịch trên hệ thống này"
    assert res["requires_user_input"] is True

@pytest.mark.asyncio
@patch("agents.booking_agent.orchestrator.backend_client")
async def test_unauthorized_error(mock_backend):
    """Test response when JWT is missing or invalid."""
    session_id = "test_session_123"
    
    # Mock backend to throw UnauthorizedError
    mock_backend.get_customer_me = AsyncMock(side_effect=UnauthorizedError("Token expired"))
    
    msg = "Đặt lịch khám với bác sĩ Nam"
    res = await orchestrator.handle_message(session_id, msg, jwt_token="invalid_token")
    
    assert "hết hạn" in res["reply"].lower() or "đăng nhập" in res["reply"].lower()
    assert "require_login" in res["actions"]
    assert res["requires_user_input"] is False

@pytest.mark.asyncio
@patch("agents.booking_agent.orchestrator.backend_client")
async def test_time_slot_not_available(mock_backend):
    """Test slot matching when requested slot is not available."""
    session_id = "test_session_123"
    jwt_token = "valid_jwt_token"
    
    mock_backend.get_customer_me = AsyncMock(return_value={"customerId": "c1", "name": "A"})
    mock_backend.search_doctors = AsyncMock(return_value=[{"id": "doc_001", "name": "Bác sĩ Nam"}])
    
    # 9:00 slot is not in the list
    mock_backend.get_available_slots = AsyncMock(return_value=[
        {"timeSlot": "08:00-08:30", "available": True},
        {"timeSlot": "10:00-10:30", "available": True}
    ])
    
    msg = "Đặt lịch khám bác sĩ Nam ngày mai lúc 9h sáng"
    res = await orchestrator.handle_message(session_id, msg, jwt_token)
    
    assert "không có sẵn" in res["reply"].lower()
    assert res["state"]["timeSlot"] is None
    assert res["requires_user_input"] is True

@pytest.mark.asyncio
@patch("agents.booking_agent.orchestrator.backend_client")
async def test_get_doctor_info(mock_backend):
    """Test retrieving doctor description/price info."""
    session_id = "test_session_123"
    
    mock_backend.search_doctors = AsyncMock(return_value=[
        {"id": "doc_001", "name": "Bác sĩ Nam", "specialty": "Nội khoa", "price": "300,000 VND"}
    ])
    
    # Using patch for LLM invoke as it makes network calls
    with patch("agents.booking_agent.config.booking_config.llm.ainvoke") as mock_llm_invoke:
        mock_llm_invoke.return_value = AsyncMock(content="Bác sĩ Nam chuyên khoa Nội khoa, giá khám là 300,000 VND.")
        
        msg = "Thông tin và giá khám của bác sĩ Nam thế nào"
        res = await orchestrator.handle_message(session_id, msg)
        
        assert res["intent"] == "get_doctor_info"
        assert "300,000" in res["reply"]
        assert res["requires_user_input"] is True

@pytest.mark.asyncio
@patch("agents.booking_agent.orchestrator.backend_client")
async def test_check_appointment(mock_backend):
    """Test checking own appointment by ID."""
    session_id = "test_session_123"
    
    mock_backend.get_appointment = AsyncMock(return_value={
        "id": "apt_123",
        "doctorName": "Bác sĩ Nam",
        "date": "2026-05-26",
        "timeSlot": "09:00-09:30"
    })
    
    with patch("agents.booking_agent.config.booking_config.llm.ainvoke") as mock_llm_invoke:
        mock_llm_invoke.return_value = AsyncMock(content="Lịch hẹn apt_123 của bạn khám với Bác sĩ Nam vào lúc 09:00 ngày 2026-05-26.")
        
        msg = "Xem lịch hẹn mã apt_123 của tôi"
        res = await orchestrator.handle_message(session_id, msg)
        
        assert res["intent"] == "check_appointment"
        assert "apt_123" in res["reply"]
        assert "Bác sĩ Nam" in res["reply"]
        assert res["requires_user_input"] is True

