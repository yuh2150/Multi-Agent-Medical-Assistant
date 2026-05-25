from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class BookingState(BaseModel):
    """The complete state of a booking session."""
    messages: List[Dict[str, str]] = Field(default_factory=list)  # Conversation history
    customerId: Optional[str] = None
    customerName: Optional[str] = None
    doctorName: Optional[str] = None
    doctorId: Optional[str] = None
    specialtyName: Optional[str] = None
    date: Optional[str] = None           # Format: YYYY-MM-DD
    timeSlot: Optional[str] = None       # Format: HH:mm-HH:mm
    planId: Optional[str] = None         # ID of the plan / working day of doctor
    reason: Optional[str] = None
    notes: Optional[str] = None
    intent: str = "unknown"              # book_appointment | search_doctor | check_available_slots | cancel | unknown
    doctors_list: List[Dict[str, Any]] = Field(default_factory=list)  # Suggested doctors for user selection
    slots_list: List[str] = Field(default_factory=list)  # Available slots for user selection
    is_confirmed: bool = False           # Has user confirmed the booking details?
    last_action: Optional[str] = None

class LLMEntities(BaseModel):
    """Extracted entities from user message."""
    doctorName: Optional[str] = None
    specialtyName: Optional[str] = None
    date: Optional[str] = None
    timeSlot: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    appointmentId: Optional[str] = None  # ID of appointment to lookup

class LLMOutputSchema(BaseModel):
    """Fixed schema returned by the LLM parsing phase."""
    intent: str = Field(description="Intent of the message: book_appointment, search_doctor, check_available_slots, get_doctor_info, check_appointment, cancel, unknown")
    entities: LLMEntities = Field(description="Extracted medical booking entities")
    missingFields: List[str] = Field(default_factory=list, description="Fields that are required but missing (from: doctorName, date, timeSlot)")
    needConfirmation: bool = Field(default=False, description="Whether the user is ready to confirm the appointment information")
    nextAction: str = Field(description="Next orchestrator action: ask_followup, search_doctor, fetch_slots, confirm_booking, create_appointment, get_doctor_info, check_appointment, final_response")
    userMessage: str = Field(description="The response message to display to the user or prompt for missing details")
