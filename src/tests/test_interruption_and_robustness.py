import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app
from app.schemas.chat import TaskResponse
from app.orchestrator.nlu_parser import ExtractedInfo, extract_passenger_fields
import json
import os

client = TestClient(app)

def get_future_date(days_ahead: int = 15) -> str:
    return (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def get_past_date(days_back: int = 30) -> str:
    return (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

@pytest.fixture(autouse=True)
def clean_sessions():
    from app.api.routes import sessions, SESSIONS_FILE, SESSIONS_DIR
    sessions.clear()
    if os.path.exists(SESSIONS_FILE):
        try:
            os.remove(SESSIONS_FILE)
        except Exception:
            pass
    if os.path.exists(SESSIONS_DIR):
        try:
            import shutil
            shutil.rmtree(SESSIONS_DIR)
            os.makedirs(SESSIONS_DIR, exist_ok=True)
        except Exception:
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
    with patch("app.orchestrator.nlu_parser.llm") as mock_nlu, \
         patch("app.orchestrator.graph.llm") as mock_graph, \
         patch("app.orchestrator.itinerary_flow.llm") as mock_itinerary:
         
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
                mock_content.content = json.dumps({
                    "answer": "Goa has warm tropical weather year-round, ideal for beach activities.",
                    "identified_option_index": None
                })
            return mock_content
            
        mock_nlu.invoke = mock_general_invoke
        mock_graph.invoke = mock_general_invoke
        mock_itinerary.invoke = mock_general_invoke
        
        yield helper

@pytest.fixture
def mock_travel_agents():
    with patch("app.orchestrator.flight_flow.call_flight_agent") as mock_flight, \
         patch("app.orchestrator.hotel_flow.call_hotel_agent") as mock_hotel, \
         patch("app.services.email_service.email_service.send_booking_confirmation", new_callable=AsyncMock) as mock_email:
        
        mock_flight.return_value = TaskResponse(
            task_id="flight_100",
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
                    "origin_airport": "DEL",
                    "destination_airport": "BOM",
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
                    "origin_airport": "DEL",
                    "destination_airport": "BOM",
                    "airline_logo": "https://logo.png"
                }
            ],
            metadata={"source": "mock"}
        )

        mock_hotel.return_value = TaskResponse(
            task_id="hotel_200",
            status="success",
            results=[
                {
                    "name": "The Taj Mahal Palace",
                    "star_rating": 5,
                    "price_per_night": "₹15,000.00",
                    "amenities": ["Pool", "Free WiFi", "Spa", "Sea View"],
                    "guest_rating": "4.9",
                    "images": ["https://hotel_image.jpg"],
                    "booking_url": "https://booking.com/taj-mumbai"
                },
                {
                    "name": "Trident Nariman Point",
                    "star_rating": 5,
                    "price_per_night": "₹9,500.00",
                    "amenities": ["Gym", "Free WiFi", "Restaurant"],
                    "guest_rating": "4.7",
                    "images": ["https://hotel_image2.jpg"],
                    "booking_url": "https://booking.com/trident-mumbai"
                }
            ],
            metadata={"source": "mock"}
        )

        yield mock_flight, mock_hotel


# =========================================================================
# 1. OPTION SELECTION PERSPECTIVES (Different flight/hotel choices)
# =========================================================================

def test_flight_different_option_selections(mock_llm_chain, mock_travel_agents):
    """Test selecting option 1 vs option 2 vs selecting by structured button format"""
    future_date = get_future_date(10)
    session_id = "test_opt_select"

    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "origin": "DEL", "destination": "BOM", "departure_date": future_date, "journey_type": "One Way"},
        {"intent": "select_flight", "selected_airline": "Air India", "selected_class": "Economy", "selected_price": "₹5,200.00"},
        {"intent": "provide_passenger_count", "adults_count": 1},
        {"intent": "confirm"},
        {"intent": "provide_details", "passenger_name": "Soujanya Hegde", "passenger_email": "soujanya@gmail.com", "passenger_contact": "+918088091773", "passenger_passport": "AR564543"}
    ])

    # Step 1: Search flight
    res1 = client.post("/api/chat", json={"session_id": session_id, "message": f"Book a flight from DEL to BOM on {future_date}"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1.get("options", [])) == 2

    # Option Selection: Select button format for Option 2 (Air India)
    res2 = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "I would like to select Economy class on Air India (AI-505) for ₹5,200.00"
    })
    assert res2.status_code == 200
    reply2 = res2.json().get("message", "").lower()
    assert "adults" in reply2 or "passenger" in reply2 or "traveling" in reply2

    # Set passenger count
    res3 = client.post("/api/chat", json={"session_id": session_id, "message": "1"})
    assert res3.status_code == 200
    res3_conf = client.post("/api/chat", json={"session_id": session_id, "message": "Yes"})
    assert res3_conf.status_code == 200

    # Provide passenger details
    res4 = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "Soujanya Hegde, soujanya@gmail.com, +918088091773, Pass AR564543"
    })
    assert res4.status_code == 200
    reply4 = res4.json().get("message", "")
    assert "summary" in reply4.lower() or "payment" in reply4.lower() or "soujanya" in reply4.lower()


def test_hotel_different_option_selections(mock_llm_chain, mock_travel_agents):
    """Test full hotel slot collection and selecting option 2 (Trident)"""
    checkin = get_future_date(10)
    checkout = get_future_date(12)
    session_id = "test_hotel_select"

    # 1. Start hotel search
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel", "hotel_city": "Mumbai"}])
    res1 = client.post("/api/chat", json={"session_id": session_id, "message": "I want a hotel in Mumbai"})
    assert res1.status_code == 200

    # 2. Check-in date
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel", "check_in_date": checkin}])
    res2 = client.post("/api/chat", json={"session_id": session_id, "message": checkin})
    assert res2.status_code == 200

    # 3. Check-out date
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel", "check_out_date": checkout}])
    res3 = client.post("/api/chat", json={"session_id": session_id, "message": checkout})
    assert res3.status_code == 200

    # 4. Guests
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel"}])
    res4 = client.post("/api/chat", json={"session_id": session_id, "message": "2 Adults"})
    assert res4.status_code == 200

    # 5. Rooms
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel"}])
    res5 = client.post("/api/chat", json={"session_id": session_id, "message": "1 Room"})
    assert res5.status_code == 200

    # 6. Room type
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel"}])
    res6 = client.post("/api/chat", json={"session_id": session_id, "message": "Deluxe Room"})
    assert res6.status_code == 200

    # 7. Budget -> searches hotels!
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel"}])
    res7 = client.post("/api/chat", json={"session_id": session_id, "message": "₹8,000–₹12,000"})
    assert res7.status_code == 200
    data7 = res7.json()
    assert len(data7.get("options", [])) == 2

    # 8. Select option 2
    mock_llm_chain.set_intent_sequence([{"intent": "select_hotel", "selected_option_index": 1}])
    res8 = client.post("/api/chat", json={"session_id": session_id, "message": "Select Trident Nariman Point"})
    assert res8.status_code == 200
    reply8 = res8.json().get("message", "").lower()
    assert "guest" in reply8 or "name" in reply8


# =========================================================================
# 2. INCORRECT / INVALID INPUT PERSPECTIVES
# =========================================================================

def test_invalid_date_input_and_recovery(mock_llm_chain, mock_travel_agents):
    """Test entering past dates, invalid formats, and recovering with valid dates"""
    past_date = get_past_date(10)
    future_date = get_future_date(15)
    session_id = "test_invalid_date"

    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "origin": "DEL", "destination": "BOM", "departure_date": past_date},
        {"intent": "book_flight", "departure_date": future_date, "journey_type": "One Way"}
    ])

    # 2.1 Attempt past departure date
    res1 = client.post("/api/chat", json={"session_id": session_id, "message": f"Book flight from DEL to BOM on {past_date}"})
    assert res1.status_code == 200
    reply1 = res1.json().get("message", "").lower()
    assert "date" in reply1 or "future" in reply1 or "invalid" in reply1

    # 2.2 Recover by entering a valid future date
    res2 = client.post("/api/chat", json={"session_id": session_id, "message": f"Let's go on {future_date}, One-Way"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2.get("options", [])) > 0


def test_invalid_passenger_contact_fields():
    """Test deterministic passenger extractor rejecting invalid emails and non-10-digit phones"""
    # 2.3 Invalid email without @ and phone without 10 digits
    bad_input = "Name: Alice, Email: notanemail, Phone: 123"
    fields_bad, errors_bad = extract_passenger_fields(bad_input)
    assert fields_bad.get("name") == "Alice"
    assert fields_bad.get("email") is None
    assert fields_bad.get("contact") is None
    assert len(errors_bad) == 0

    # 2.4 Correct input
    good_input = "Alice Smith, alice@example.com, +919876543210, M1234567"
    fields_good, errors_good = extract_passenger_fields(good_input)
    assert fields_good.get("name") == "Alice Smith"
    assert fields_good.get("email") == "alice@example.com"
    assert fields_good.get("contact") == "+919876543210"
    assert fields_good.get("passport") == "M1234567"
    assert len(errors_good) == 0


def test_gibberish_and_nonsensical_inputs(mock_llm_chain):
    """Test chatbot responding safely to random gibberish"""
    session_id = "test_gibberish"
    mock_llm_chain.set_intent_sequence([{"intent": "general_qa"}])
    mock_llm_chain.set_response_sequence(["I'm sorry, I can only assist with travel-related queries."])

    res = client.post("/api/chat", json={"session_id": session_id, "message": "asdfjkl qwerty 98127391823"})
    assert res.status_code == 200
    reply = res.json().get("message", "").lower()
    assert "travel" in reply or "help" in reply or "sorry" in reply


# =========================================================================
# 3. IRRELEVANT INFORMATION / OFF-TOPIC vs TRAVEL QA
# =========================================================================

def test_strictly_off_topic_decline(mock_llm_chain):
    """Test strictly non-travel questions (e.g. math, coding) are rejected politely"""
    session_id = "test_off_topic"
    queries = [
        "How do I reverse a linked list in Python?",
        "What is the quadratic formula?",
        "Who is the CEO of Microsoft?"
    ]
    mock_llm_chain.set_intent_sequence([{"intent": "general_qa"}] * len(queries))
    mock_llm_chain.set_response_sequence([
        "I'm sorry, but I can only assist with travel-related queries such as flight bookings, hotel reservations, and itinerary planning. Please ask a travel-related question."
    ] * len(queries))

    for q in queries:
        res = client.post("/api/chat", json={"session_id": session_id, "message": q})
        assert res.status_code == 200
        reply = res.json().get("message", "")
        assert "travel-related queries" in reply or "only assist with travel" in reply or "travel" in reply.lower()


def test_destination_and_travel_qa(mock_llm_chain):
    """Test general travel questions (places to visit, food, weather) are answered directly"""
    session_id = "test_travel_qa"
    travel_questions = [
        "What are the best places to visit in Mumbai?",
        "What food is famous in Goa?",
        "How is the weather in Delhi?",
        "What is the standard baggage allowance?"
    ]
    mock_llm_chain.set_intent_sequence([{"intent": "general_qa"}] * len(travel_questions))
    mock_llm_chain.set_response_sequence([
        "Top attractions in Mumbai include Gateway of India and Marine Drive.",
        "Goa is famous for fish curry, vindaloo, and fresh seafood.",
        "Delhi has pleasant weather in winter and warm summers.",
        "Standard domestic baggage is 15kg checked and 7kg cabin."
    ])

    for q in travel_questions:
        res = client.post("/api/chat", json={"session_id": session_id, "message": q})
        assert res.status_code == 200
        reply = res.json().get("message", "")
        assert len(reply) > 15
        assert "I can only assist with travel-related queries" not in reply


# =========================================================================
# 4. MID-FLOW INTERRUPTIONS AND PROPER RESUMPTION
# =========================================================================

def test_interruption_during_flight_slot_filling_and_resume(mock_llm_chain, mock_travel_agents):
    """
    Scenario: User starts flight booking -> asks off-topic baggage question ->
    bot answers baggage QA + reminds user about the pending flight booking step ->
    user provides destination -> booking proceeds seamlessly.
    """
    session_id = "test_interrupt_slot"
    future_date = get_future_date(12)

    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "origin": "DEL"},
        {"intent": "general_qa"},
        {"intent": "book_flight", "destination": "BOM", "departure_date": future_date, "journey_type": "One Way"}
    ])
    mock_llm_chain.set_response_sequence([
        json.dumps({
            "answer": "Standard domestic baggage allowance is 15 kg for check-in and 7 kg for cabin baggage.",
            "identified_option_index": None
        })
    ])

    # 1. Start partial booking
    res1 = client.post("/api/chat", json={"session_id": session_id, "message": "I want to fly from Delhi"})
    assert res1.status_code == 200

    # 2. Interruption: User asks about baggage
    res2 = client.post("/api/chat", json={"session_id": session_id, "message": "What is the standard luggage allowance?"})
    assert res2.status_code == 200
    reply2 = res2.json().get("message", "").lower()
    followup2 = (res2.json().get("followup_message") or "").lower()
    
    # Combined response answers question & prompts to resume booking
    assert "luggage" in reply2 or "baggage" in reply2 or "15" in reply2 or "allowance" in reply2 or "flying" in followup2 or "fly" in followup2
    
    # 3. Resumption: User gives destination & date
    res3 = client.post("/api/chat", json={"session_id": session_id, "message": f"Fly to Mumbai on {future_date}, One-Way"})
    assert res3.status_code == 200
    data3 = res3.json()
    assert len(data3.get("options", [])) > 0


def test_interruption_during_passenger_details_and_resume(mock_llm_chain, mock_travel_agents):
    """
    Scenario: During passenger details collection, user interrupts with greeting or destination QA ->
    bot answers -> state preserves passenger details -> user completes remaining fields -> reaches payment.
    """
    session_id = "test_interrupt_passenger"
    future_date = get_future_date(14)

    mock_llm_chain.set_intent_sequence([
        {"intent": "book_flight", "origin": "DEL", "destination": "BOM", "departure_date": future_date, "journey_type": "One Way"},
        {"intent": "select_flight", "selected_airline": "IndiGo", "selected_class": "Economy", "selected_price": "₹4,500.00"},
        {"intent": "provide_passenger_count", "adults_count": 1},
        {"intent": "confirm"},
        {"intent": "provide_details", "passenger_name": "Soujanya S P"},
        {"intent": "general_qa"},
        {"intent": "provide_details", "passenger_email": "soujanya@gmail.com", "passenger_contact": "+918088091773", "passenger_passport": "AR564543"}
    ])
    mock_llm_chain.set_response_sequence([
        json.dumps({
            "answer": "Mumbai is famous for Gateway of India, Marine Drive, and delicious Vada Pav.",
            "identified_option_index": None
        })
    ])

    # Search and select flight
    client.post("/api/chat", json={"session_id": session_id, "message": f"Book flight DEL to BOM on {future_date}, One-way"})
    client.post("/api/chat", json={"session_id": session_id, "message": "I would like to select Economy class on IndiGo (6E-204) for ₹4,500.00"})
    client.post("/api/chat", json={"session_id": session_id, "message": "1"})
    client.post("/api/chat", json={"session_id": session_id, "message": "Yes"})

    # Provide only passenger Name first
    res_name = client.post("/api/chat", json={"session_id": session_id, "message": "Soujanya S P"})
    assert res_name.status_code == 200

    # Interruption: User asks "What is famous in Mumbai?"
    res_interrupt = client.post("/api/chat", json={"session_id": session_id, "message": "What is famous in Mumbai?"})
    assert res_interrupt.status_code == 200
    interrupt_reply = res_interrupt.json().get("message", "").lower()
    followup = (res_interrupt.json().get("followup_message") or "").lower()
    
    assert "mumbai" in interrupt_reply or "gateway" in interrupt_reply or "vada pav" in interrupt_reply or "email" in followup or "soujanya" in followup

    # Resumption: User gives email, contact and passport
    res_resume = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "soujanya@gmail.com, +918088091773, AR564543"
    })
    assert res_resume.status_code == 200
    resume_reply = res_resume.json().get("message", "").lower()
    
    # Must preserve Soujanya S P and proceed to payment / booking summary!
    assert "soujanya" in resume_reply or "payment" in resume_reply or "summary" in resume_reply or "proceed" in resume_reply


def test_interruption_during_hotel_booking_and_resume(mock_llm_chain, mock_travel_agents):
    """
    Scenario: In hotel flow, user interrupts with a weather question ->
    bot answers -> user resumes answering hotel prompts -> completes hotel options search.
    """
    session_id = "test_interrupt_hotel"
    checkin = get_future_date(20)
    checkout = get_future_date(23)

    mock_llm_chain.set_response_sequence([
        json.dumps({
            "answer": "Goa has warm tropical weather year-round, ideal for beaches.",
            "identified_option_index": None
        })
    ])

    # 1. Start hotel inquiry
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel", "hotel_city": "Goa"}])
    client.post("/api/chat", json={"session_id": session_id, "message": "I need a hotel in Goa"})

    # 2. Interruption: User asks about weather in Goa
    mock_llm_chain.set_intent_sequence([{"intent": "general_qa"}])
    res_interrupt = client.post("/api/chat", json={"session_id": session_id, "message": "How is the weather in Goa?"})
    assert res_interrupt.status_code == 200
    reply = res_interrupt.json().get("message", "").lower()
    assert "goa" in reply or "weather" in reply or "tropical" in reply

    # 3. Resumption: User provides checkin date
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel", "check_in_date": checkin}])
    res_in = client.post("/api/chat", json={"session_id": session_id, "message": checkin})
    assert res_in.status_code == 200
    
    # 4. Check-out date
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel", "check_out_date": checkout}])
    res_out = client.post("/api/chat", json={"session_id": session_id, "message": checkout})
    assert res_out.status_code == 200
    
    # 5. Guests
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel"}])
    res_guests = client.post("/api/chat", json={"session_id": session_id, "message": "2 Adults"})
    assert res_guests.status_code == 200

    # 6. Rooms
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel"}])
    res_rooms = client.post("/api/chat", json={"session_id": session_id, "message": "1 Room"})
    assert res_rooms.status_code == 200

    # 7. Room type
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel"}])
    res_type = client.post("/api/chat", json={"session_id": session_id, "message": "Standard Room"})
    assert res_type.status_code == 200

    # 8. Budget -> triggers hotel search
    mock_llm_chain.set_intent_sequence([{"intent": "book_hotel"}])
    res_budget = client.post("/api/chat", json={"session_id": session_id, "message": "₹8,000–₹12,000"})
    assert res_budget.status_code == 200
    data_budget = res_budget.json()
    assert len(data_budget.get("options", [])) > 0
