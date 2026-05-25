import re
import logging
from typing import Dict, Any, List, Optional
from .config import booking_config
from .types import BookingState, LLMOutputSchema, LLMEntities
from .memory_store import session_store
from .llm_parser import llm_parser
from .state_machine import BookingStateMachine
from .backend_client import backend_client
from .appointment_tools import find_matching_slots
from .errors import (
    BookingAgentException,
    UnauthorizedError,
    DoctorNotFoundError,
    NoAvailableSlotsError,
    InvalidTimeSlotError,
    AppointmentConflictError,
    BackendAPIError
)

logger = logging.getLogger("booking_agent.orchestrator")

class Orchestrator:
    """Orchestrates the chat booking workflow, connecting the LLM Parser, State Machine, and Backend Client."""
    
    def __init__(self):
        self.backend = backend_client
        self.state_machine = BookingStateMachine()

    def _plan_actions(self, state: BookingState, parsed: Optional[LLMOutputSchema]) -> List[str]:
        """Build a bounded action plan so the agent can chain tool use dynamically."""
        actions: List[str] = []

        if parsed:
            if parsed.intent == "cancel":
                return ["cancel"]
            if parsed.intent == "get_doctor_info":
                return ["get_doctor_info"]
            if parsed.intent == "check_appointment":
                return ["check_appointment"]

        if (state.doctorName or state.specialtyName) and not state.doctorId:
            actions.append("search_doctor")

        if state.doctorId and state.date:
            actions.append("fetch_slots")

        if state.doctorId and state.date and state.timeSlot:
            actions.append("create_appointment" if state.is_confirmed else "confirm_booking")
        elif parsed and parsed.nextAction == "ask_followup":
            actions.append("ask_followup")

        if not actions:
            if parsed and parsed.nextAction in {"search_doctor", "fetch_slots", "confirm_booking", "create_appointment", "final_response", "ask_followup"}:
                actions.append(parsed.nextAction)
            else:
                actions.append("final_response")

        return actions

    @staticmethod
    def _append_next_action(action_queue: List[str], cursor: int, next_action: str) -> None:
        """Insert a follow-up action right after the current step if it is not already queued."""
        if cursor < len(action_queue) and action_queue[cursor] == next_action:
            return
        action_queue.insert(cursor, next_action)

    def _format_reply_message(self, reply: str, intent: str, state: BookingState, actions: List[str], requires_input: bool) -> Dict[str, Any]:
        """Formats the response object according to the API contract."""
        return {
            "reply": reply,
            "intent": intent,
            "state": state.dict(),
            "actions": actions,
            "requires_user_input": requires_input
        }

    async def handle_message(self, session_id: str, message: str, jwt_token: Optional[str] = None) -> Dict[str, Any]:
        """Main entrypoint to process a message and return the next agent step."""
        logger.info(f"Handling message for session '{session_id}': '{message}'")
        
        # 1. Load existing session state
        state = session_store.get(session_id)
        
        # 2. Match selection index shortcuts if waiting for user choices
        is_handled_shortcut = False
        message_cleaned = message.strip()
        
        # A. Selecting a doctor from a list of options
        if state.doctors_list and re.match(r'^\d+$', message_cleaned):
            idx = int(message_cleaned) - 1
            if 0 <= idx < len(state.doctors_list):
                selected = state.doctors_list[idx]
                state.doctorId = selected.get("id")
                state.doctorName = selected.get("name")
                state.doctors_list = []  # Clear choices
                is_handled_shortcut = True
                logger.info(f"User selected doctor index {idx + 1}: {state.doctorName}")
                
        # B. Selecting a slot from a list of options
        elif state.slots_list and re.match(r'^\d+$', message_cleaned):
            idx = int(message_cleaned) - 1
            if 0 <= idx < len(state.slots_list):
                selected_slot = state.slots_list[idx]
                state.timeSlot = selected_slot
                state.slots_list = []  # Clear choices
                is_handled_shortcut = True
                logger.info(f"User selected time slot index {idx + 1}: {state.timeSlot}")

        # 3. Call LLM to parse intent/entities if it wasn't a quick index selection
        parsed = None
        if not is_handled_shortcut:
            try:
                parsed = await llm_parser.parse_message(message, state.messages)
                logger.info(f"LLM parsed result: intent={parsed.intent}, nextAction={parsed.nextAction}, entities={parsed.entities}")
                
                # Check for cancellation intent
                if parsed.intent == "cancel":
                    return self._format_reply_message(
                        reply="Hiện chưa hỗ trợ hủy lịch trên hệ thống này",
                        intent="cancel",
                        state=state,
                        actions=[],
                        requires_input=True
                    )
                
                # Apply updates to state
                state = self.state_machine.update_state(state, parsed)
            except Exception as exc:
                logger.exception("Failed to parse message using LLM")
                return self._format_reply_message(
                    reply="Xin lỗi, tôi gặp sự cố khi phân tích tin nhắn. Bạn vui lòng thử lại hoặc cung cấp thông tin khám.",
                    intent="unknown",
                    state=state,
                    actions=[],
                    requires_input=True
                )
        
        # 4. Fetch Customer Profile if not already fetched (and JWT is present)
        if jwt_token and not state.customerId:
            try:
                profile = await self.backend.get_customer_me(jwt_token)
                state.customerId = profile.get("customerId") or profile.get("id")
                state.customerName = profile.get("name")
                logger.info(f"Loaded customer profile: customerId={state.customerId}, name={state.customerName}")
            except UnauthorizedError as e:
                return self._format_reply_message(
                    reply=str(e),
                    intent=state.intent,
                    state=state,
                    actions=["require_login"],
                    requires_input=False
                )
            except Exception as e:
                logger.error(f"Error fetching customer profile: {e}")
                # We do not block the entire flow immediately, can try again later

        # Determine a bounded action plan using current state + LLM output.
        action_queue = self._plan_actions(state, parsed)
        next_action = action_queue[0]

        # 5. Core plan-and-act loop (bounded ReAct-lite)
        try:
            cursor = 0
            while cursor < len(action_queue) and cursor < 4:
                next_action = action_queue[cursor]
                cursor += 1
                logger.info(f"Evaluating booking action loop: next_action={next_action}")
                
                if next_action == "search_doctor":
                    # We need either doctorName or specialtyName to search
                    if not state.doctorName and not state.specialtyName:
                        next_action = "ask_followup"
                        reply_msg = "Bạn muốn khám với bác sĩ nào hoặc chuyên khoa nào?"
                        break
                        
                    # Search by doctorName
                    if state.doctorName:
                        docs = await self.backend.search_doctors(state.doctorName)
                        if not docs:
                            # Try searching by specialty if doctor name failed
                            if state.specialtyName:
                                docs = await self.backend.get_doctors_by_specialty(state.specialtyName)
                            
                        if not docs:
                            state.doctorName = None  # Reset invalid name
                            return self._format_reply_message(
                                reply=f"Không tìm thấy bác sĩ nào phù hợp với từ khóa '{state.doctorName or state.specialtyName}'. Bạn vui lòng cung cấp tên bác sĩ khác.",
                                intent=state.intent,
                                state=state,
                                actions=[],
                                requires_input=True
                            )
                        elif len(docs) == 1:
                            state.doctorId = docs[0].get("id") or docs[0].get("doctorId")
                            state.doctorName = docs[0].get("name")
                            state.doctors_list = []
                            logger.info(f"Doctor resolved to a single match: {state.doctorName} ({state.doctorId})")
                            # Chain immediately into slot fetching when possible.
                            if state.date:
                                self._append_next_action(action_queue, cursor, "fetch_slots")
                            else:
                                self._append_next_action(action_queue, cursor, "ask_followup")
                        else:
                            # Multiple doctors found - ask user to choose
                            state.doctors_list = [{"id": d.get("id"), "name": d.get("name")} for d in docs]
                            options_text = "\n".join([f"{i+1}. {d.get('name')}" for i, d in enumerate(docs)])
                            reply_msg = f"Tôi tìm thấy nhiều bác sĩ phù hợp. Vui lòng chọn số thứ tự bác sĩ bạn muốn đặt lịch:\n{options_text}"
                            return self._format_reply_message(
                                reply=reply_msg,
                                intent=state.intent,
                                state=state,
                                actions=["select_doctor"],
                                requires_input=True
                            )
                    # Search by specialty only
                    elif state.specialtyName:
                        docs = await self.backend.get_doctors_by_specialty(state.specialtyName)
                        if not docs:
                            state.specialtyName = None
                            return self._format_reply_message(
                                reply=f"Không tìm thấy bác sĩ nào thuộc chuyên khoa '{state.specialtyName}'. Vui lòng cung cấp lại chuyên khoa.",
                                intent=state.intent,
                                state=state,
                                actions=[],
                                requires_input=True
                            )
                        elif len(docs) == 1:
                            state.doctorId = docs[0].get("id") or docs[0].get("doctorId")
                            state.doctorName = docs[0].get("name")
                            state.doctors_list = []
                            if state.date:
                                self._append_next_action(action_queue, cursor, "fetch_slots")
                            else:
                                self._append_next_action(action_queue, cursor, "ask_followup")
                        else:
                            state.doctors_list = [{"id": d.get("id"), "name": d.get("name")} for d in docs]
                            options_text = "\n".join([f"{i+1}. {d.get('name')}" for i, d in enumerate(docs)])
                            reply_msg = f"Dưới đây là các bác sĩ thuộc chuyên khoa '{state.specialtyName}'. Vui lòng chọn số thứ tự bác sĩ:\n{options_text}"
                            return self._format_reply_message(
                                reply=reply_msg,
                                intent=state.intent,
                                state=state,
                                actions=["select_doctor"],
                                requires_input=True
                            )
                            
                elif next_action == "fetch_slots":
                    if not state.doctorId:
                        next_action = "search_doctor"
                        continue
                    if not state.date:
                        next_action = "ask_followup"
                        reply_msg = f"Vui lòng cho biết ngày bạn muốn đặt khám với bác sĩ {state.doctorName} (ví dụ: ngày mai, thứ hai tuần này, hoặc YYYY-MM-DD)."
                        break
                        
                    # Fetch slots from backend
                    slots_data = await self.backend.get_available_slots(state.doctorId, state.date)
                    if not slots_data:
                        return self._format_reply_message(
                            reply=f"Rất tiếc, bác sĩ {state.doctorName} không có lịch khám nào khả dụng vào ngày {state.date}. Vui lòng chọn một ngày khám khác.",
                            intent=state.intent,
                            state=state,
                            actions=[],
                            requires_input=True
                        )
                        
                    # Filter slots that are available
                    available_slots = []
                    for item in slots_data:
                        if isinstance(item, str):
                            available_slots.append(item)
                        elif isinstance(item, dict):
                            if item.get("available", True) is not False:
                                available_slots.append(item)

                    if not available_slots:
                        return self._format_reply_message(
                            reply=f"Bác sĩ {state.doctorName} đã kín lịch vào ngày {state.date}. Vui lòng chọn ngày khám khác.",
                            intent=state.intent,
                            state=state,
                            actions=[],
                            requires_input=True
                        )
                        
                    # Extract raw slot strings for matching
                    available_slot_strs = []
                    plan_map = {}  # Map slot string to planId if present in BE response
                    
                    for item in available_slots:
                        if isinstance(item, str):
                            available_slot_strs.append(item)
                        elif isinstance(item, dict):
                            slot_str = item.get("timeSlot", "")
                            plan_id = item.get("planId")
                            if slot_str:
                                available_slot_strs.append(slot_str)
                                if plan_id:
                                    plan_map[slot_str] = plan_id

                    # If user has specified a time, try to match it
                    if state.timeSlot:
                        matched = find_matching_slots(state.timeSlot, available_slot_strs)
                        if len(matched) == 1:
                            state.timeSlot = matched[0]
                            # Assign planId if mapped
                            if matched[0] in plan_map:
                                state.planId = plan_map[matched[0]]
                            state.slots_list = []
                            logger.info(f"Resolved single slot match: {state.timeSlot}")
                            self._append_next_action(action_queue, cursor, "confirm_booking")
                        elif len(matched) > 1:
                            # Multiple matching slots found
                            state.slots_list = matched
                            options_text = "\n".join([f"{i+1}. {slot}" for i, slot in enumerate(matched)])
                            reply_msg = f"Tôi thấy có nhiều khung giờ trống phù hợp với thời gian bạn chọn. Vui lòng chọn số thứ tự khung giờ mong muốn:\n{options_text}"
                            return self._format_reply_message(
                                reply=reply_msg,
                                intent=state.intent,
                                state=state,
                                actions=["select_slot"],
                                requires_input=True
                            )
                        else:
                            # Invalid time slot specified
                            state.timeSlot = None  # Reset invalid slot
                            options_text = "\n".join([f"- {slot}" for slot in available_slot_strs[:8]])
                            reply_msg = f"Khung giờ bạn yêu cầu hiện không có sẵn. Dưới đây là các khung giờ trống còn lại của bác sĩ {state.doctorName} trong ngày {state.date}, vui lòng chọn lại:\n{options_text}"
                            return self._format_reply_message(
                                reply=reply_msg,
                                intent=state.intent,
                                state=state,
                                actions=[],
                                requires_input=True
                            )
                    else:
                        # User has not selected a time yet, show all slots
                        state.slots_list = available_slot_strs
                        options_text = "\n".join([f"{i+1}. {slot}" for i, slot in enumerate(available_slot_strs)])
                        reply_msg = f"Dưới đây là danh sách khung giờ trống của bác sĩ {state.doctorName} vào ngày {state.date}. Vui lòng chọn số thứ tự khung giờ bạn muốn khám:\n{options_text}"
                        return self._format_reply_message(
                            reply=reply_msg,
                            intent=state.intent,
                            state=state,
                            actions=["select_slot"],
                            requires_input=True
                        )
                        
                elif next_action == "confirm_booking":
                    # Check if we have everything
                    if not state.doctorId or not state.date or not state.timeSlot:
                        self._append_next_action(action_queue, cursor, "ask_followup")
                        continue
                        
                    # Trigger confirmation response if not already confirmed
                    if not state.is_confirmed:
                        reply_msg = (
                            f"Tôi đã ghi nhận thông tin đặt lịch khám của bạn:\n"
                            f"- Họ tên khách hàng: {state.customerName or 'Chưa xác định'}\n"
                            f"- Bác sĩ khám: {state.doctorName}\n"
                            f"- Ngày khám: {state.date}\n"
                            f"- Giờ khám: {state.timeSlot}\n"
                            f"- Lý do khám: {state.reason or 'Khám tổng quát'}\n"
                            f"Bạn có xác nhận thông tin này là đúng không? (Trả lời 'Đồng ý' hoặc 'Xác nhận' để đặt lịch)."
                        )
                        return self._format_reply_message(
                            reply=reply_msg,
                            intent=state.intent,
                            state=state,
                            actions=["confirm_booking"],
                            requires_input=True
                        )
                    else:
                        # User already confirmed (via needConfirmation)
                        self._append_next_action(action_queue, cursor, "create_appointment")
                        
                elif next_action == "create_appointment":
                    if not jwt_token:
                        return self._format_reply_message(
                            reply="Yêu cầu đăng nhập. Vui lòng đăng nhập hệ thống để tiếp tục đặt lịch.",
                            intent=state.intent,
                            state=state,
                            actions=["require_login"],
                            requires_input=False
                        )
                    if not state.customerId:
                        # Attempt to resolve customerId again
                        profile = await self.backend.get_customer_me(jwt_token)
                        state.customerId = profile.get("customerId") or profile.get("id")
                        state.customerName = profile.get("name")
                        
                    # Create payload
                    payload = {
                        "doctorId": state.doctorId,
                        "customerId": state.customerId,
                        "date": state.date,
                        "timeSlot": state.timeSlot
                    }
                    if state.planId:
                        payload["planId"] = state.planId
                    if state.reason:
                        payload["reason"] = state.reason
                    if state.notes:
                        payload["notes"] = state.notes
                        
                    # Post appointment
                    result = await self.backend.create_appointment(jwt_token, payload)
                    appointment_id = result.get("id") or result.get("appointmentId", "N/A")
                    
                    reply_msg = (
                        f"🎉 Đặt lịch khám bệnh thành công!\n"
                        f"- Mã lịch hẹn: {appointment_id}\n"
                        f"- Bác sĩ khám: {state.doctorName}\n"
                        f"- Thời gian: {state.timeSlot} ngày {state.date}\n"
                        f"Hệ thống đã lưu thông tin và gửi thông báo xác nhận. Cảm ơn bạn!"
                    )
                    
                    # Store messages history before clearing
                    state.messages.append({"role": "user", "content": message})
                    state.messages.append({"role": "assistant", "content": reply_msg})
                    
                    # Clear booking data for next session but keep chat history
                    session_store.clear(session_id)
                    
                    return self._format_reply_message(
                        reply=reply_msg,
                        intent="book_appointment",
                        state=state,
                        actions=["booking_success"],
                        requires_input=True
                    )
                    
                elif next_action == "get_doctor_info":
                    doc_name = state.doctorName or (parsed.entities.doctorName if parsed else None)
                    if not doc_name:
                        reply_msg = "Bạn muốn hỏi thông tin về bác sĩ nào ạ?"
                        break
                        
                    docs = await self.backend.search_doctors(doc_name)
                    if not docs:
                        reply_msg = f"Không tìm thấy bác sĩ nào có tên '{doc_name}' trên hệ thống."
                        break
                        
                    doc = docs[0]
                    # Format prompt for LLM to summarize doctor profile nicely
                    prompt = (
                        f"Dựa trên dữ liệu bác sĩ từ hệ thống dưới đây, hãy soạn một câu trả lời giới thiệu chi tiết "
                        f"cho bệnh nhân bằng tiếng Việt tự nhiên và thân thiện (bao gồm tên, chuyên khoa, mô tả/chuyên môn và giá khám nếu có):\n"
                        f"Dữ liệu hệ thống: {doc}\n"
                        f"Câu hỏi của bệnh nhân: {message}"
                    )
                    llm_response = await booking_config.llm.ainvoke(prompt)
                    reply_msg = llm_response.content
                    break

                elif next_action == "check_appointment":
                    # Try to extract appointmentId
                    apt_id = parsed.entities.appointmentId if parsed else None
                    
                    if not apt_id:
                        # Extract via regex in user message
                        match = re.search(r'(apt_[a-zA-Z0-9_]+|\b[0-9]{4,}\b)', message)
                        if match:
                            apt_id = match.group(1)
                            
                    if not apt_id:
                        # Check conversation history for last booked appointment id
                        for msg_dict in reversed(state.messages):
                            match = re.search(r'Mã lịch hẹn:\s*([^\s\n]+)', msg_dict.get("content", ""))
                            if match:
                                apt_id = match.group(1)
                                break
                                
                    if not apt_id:
                        reply_msg = "Bạn vui lòng cung cấp mã lịch hẹn khám (ví dụ: apt_123) để tôi hỗ trợ tra cứu nhé."
                        break
                        
                    try:
                        apt = await self.backend.get_appointment(apt_id)
                        # Format prompt for LLM to explain appointment details nicely
                        prompt = (
                            f"Dựa trên dữ liệu lịch hẹn khám từ hệ thống dưới đây, hãy viết một tin nhắn thông báo "
                            f"chi tiết thông tin lịch khám cho bệnh nhân bằng tiếng Việt tự nhiên, lịch sự:\n"
                            f"Dữ liệu lịch hẹn: {apt}\n"
                            f"Yêu cầu của bệnh nhân: {message}"
                        )
                        llm_response = await booking_config.llm.ainvoke(prompt)
                        reply_msg = llm_response.content
                    except Exception as e:
                        logger.error(f"Error fetching appointment {apt_id}: {e}")
                        reply_msg = f"Không tìm thấy lịch hẹn khám nào có mã '{apt_id}' trên hệ thống. Vui lòng kiểm tra lại mã số lịch khám."
                    break

                elif next_action == "ask_followup":
                    reply_msg = parsed.userMessage if parsed else "Vui lòng cung cấp thêm thông tin đặt lịch khám."
                    break
                    
                else:  # final_response
                    reply_msg = parsed.userMessage if parsed else "Tôi có thể giúp gì thêm cho bạn?"
                    break

        except BookingAgentException as exc:
            logger.error(f"Booking Agent domain error: {exc}")
            return self._format_reply_message(
                reply=str(exc),
                intent=state.intent,
                state=state,
                actions=[],
                requires_input=True
            )
        except Exception as exc:
            logger.exception("Unexpected backend or engine crash")
            return self._format_reply_message(
                reply=f"Đã xảy ra lỗi hệ thống: {str(exc)}. Vui lòng thử lại sau.",
                intent=state.intent,
                state=state,
                actions=[],
                requires_input=True
            )

        # 6. Save State and Append message history
        state.messages.append({"role": "user", "content": message})
        state.messages.append({"role": "assistant", "content": reply_msg})
        session_store.set(session_id, state)
        
        return self._format_reply_message(
            reply=reply_msg,
            intent=state.intent,
            state=state,
            actions=[],
            requires_input=True
        )

# Initialize singleton orchestrator
orchestrator = Orchestrator()
