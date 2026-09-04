import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app
from app.schemas.chat import TaskResponse
from pydantic import BaseModel
from typing import Optional, List

class ExtractedIntent(BaseModel):
    intent: str
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None

class FlightOption(BaseModel):
    airline: str
    flight_number: str
    depart_time: str
    arrive_time: str
    duration: int
    price: float
    stops: int

class HotelOption(BaseModel):
    name: str
    star_rating: float
    price_per_night: float
    amenities: List[str]

import json
import time
import os

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_sessions():
    from app.api.routes import sessions, SESSIONS_FILE, SESSIONS_DIR
    sessions.clear()
    if os.path.exists(SESSIONS_FILE):
        try:
            os.remove(SESSIONS_FILE)
        except:
            pass
    if os.path.exists(SESSIONS_DIR):
        try:
            import shutil
            shutil.rmtree(SESSIONS_DIR)
            os.makedirs(SESSIONS_DIR, exist_ok=True)
        except Exception as e:
            print(f"Error cleaning sessions directory in tests: {e}")

from unittest.mock import patch, AsyncMock, MagicMock
from app.orchestrator.nlu_parser import ExtractedInfo

class MockLLMHelper:
    def __init__(self):
        self.parse_intent = MagicMock()
        self.generate_response = MagicMock()

@pytest.fixture
def mock_llm():
    helper = MockLLMHelper()
    with patch('app.orchestrator.nlu_parser.llm') as mock_nlu, \
         patch('app.orchestrator.graph.llm') as mock_graph, \
         patch('app.orchestrator.itinerary_flow.llm') as mock_itinerary:
         
        mock_structured = MagicMock()
        mock_nlu.with_structured_output.return_value = mock_structured
        mock_graph.with_structured_output.return_value = mock_structured
        mock_itinerary.with_structured_output.return_value = mock_structured
        
        def mock_invoke(messages):
            intent_val = helper.parse_intent()
            idx = getattr(intent_val, "selected_option_index", None)
            return ExtractedInfo(
                intent=intent_val.intent or "general_qa",
                origin=intent_val.origin,
                destination=intent_val.destination,
                departure_date=intent_val.departure_date,
                journey_type="One Way",
                selected_option_index=idx
            )
        mock_structured.invoke = mock_invoke
        
        mock_content = MagicMock()
        def mock_general_invoke(messages):
            mock_content.content = helper.generate_response()
            return mock_content
            
        mock_nlu.invoke = mock_general_invoke
        mock_graph.invoke = mock_general_invoke
        mock_itinerary.invoke = mock_general_invoke
        
        yield helper


@pytest.fixture
def mock_serp():
    with patch('app.orchestrator.flight_flow.call_flight_agent') as mock_flight, \
         patch('app.orchestrator.hotel_flow.call_hotel_agent') as mock_hotel:
        
        class SerpHelper:
            def __init__(self):
                self.search_flights = MagicMock()
                self.search_hotels = MagicMock()
                
        helper = SerpHelper()
        
        def mock_call_flight(request):
            flights = helper.search_flights()
            results = []
            for f in flights:
                results.append({
                    "airline_name": f.airline,
                    "flight_numbers": f.flight_number,
                    "departure_time": f.depart_time,
                    "arrival_time": f.arrive_time,
                    "duration": f"{f.duration}m",
                    "stops": "Non-stop" if f.stops == 0 else f"{f.stops} Stop",
                    "price": f.price,
                    "pricing": [{"class": "Economy", "price": f"INR {f.price:,.2f}"}]
                })
            return TaskResponse(
                task_id=request.task_id,
                status="success" if results else "failed",
                results=results,
                metadata={"agent_id": "flight_agent", "timestamp": time.time()}
            )
        mock_flight.side_effect = mock_call_flight
        
        def mock_call_hotel(request):
            hotels = helper.search_hotels()
            results = []
            for h in hotels:
                results.append({
                    "name": h.name,
                    "star_rating": h.star_rating,
                    "price_per_night": f"₹{h.price_per_night:,.2f}",
                    "amenities": h.amenities,
                    "guest_rating": "4.5",
                    "images": [""]
                })
            return TaskResponse(
                task_id=request.task_id,
                status="success" if results else "failed",
                results=results,
                metadata={"agent_id": "hotel_agent", "timestamp": time.time()}
            )
        mock_hotel.side_effect = mock_call_hotel
        
        yield {"flight": helper, "hotel": helper}

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_chat_flight_only_flow(mock_llm, mock_serp):
    session_id = "test_session_id"
    
    # 1. User says "Book a flight to NYC"
    mock_llm.parse_intent.return_value = ExtractedIntent(
        intent="book_flight",
        destination="NYC"
    )
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "Book a flight to NYC"})
    assert response.status_code == 200
    data = response.json()
    assert data["clarification_needed"] is True
    assert "Where are you flying from and to?" in data["message"]
    
    # 2. User provides the rest: "From LAX on 2026-10-10"
    mock_llm.parse_intent.return_value = ExtractedIntent(
        intent="book_flight",
        origin="LAX",
        destination="NYC",
        departure_date="2026-10-10"
    )
    
    # Mock the search response
    mock_serp["flight"].search_flights.return_value = [
        FlightOption(
            airline="Mock Airlines",
            flight_number="MK123",
            depart_time="10:00 AM",
            arrive_time="02:00 PM",
            duration=240,
            price=250.0,
            stops=0
        )
    ]
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "From LAX on 2026-10-10"})
    assert response.status_code == 200
    data = response.json()
    assert data["clarification_needed"] is False
    assert data["options"] is not None
    assert len(data["options"]) == 1
    assert data["options"][0]["airline_name"] == "Mock Airlines"
    assert "flight options" in data["message"]

def test_conversational_selection_and_interruption(mock_llm, mock_serp):
    session_id = "test_session_id_conversational"
    
    # 1. User says "Book a flight to NYC"
    mock_llm.parse_intent.return_value = ExtractedIntent(
        intent="book_flight",
        destination="NYC"
    )
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "Book a flight to NYC"})
    assert response.status_code == 200
    data = response.json()
    assert data["clarification_needed"] is True
    assert "Where are you flying from and to?" in data["message"]
    
    # 2. Interruption turn: User asks about the weather in Delhi *in the middle of booking*
    mock_llm.parse_intent.return_value = ExtractedIntent(
        intent="general_qa"
    )
    mock_llm.generate_response.return_value = "The weather in Delhi is currently sunny and warm."
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "what is the weather in Delhi?"})
    assert response.status_code == 200
    data = response.json()
    # It should have answered the question AND repeated the prompt
    assert data["clarification_needed"] is True
    assert "The weather in Delhi is currently sunny and warm." in data["message"]
    assert "where you are flying from and to" in data["followup_message"].lower()

    # 3. Second Interruption turn: User asks about local food
    mock_llm.parse_intent.return_value = ExtractedIntent(
        intent="general_qa"
    )
    mock_llm.generate_response.return_value = "You should try Butter Chicken and Chole Bhature."
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "what should I eat there?"})
    assert response.status_code == 200
    data = response.json()
    # It should have answered the question AND repeated the prompt
    assert data["clarification_needed"] is True
    assert "You should try Butter Chicken and Chole Bhature." in data["message"]
    assert "where you are flying from and to" in data["followup_message"].lower()

    # 4. User provides parameters: "From LAX on 2026-10-10"
    mock_llm.parse_intent.return_value = ExtractedIntent(
        intent="book_flight",
        origin="LAX",
        destination="NYC",
        departure_date="2026-10-10"
    )
    mock_serp["flight"].search_flights.return_value = [
        FlightOption(
            airline="Mock Airlines",
            flight_number="MK123",
            depart_time="10:00 AM",
            arrive_time="02:00 PM",
            duration=240,
            price=250.0,
            stops=0
        ),
        FlightOption(
            airline="Expensive Airlines",
            flight_number="EX999",
            depart_time="11:00 AM",
            arrive_time="03:00 PM",
            duration=240,
            price=999.0,
            stops=0
        )
    ]
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "From LAX on 2026-10-10"})
    assert response.status_code == 200
    data = response.json()
    assert data["clarification_needed"] is False
    assert len(data["options"]) == 2
    
    # 4.5. User asks "which is the expensive one in this?" (should answer QA without selecting yet)
    mock_llm.parse_intent.return_value = ExtractedIntent(
        intent="general_qa"
    )
    mock_llm.generate_response.return_value = '{"answer": "The expensive flight is Expensive Airlines flight EX999 for INR 999.00.", "identified_option_index": 1}'
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "which is the expensive one in this?"})
    assert response.status_code == 200
    data = response.json()
    assert data["clarification_needed"] is False
    assert "The expensive flight is Expensive Airlines flight EX999 for INR 999.00." in data["message"]
    assert "Would you like to proceed with this flight" in data["followup_message"]
    assert len(data["options"]) == 1
    
    # 5. User says "choose the expensive one"
    intent_val = MagicMock()
    intent_val.intent = "select_flight"
    intent_val.origin = None
    intent_val.destination = None
    intent_val.departure_date = None
    intent_val.selected_option_index = 0
    mock_llm.parse_intent.return_value = intent_val
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "choose the expensive one"})
    assert response.status_code == 200
    data = response.json()
    # It should transition to awaiting passenger count
    assert data["clarification_needed"] is True
    assert "How many adults, children, and infants" in data["message"]


def test_initial_message_prefilling(mock_llm, mock_serp):
    session_id = "test_session_id_prefilling"
    
    # User provides origin, destination, and departure_date in the initial query
    mock_llm.parse_intent.return_value = ExtractedIntent(
        intent="book_flight",
        origin="BLR",
        destination="DEL",
        departure_date="2026-10-15"
    )
    
    # Mock the search response
    mock_serp["flight"].search_flights.return_value = [
        FlightOption(
            airline="Mock Airlines",
            flight_number="MK123",
            depart_time="10:00 AM",
            arrive_time="02:00 PM",
            duration=240,
            price=250.0,
            stops=0
        )
    ]
    
    response = client.post("/api/chat", json={"session_id": session_id, "message": "Book a flight from BLR to DEL on 2026-10-15"})
    assert response.status_code == 200
    data = response.json()
    # It should search flights immediately since all details are prefilled!
    assert data["clarification_needed"] is False
    assert data["options"] is not None
    assert len(data["options"]) == 1
    assert data["options"][0]["airline_name"] == "Mock Airlines"
    assert "flight options" in data["message"]


