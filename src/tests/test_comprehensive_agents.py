import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app
from app.schemas.chat import TaskRequest, TaskResponse
from app.orchestrator.nlu_parser import ExtractedInfo
from app.agents.flight_agent import call_flight_agent
from app.agents.hotel_agent import call_hotel_agent
from pydantic import BaseModel
from typing import Optional, List
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
        except:
            pass

class MockLLMHelper:
    def __init__(self):
        self.parse_intent_queue = []
        self.generate_response_queue = []

    def set_intent_sequence(self, sequence):
        self.parse_intent_queue = list(sequence)

    def set_response_sequence(self, sequence):
        self.generate_response_queue = list(sequence)

@pytest.fixture
def mock_llm_chain():
    helper = MockLLMHelper()
    with patch('app.orchestrator.nlu_parser.llm') as mock_nlu, \
         patch('app.orchestrator.graph.llm') as mock_graph, \
         patch('app.orchestrator.itinerary_flow.llm') as mock_itinerary:
         
        mock_structured = MagicMock()
        mock_nlu.with_structured_output.return_value = mock_structured
        mock_graph.with_structured_output.return_value = mock_structured
        mock_itinerary.with_structured_output.return_value = mock_structured
        
        def mock_invoke(messages):
            if helper.parse_intent_queue:
                item = helper.parse_intent_queue.pop(0)
                if isinstance(item, ExtractedInfo):
                    return item
                return ExtractedInfo(**item)
            return ExtractedInfo(intent="general_qa")
            
        mock_structured.invoke = mock_invoke
        
        mock_content = MagicMock()
        def mock_general_invoke(messages):
            if helper.generate_response_queue:
                mock_content.content = helper.generate_response_queue.pop(0)
            else:
                mock_content.content = "Here is your travel answer."
            return mock_content
            
        mock_nlu.invoke = mock_general_invoke
        mock_graph.invoke = mock_general_invoke
        mock_itinerary.invoke = mock_general_invoke
        
        yield helper

@pytest.fixture
def mock_serp_agents():
    with patch('app.orchestrator.flight_flow.call_flight_agent') as mock_flight, \
         patch('app.orchestrator.hotel_flow.call_hotel_agent') as mock_hotel, \
         patch('app.services.email_service.email_service.send_booking_confirmation', new_callable=AsyncMock) as mock_email:
        
        mock_flight.return_value = TaskResponse(
            task_id="flight_123",
            status="success",
            results=[
                {
                    "airline_name": "IndiGo",
                    "flight_numbers": "6E-204",
                    "departure_time": "06:00 AM",
                    "arrival_time": "08:30 AM",
                    "duration": "150m",
                    "stops": "Non-stop",
                    "price": "₹4,500.00",
                    "pricing": [
                        {"class": "Economy", "price": "₹4,500.00"},
                        {"class": "Business", "price": "₹12,000.00"}
                    ],
                    "booking_link": "https://flights.google.com/booking/6E204",
                    "origin_airport": "BLR",
                    "destination_airport": "DEL",
                    "airline_logo": "https://logo.png"
                },
                {
                    "airline_name": "Air India",
                    "flight_numbers": "AI-505",
                    "departure_time": "09:00 AM",
                    "arrival_time": "11:45 AM",
                    "duration": "165m",
                    "stops": "Non-stop",
                    "price": "₹5,200.00",
                    "pricing": [
                        {"class": "Economy", "price": "₹5,200.00"},
                        {"class": "Business", "price": "₹14,500.00"}
                    ],
                    "booking_link": "https://flights.google.com/booking/AI505",
                    "origin_airport": "BLR",
                    "destination_airport": "DEL",
                    "airline_logo": "https://logo.png"
                }
            ],
            metadata={"serpapi_request": {"q": "BLR to DEL"}, "serpapi_response": {"status": "ok"}}
        )

        mock_hotel.return_value = TaskResponse(
            task_id="hotel_123",
            status="success",
            results=[
                {
                    "name": "Grand Hyatt Goa",
                    "star_rating": 5,
                    "price_per_night": "₹8,500.00",
                    "amenities": ["Pool", "Free WiFi", "Spa", "Beach Access"],
                    "guest_rating": "4.8",
                    "images": ["https://hotel_image.jpg"],
                    "booking_url": "https://booking.com/grand-hyatt"
                },
                {
                    "name": "Taj Holiday Village",
                    "star_rating": 5,
                    "price_per_night": "₹11,000.00",
                    "amenities": ["Sea View", "Pool", "Breakfast Included"],
                    "guest_rating": "4.9",
                    "images": ["https://hotel_image2.jpg"],
                    "booking_url": "https://booking.com/taj"
                }
            ],
            metadata={"serpapi_request": {"q": "Goa hotels"}, "serpapi_response": {"status": "ok"}}
        )

        yield {"flight": mock_flight, "hotel": mock_hotel, "email": mock_email}


# ==============================================================================
# TEST 1: Full Flight Agent Flow (End-to-End multi-turn + Ticket Validation)
# ==============================================================================
def test_full_flight_booking_and_ticket_generation(mock_llm_chain, mock_serp_agents):
    session_id = "test_flight_e2e"

    # Turn 1: Start flight booking
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "origin": None, "destination": None}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "I want to book a flight"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Where are you flying from and to?" in data["message"]

    # Turn 2: Provide origin and destination
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "origin": "BLR", "destination": "DEL"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "From BLR to DEL"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "When are you departing?" in data["message"]

    # Turn 3: Provide departure date
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "departure_date": "2026-11-20"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "On 2026-11-20"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "one-way or return journey?" in data["message"]

    # Turn 4: Provide journey type -> Searches flights!
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "journey_type": "One Way"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "One way"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is False
    assert len(data["options"]) == 2
    assert data["options"][0]["airline_name"] == "IndiGo"
    assert data["options"][1]["airline_name"] == "Air India"

    # Turn 5: Select flight (IndiGo)
    mock_llm_chain.set_intent_sequence([
        {"intent": "select_flight", "selected_option_index": 0, "selected_class": "Economy"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "I want the IndiGo flight"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "How many adults, children, and infants" in data["message"]

    # Turn 6: Provide passenger count
    mock_llm_chain.set_intent_sequence([
        {"intent": "provide_passenger_count", "adults_count": 2, "children_count": 0, "infants_count": 0}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "2 adults"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "verify the number of passengers" in data["message"]
    assert "Adults: 2" in data["message"]

    # Turn 7: Confirm passenger count
    mock_llm_chain.set_intent_sequence([
        {"intent": "confirm"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Yes"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Passenger 1 of 2" in data["message"]

    # Turn 8: Provide details for Passenger 1
    mock_llm_chain.set_intent_sequence([
        {
            "intent": "provide_details",
            "passenger_name": "Alice Smith",
            "passenger_email": "alice@example.com",
            "passenger_contact": "+919876543210",
            "passenger_passport": "A1234567"
        }
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Alice Smith, alice@example.com, +919876543210, A1234567"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Passenger 2 of 2" in data["message"]

    # Turn 9: Provide details for Passenger 2
    mock_llm_chain.set_intent_sequence([
        {
            "intent": "provide_details",
            "passenger_name": "Bob Smith",
            "passenger_email": "bob@example.com",
            "passenger_contact": "+919876543211",
            "passenger_passport": "B7654321"
        }
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Bob Smith, bob@example.com, +919876543211, B7654321"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Perfect! Let's proceed with your booking" in data["message"]
    assert any(opt.get("label") == "Proceed With Booking" for opt in data["options"])

    # Turn 10: Complete payment -> Generate Flight Boarding Pass!
    mock_llm_chain.set_intent_sequence([
        {"intent": "payment_done"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Payment done"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is False
    assert "Payment Successful! Booking Confirmed." in data["message"]
    
    # Verify Flight Ticket structure
    ticket = data["ticket"]
    assert ticket is not None, "Flight ticket must be generated"
    assert "pnr" in ticket and len(ticket["pnr"]) == 6
    assert ticket["airline"] == "IndiGo"
    assert ticket["flight_numbers"] == "6E-204"
    assert ticket["origin"] == "BLR"
    assert ticket["destination"] == "DEL"
    assert ticket["flight_class"] == "Economy"
    assert ticket["price"] == "₹4,500.00"
    assert len(ticket["passengers"]) == 2
    assert ticket["passengers"][0]["name"] == "Alice Smith"
    assert ticket["passengers"][1]["name"] == "Bob Smith"
    assert "gate" in ticket
    assert "seat" in ticket


# ==============================================================================
# TEST 2: Full Hotel Agent Flow (End-to-End multi-turn + Ticket Validation)
# ==============================================================================
def test_full_hotel_booking_and_ticket_generation(mock_llm_chain, mock_serp_agents):
    session_id = "test_hotel_e2e"

    # Turn 1: Start hotel booking
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel", "hotel_city": "Goa"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "I want to book a hotel in Goa"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "When will you be checking in?" in data["message"]

    # Turn 2: Provide check-in date
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel", "check_in_date": "2026-11-25"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "2026-11-25"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "when is your check-out date?" in data["message"]

    # Turn 3: Provide check-out date (3 nights)
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel", "check_out_date": "2026-11-28"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "2026-11-28"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "How many guests will be staying?" in data["message"]

    # Turn 4: Provide guests
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "2 Adults"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "How many rooms would you like to book?" in data["message"]

    # Turn 5: Provide rooms
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "1 Room"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "What type of room would you prefer" in data["message"]

    # Turn 6: Room type
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Deluxe Room"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "What's your preferred budget" in data["message"]

    # Turn 7: Budget -> Immediately triggers hotel search!
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "₹8,000–₹12,000"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is False
    assert len(data["options"]) == 2
    assert data["options"][0]["name"] == "Grand Hyatt Goa"

    # Turn 8: Select Hotel (Grand Hyatt)
    mock_llm_chain.set_intent_sequence([
        {"intent": "select_hotel", "selected_option_index": 0}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Select Grand Hyatt Goa"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Guest's Full Name" in data["message"]

    # Turn 9: Provide Guest Name
    mock_llm_chain.set_intent_sequence([
        {"intent": "provide_details", "passenger_name": "Charlie Davis"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Charlie Davis"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Guest's Email Address" in data["message"]

    # Turn 10: Provide Guest Email
    mock_llm_chain.set_intent_sequence([
        {"intent": "provide_details", "passenger_email": "charlie@example.com"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "charlie@example.com"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Guest's Mobile Number" in data["message"]

    # Turn 11: Provide Guest Phone
    mock_llm_chain.set_intent_sequence([
        {"intent": "provide_details", "passenger_contact": "+919123456780"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "+919123456780"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Special Requests" in data["message"]

    # Turn 12: Special requests (Skip)
    mock_llm_chain.set_intent_sequence([
        {"intent": "general_qa"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Skip"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Estimated Arrival Time" in data["message"]

    # Turn 13: Arrival Time (Skip) -> Generates Booking Summary Invoice!
    mock_llm_chain.set_intent_sequence([
        {"intent": "general_qa"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Skip"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "📋 Booking Summary" in data["message"]
    assert "Grand Hyatt Goa" in data["message"]
    assert "3 night" in data["message"] or "₹25,500.00" in data["message"] # 8500 * 3 nights = 25500

    # Turn 14: Complete payment -> Generate Hotel Voucher Ticket!
    mock_llm_chain.set_intent_sequence([
        {"intent": "payment_done"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Payment done"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is False
    assert "Payment Successful! Booking Confirmed." in data["message"]

    # Verify Hotel Ticket structure
    ticket = data["ticket"]
    assert ticket is not None, "Hotel ticket must be generated"
    assert ticket["hotel_name"] == "Grand Hyatt Goa"
    assert ticket["city"] == "Goa"
    assert ticket["check_in_date"] == "2026-11-25"
    assert ticket["check_out_date"] == "2026-11-28"
    assert ticket["nights"] == 3
    assert ticket["guest_name"] == "Charlie Davis"
    assert "₹8,500.00" in ticket["price_per_night"]
    assert "₹25,500.00" in ticket["total_price"]


# ==============================================================================
# TEST 3: Chaining Flight -> Hotel with Parameter Inheritance
# ==============================================================================
def test_flight_to_hotel_chaining(mock_llm_chain, mock_serp_agents):
    session_id = "test_chaining_flow"

    # Fast forward: Initial prefilled flight search
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "origin": "BOM", "destination": "GOI", "departure_date": "2026-12-10", "journey_type": "One Way"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Book a flight from BOM to GOI on 2026-12-10"})
    assert res.status_code == 200
    assert len(res.json()["options"]) == 2

    # Select flight
    mock_llm_chain.set_intent_sequence([
        {"intent": "select_flight", "selected_option_index": 0}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Select first flight"})

    # Passenger count
    mock_llm_chain.set_intent_sequence([
        {"intent": "provide_passenger_count", "adults_count": 1}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "1 adult"})

    # Verify passenger count
    mock_llm_chain.set_intent_sequence([{"intent": "confirm"}])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Yes"})

    # Provide passenger details
    mock_llm_chain.set_intent_sequence([
        {"intent": "provide_details", "passenger_name": "Diana Prince", "passenger_email": "diana@amazon.com", "passenger_contact": "+919988776655", "passenger_passport": "W8889999"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Diana Prince, diana@amazon.com, +919988776655, W8889999"})

    # Payment
    mock_llm_chain.set_intent_sequence([{"intent": "payment_done"}])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Payment done"})
    assert res.json()["ticket"] is not None

    # Now user says: "Book a hotel" -> Bot prompts to confirm hotel in Goa!
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel"}
    ])
    res_city = client.post("/api/chat", json={"session_id": session_id, "message": "Book a hotel"})
    assert res_city.status_code == 200
    data_city = res_city.json()
    assert "I see you've booked a flight to Goa" in data_city["message"]

    # User confirms Goa -> Bot prompts to confirm check-in on flight arrival date (2026-12-10)!
    mock_llm_chain.set_intent_sequence([
        {"intent": "confirm"}
    ])
    res_date = client.post("/api/chat", json={"session_id": session_id, "message": "✅ Yes"})
    assert res_date.status_code == 200
    data_date = res_date.json()
    assert "Your flight arrival is on 2026-12-10" in data_date["message"]


# ==============================================================================
# TEST 4: Direct Flight & Hotel Agent Invocations
# ==============================================================================
def test_direct_flight_agent_execution():
    req = TaskRequest(
        task_id="direct_f1",
        session_id="session_f1",
        task_type="flight_search",
        parameters={"origin": "BLR", "destination": "DEL", "departure_date": "2026-11-20"}
    )
    with patch('httpx.get') as mock_http:
        mock_http.return_value.status_code = 200
        mock_http.return_value.json.return_value = {
            "best_flights": [
                {
                    "flights": [
                        {
                            "airline": "Vistara",
                            "flight_number": "UK808",
                            "departure_airport": {"name": "BLR", "time": "2026-11-20 14:00"},
                            "arrival_airport": {"name": "DEL", "time": "2026-11-20 16:45"},
                            "duration": 165
                        }
                    ],
                    "price": 6000
                }
            ]
        }
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "dummy_key"}):
            resp = call_flight_agent(req)
            assert resp.status == "success"
            assert len(resp.results) > 0
            assert resp.results[0]["airline_name"] == "Vistara"


def test_direct_hotel_agent_execution():
    req = TaskRequest(
        task_id="direct_h1",
        session_id="session_h1",
        task_type="hotel_search",
        parameters={"city": "Mumbai", "check_in_date": "2026-11-20", "check_out_date": "2026-11-22"}
    )
    with patch('httpx.get') as mock_http:
        mock_http.return_value.status_code = 200
        mock_http.return_value.json.return_value = {
            "properties": [
                {
                    "name": "The Taj Mahal Palace",
                    "extracted_hotel_class": 5,
                    "rate_per_night": {"lowest": "₹18,000"},
                    "overall_rating": 4.9,
                    "amenities": ["Spa", "Sea View"],
                    "images": [{"thumbnail": "https://taj.jpg"}]
                }
            ]
        }
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "dummy_key"}):
            resp = call_hotel_agent(req)
            assert resp.status == "success"
            assert len(resp.results) > 0
            assert resp.results[0]["name"] == "The Taj Mahal Palace"



# ==============================================================================
# TEST 5: Guardrails & Off-Topic Rejection
# ==============================================================================
def test_off_topic_hard_rejection(mock_llm_chain):
    session_id = "test_off_topic"
    
    # User asks a coding question
    mock_llm_chain.set_intent_sequence([{"intent": "general_qa"}])
    mock_llm_chain.set_response_sequence([
        "I'm sorry, but I can only assist with travel-related queries such as flight bookings, hotel reservations, and itinerary planning. Please ask a travel-related question."
    ])

    res = client.post("/api/chat", json={"session_id": session_id, "message": "Write a python script to sort an array"})
    assert res.status_code == 200
    data = res.json()
    assert "I can only assist with travel-related queries" in data["message"]


# ==============================================================================
# TEST 6: Itinerary Agent & Flow
# ==============================================================================
def test_itinerary_planning_flow(mock_llm_chain):
    session_id = "test_itinerary_flow"

    # Turn 1: User asks to plan an itinerary
    mock_llm_chain.set_intent_sequence([
        {"intent": "plan_itinerary"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Plan an itinerary"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "Which city or destination are you planning to visit?" in data["message"]

    # Turn 2: User provides city (Paris)
    mock_llm_chain.set_intent_sequence([
        {"intent": "plan_itinerary"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Paris"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "When are you planning to start your trip" in data["message"]

    # Turn 3: User provides start date
    mock_llm_chain.set_intent_sequence([
        {"intent": "plan_itinerary", "check_in_date": "2026-11-01"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "2026-11-01"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is True
    assert "How many days" in data["message"]

    # Turn 4: User provides duration (3 days) -> Generates luxury itinerary!
    mock_llm_chain.set_intent_sequence([
        {"intent": "plan_itinerary"}
    ])
    mock_llm_chain.set_response_sequence([
        "✨ **Luxury 3-Day Paris Itinerary** ✨\n\n**Day 1**: Eiffel Tower & Seine River Cruise\n**Day 2**: Louvre Museum & Montmartre\n**Day 3**: Palace of Versailles & Gourmet Dining"
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "3 days"})
    assert res.status_code == 200
    data = res.json()
    assert data["clarification_needed"] is False
    assert "Luxury 3-Day Paris Itinerary" in data["message"]
    assert "Eiffel Tower" in data["message"]


# ==============================================================================
# TEST 7: Hotel Modification & Detail Cloning
# ==============================================================================
def test_hotel_modification_and_detail_cloning(mock_llm_chain, mock_serp_agents):
    session_id = "test_hotel_mod"

    # Step A: Perform a complete hotel booking for Hotel A
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_hotel", "hotel_city": "Goa"},
        {"intent": "book_hotel", "check_in_date": "2026-11-25"},
        {"intent": "book_hotel", "check_out_date": "2026-11-27"},
        {"intent": "book_hotel"},
        {"intent": "book_hotel"},
        {"intent": "book_hotel"},
        {"intent": "book_hotel"}, # Budget triggers search
        {"intent": "select_hotel", "selected_option_index": 0}, # Select Grand Hyatt
        {"intent": "provide_details", "passenger_name": "Bruce Wayne"},
        {"intent": "provide_details", "passenger_email": "bruce@waynecorp.com"},
        {"intent": "provide_details", "passenger_contact": "+919876543219"},
        {"intent": "general_qa"},
        {"intent": "general_qa"},
        {"intent": "payment_done"}
    ])

    client.post("/api/chat", json={"session_id": session_id, "message": "I want to book a hotel in Goa"})
    client.post("/api/chat", json={"session_id": session_id, "message": "2026-11-25"})
    client.post("/api/chat", json={"session_id": session_id, "message": "2026-11-27"})
    client.post("/api/chat", json={"session_id": session_id, "message": "1 Adult"})
    client.post("/api/chat", json={"session_id": session_id, "message": "1 Room"})
    client.post("/api/chat", json={"session_id": session_id, "message": "Deluxe Room"})
    client.post("/api/chat", json={"session_id": session_id, "message": "₹8,000–₹12,000"})
    client.post("/api/chat", json={"session_id": session_id, "message": "Select Grand Hyatt"})
    client.post("/api/chat", json={"session_id": session_id, "message": "Bruce Wayne"})
    client.post("/api/chat", json={"session_id": session_id, "message": "bruce@waynecorp.com"})
    client.post("/api/chat", json={"session_id": session_id, "message": "+919876543219"})
    client.post("/api/chat", json={"session_id": session_id, "message": "Skip"})
    client.post("/api/chat", json={"session_id": session_id, "message": "Skip"})
    res_confirm = client.post("/api/chat", json={"session_id": session_id, "message": "Payment done"})
    assert res_confirm.json()["ticket"]["hotel_name"] == "Grand Hyatt Goa"

    # Step B: User now wants to switch and select Taj Holiday Village!
    mock_llm_chain.set_intent_sequence([
        {"intent": "select_hotel"}
    ])
    res_change = client.post("/api/chat", json={"session_id": session_id, "message": "I would like to select hotel Taj Holiday Village for ₹11,000"})
    assert res_change.status_code == 200
    data = res_change.json()
    assert "already have a confirmed booking at **Grand Hyatt Goa**" in data["message"]
    assert "cancel it and book **Taj Holiday Village**" in data["message"]

    # Step C: User confirms change -> Details (Bruce Wayne, email, phone) are cloned!
    mock_llm_chain.set_intent_sequence([
        {"intent": "confirm"}
    ])
    res_cloned = client.post("/api/chat", json={"session_id": session_id, "message": "Yes, cancel and book new"})
    assert res_cloned.status_code == 200
    data_cloned = res_cloned.json()
    assert "📋 Booking Summary" in data_cloned["message"]
    assert "Taj Holiday Village" in data_cloned["message"]
    assert "Bruce Wayne" in data_cloned["message"]


# ==============================================================================
# TEST 8: Passenger Details Validation & Error Recovery
# ==============================================================================
def test_passenger_validation_errors_and_recovery(mock_llm_chain, mock_serp_agents):
    session_id = "test_validation_recovery"

    # Fast forward to passenger details
    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "origin": "DEL", "destination": "BOM", "departure_date": "2026-11-15", "journey_type": "One Way"},
        {"intent": "select_flight", "selected_option_index": 0},
        {"intent": "provide_passenger_count", "adults_count": 1},
        {"intent": "confirm"}
    ])
    client.post("/api/chat", json={"session_id": session_id, "message": "Book flight from DEL to BOM on 2026-11-15"})
    client.post("/api/chat", json={"session_id": session_id, "message": "Select flight 1"})
    client.post("/api/chat", json={"session_id": session_id, "message": "1 adult"})
    res = client.post("/api/chat", json={"session_id": session_id, "message": "Yes"})
    assert "Passenger 1 of 1" in res.json()["message"]

    # Try invalid email & bad phone (no country code or missing digits)
    mock_llm_chain.set_intent_sequence([
        {
            "intent": "provide_details",
            "passenger_name": "J",
            "passenger_email": "invalid-email-format",
            "passenger_contact": "12345",
            "passenger_passport": "12"
        }
    ])
    res_err = client.post("/api/chat", json={"session_id": session_id, "message": "J, invalid-email-format, 12345, 12"})
    assert res_err.status_code == 200
    err_data = res_err.json()
    assert "⚠️ Validation Error" in err_data["message"]
    assert err_data["clarification_needed"] is True

    # Now recover with valid details
    mock_llm_chain.set_intent_sequence([
        {
            "intent": "provide_details",
            "passenger_name": "John Doe",
            "passenger_email": "john.doe@example.com",
            "passenger_contact": "+919876543210",
            "passenger_passport": "K9876543"
        }
    ])
    res_valid = client.post("/api/chat", json={"session_id": session_id, "message": "John Doe, john.doe@example.com, +919876543210, K9876543"})
    assert res_valid.status_code == 200
    valid_data = res_valid.json()
    assert "Proceed with your booking" in valid_data["message"] or "Proceed With Booking" in str(valid_data["options"])


# ==============================================================================
# TEST 9: Accommodation Suggestion Query (Direct Suggestion Card Interception)
# ==============================================================================
def test_accommodation_suggestion_query(mock_llm_chain, mock_serp_agents):
    session_id = "test_suggestions_card"

    # User says "suggest hostels in Goa" -> Fast track search with default dates!
    mock_llm_chain.set_intent_sequence([
        {"intent": "general_qa", "hotel_city": "Goa"}
    ])
    res = client.post("/api/chat", json={"session_id": session_id, "message": "suggest hostels in Goa"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["options"]) > 0
    assert data["options"][0]["name"] == "Grand Hyatt Goa"

