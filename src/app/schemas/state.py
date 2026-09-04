from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage

class FlightState(TypedDict):
    flight_params: Dict[str, Any] | None
    flight_result: Dict[str, Any] | None
    selected_flight: Dict[str, Any] | None
    passenger_details: Dict[str, Any] | None
    
    # Multi-passenger flow
    passenger_count: Dict[str, int] | None
    passengers_details: List[Dict[str, Any]] | None
    current_passenger_index: int | None
    ticket: Dict[str, Any] | None
    flight_email_sent: Optional[bool]

class HotelState(TypedDict):
    hotel_params: Dict[str, Any] | None
    hotel_result: Dict[str, Any] | None
    selected_hotel: Dict[str, Any] | None
    hotel_ticket: Dict[str, Any] | None
    temp_new_hotel: Dict[str, Any] | None
    hotel_email_sent: Optional[bool]

class CommonState(TypedDict):
    messages: List[BaseMessage]
    session_id: str
    current_step: str | None
    latest_intent: str | None
    pending_clarification: str | None
    quick_replies: List[str] | None
    final_response: str | None
    options_to_show: List[Dict[str, Any]] | None

    # Conversational enhancements
    interruption_question: str | None
    clarification_repeats: Dict[str, int] | None
    followup_message: str | None
    followup_quick_replies: List[str] | None
    serpapi_calls: List[Dict[str, Any]] | None

class ConversationState(CommonState, FlightState, HotelState):
    pass
