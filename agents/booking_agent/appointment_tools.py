import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("booking_agent.appointment_tools")

def find_matching_slots(user_time: str, available_slots: List[Any]) -> List[str]:
    """
    Matches the user's requested time (already normalized by LLM, e.g. '09:00', '14:30', or 'sáng') to available slots.
    Handles available_slots as either List[str] e.g. ["09:00-09:30"]
    or List[Dict] e.g. [{"timeSlot": "09:00-09:30", "available": True}].
    """
    if not available_slots:
        return []
        
    # Extract slot strings
    slot_strs: List[str] = []
    for item in available_slots:
        if isinstance(item, str):
            slot_strs.append(item)
        elif isinstance(item, dict):
            # Only include if available is True
            if item.get("available", True) is not False:
                slot_strs.append(item.get("timeSlot", ""))
                
    slot_strs = [s for s in slot_strs if s]
    
    if not user_time:
        return slot_strs
        
    user_time_clean = user_time.strip().lower()
    
    # 1. Match directly (e.g., "09:00" matches "09:00-09:30")
    matches = []
    for slot in slot_strs:
        slot_clean = slot.lower()
        if user_time_clean in slot_clean:
            matches.append(slot)
            
    if matches:
        return matches
        
    # 2. General period matching if LLM extracted the period shift ("sáng", "chiều", "tối")
    period_matches = []
    for slot in slot_strs:
        try:
            # Extract start hour (e.g. "09" from "09:00-09:30")
            start_hour = int(slot.split("-")[0].split(":")[0])
            
            if "sáng" in user_time_clean and start_hour < 12:
                period_matches.append(slot)
            elif "chiều" in user_time_clean and 12 <= start_hour < 18:
                period_matches.append(slot)
            elif "tối" in user_time_clean and start_hour >= 18:
                period_matches.append(slot)
        except Exception:
            continue
            
    if period_matches:
        return period_matches
        
    return slot_strs

