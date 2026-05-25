import logging
from .types import BookingState, LLMOutputSchema

logger = logging.getLogger("booking_agent.state_machine")

class BookingStateMachine:
    """Manages updates to BookingState to ensure logical transitions and reset states when entities change."""
    
    @staticmethod
    def update_state(state: BookingState, parsed: LLMOutputSchema) -> BookingState:
        """Merges new LLM output data into the existing session state."""
        entities = parsed.entities
        
        # 1. Update Intent
        state.intent = parsed.intent
        
        # 2. Check for doctor name changes (to reset IDs and slots)
        if entities.doctorName:
            clean_new_doc = entities.doctorName.strip()
            # If doctorName has changed, reset corresponding fetched IDs and slots
            if state.doctorName and clean_new_doc.lower() != state.doctorName.lower():
                logger.info(f"Doctor name changed from '{state.doctorName}' to '{clean_new_doc}'. Resetting IDs.")
                state.doctorName = clean_new_doc
                state.doctorId = None
                state.planId = None
                state.timeSlot = None
                state.is_confirmed = False
                state.doctors_list = []
                state.slots_list = []
            elif not state.doctorName:
                state.doctorName = clean_new_doc
                
        # 3. Check for specialty name changes
        if entities.specialtyName:
            clean_new_spec = entities.specialtyName.strip()
            if state.specialtyName and clean_new_spec.lower() != state.specialtyName.lower():
                logger.info(f"Specialty changed from '{state.specialtyName}' to '{clean_new_spec}'. Resetting doctor info.")
                state.specialtyName = clean_new_spec
                state.doctorName = None
                state.doctorId = None
                state.planId = None
                state.timeSlot = None
                state.is_confirmed = False
                state.doctors_list = []
                state.slots_list = []
            elif not state.specialtyName:
                state.specialtyName = clean_new_spec

        # 4. Check for date changes
        if entities.date:
            clean_new_date = entities.date.strip()
            if state.date and clean_new_date != state.date:
                logger.info(f"Date changed from '{state.date}' to '{clean_new_date}'. Resetting slots.")
                state.date = clean_new_date
                state.planId = None
                state.timeSlot = None
                state.is_confirmed = False
                state.slots_list = []
            elif not state.date:
                state.date = clean_new_date

        # 5. Check for timeSlot changes
        if entities.timeSlot:
            clean_new_time = entities.timeSlot.strip()
            if state.timeSlot and clean_new_time != state.timeSlot:
                logger.info(f"Time slot changed from '{state.timeSlot}' to '{clean_new_time}'. Resetting confirmation.")
                state.timeSlot = clean_new_time
                state.is_confirmed = False
            elif not state.timeSlot:
                state.timeSlot = clean_new_time

        # 6. Update optional fields
        if entities.reason:
            state.reason = entities.reason
        if entities.notes:
            state.notes = entities.notes
            
        # 7. Force confirm if LLM explicitly sets needConfirmation
        if parsed.needConfirmation:
            state.is_confirmed = True
            
        return state
