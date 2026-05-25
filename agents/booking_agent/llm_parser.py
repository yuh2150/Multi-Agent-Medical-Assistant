import json
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from .config import booking_config
from .types import LLMOutputSchema, LLMEntities
from .prompt import BOOKING_SYSTEM_PROMPT

logger = logging.getLogger("booking_agent.llm_parser")

class LLMParser:
    """Handles LLM communication and parses natural language into structured booking entities."""
    
    def __init__(self):
        self.llm = booking_config.llm
        self.structured_llm = None
        
        # Try initializing with structured output
        try:
            self.structured_llm = self.llm.with_structured_output(LLMOutputSchema)
            logger.info("Successfully configured structured output for LLM.")
        except Exception as e:
            logger.warning(f"Structured output not supported or failed to initialize: {e}. Falling back to manual JSON parsing.")

    def _get_vietnamese_weekday(self, weekday_idx: int) -> str:
        weekdays = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        return weekdays[weekday_idx]

    def _get_current_date_info(self) -> Tuple[str, str, str]:
        """Get formatted current date information in Vietnamese."""
        now = datetime.now(booking_config.timezone)
        weekday = self._get_vietnamese_weekday(now.weekday())
        current_date_info = f"{weekday}, ngày {now.strftime('%d/%m/%Y')} (Giờ hiện tại: {now.strftime('%H:%M')})"
        today = now.strftime("%Y-%m-%d")
        
        # Calculate tomorrow
        from datetime import timedelta
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        
        return current_date_info, today, tomorrow

    def _build_messages(self, user_message: str, history: List[Dict[str, str]]) -> List[BaseMessage]:
        """Convert session history and current message into LangChain messages."""
        current_date_info, today, tomorrow = self._get_current_date_info()
        
        # Format the system prompt with date parameters
        sys_prompt = BOOKING_SYSTEM_PROMPT.format(
            current_date_info=current_date_info,
            today=today,
            tomorrow=tomorrow
        )
        
        messages = [SystemMessage(content=sys_prompt)]
        
        # Add conversation history (up to last 10 messages for context)
        for msg in history[-10:]:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
                
        # Append current user message
        messages.append(HumanMessage(content=user_message))
        return messages

    async def parse_message(self, user_message: str, history: List[Dict[str, str]]) -> LLMOutputSchema:
        """Invokes LLM and parses the result into LLMOutputSchema."""
        messages = self._build_messages(user_message, history)
        
        # 1. Try using Structured LLM
        if self.structured_llm:
            try:
                logger.info("Invoking LLM with structured output...")
                result = await self.structured_llm.ainvoke(messages)
                if isinstance(result, LLMOutputSchema):
                    return result
            except Exception as e:
                logger.error(f"Structured LLM invocation failed: {e}. Attempting fallback...")

        # 2. Fallback to standard LLM invoke and manual regex parsing
        logger.info("Executing fallback parsing using standard invoke...")
        try:
            response = await self.llm.ainvoke(messages)
            content = response.content
            return self._manual_parse_json(content)
        except Exception as e:
            logger.error(f"Fallback LLM invocation failed: {e}")
            # Final safety fallback returning an unknown intent state
            return LLMOutputSchema(
                intent="unknown",
                entities=LLMEntities(),
                missingFields=[],
                needConfirmation=False,
                nextAction="final_response",
                userMessage="Xin lỗi, tôi gặp khó khăn khi xử lý yêu cầu của bạn. Bạn có muốn đặt lịch khám bệnh không?"
            )

    def _manual_parse_json(self, text: str) -> LLMOutputSchema:
        """Parse JSON from raw text using regex extraction and loads."""
        text = text.strip()
        logger.debug(f"Attempting manual JSON parsing of text: {text[:100]}...")
        
        # Try extracting JSON code block first
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find any curly brace structure
            json_match = re.search(r'(\{.*\})', text, re.DOTALL)
            json_str = json_match.group(1) if json_match else text

        try:
            data = json.loads(json_str)
            
            # Map elements into LLMOutputSchema manually to catch validation errors
            entities_data = data.get("entities", {})
            entities = LLMEntities(
                doctorName=entities_data.get("doctorName"),
                specialtyName=entities_data.get("specialtyName"),
                date=entities_data.get("date"),
                timeSlot=entities_data.get("timeSlot"),
                reason=entities_data.get("reason"),
                notes=entities_data.get("notes")
            )
            
            return LLMOutputSchema(
                intent=data.get("intent", "unknown"),
                entities=entities,
                missingFields=data.get("missingFields", []),
                needConfirmation=bool(data.get("needConfirmation", False)),
                nextAction=data.get("nextAction", "final_response"),
                userMessage=data.get("userMessage", "Tôi có thể giúp gì cho bạn?")
            )
        except Exception as e:
            logger.error(f"Manual JSON validation failed: {e}. Raw text was: {text}")
            # Return parsed fields from fallback logic
            intent = "unknown"
            if "hủy" in text.lower():
                intent = "cancel"
            elif any(k in text.lower() for k in ["đặt", "khám", "lịch", "bác sĩ"]):
                intent = "book_appointment"
                
            return LLMOutputSchema(
                intent=intent,
                entities=LLMEntities(),
                missingFields=[],
                needConfirmation=False,
                nextAction="final_response",
                userMessage=text if text else "Vui lòng cho tôi biết bạn cần hỗ trợ gì."
            )

# Import Tuple helper
from typing import Tuple
# Initialize singleton parser
llm_parser = LLMParser()
