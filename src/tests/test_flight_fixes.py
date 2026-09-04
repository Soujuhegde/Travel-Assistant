import pytest
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage
from app.orchestrator.nlu_parser import extract_passenger_fields, parse_intent
from app.orchestrator.flight_flow import handle_flight_clarification, get_flight_contextual_reminder
from app.orchestrator.graph import graph

def test_extract_passenger_fields_multi_comma():
    text = "Soujanya S P ,soujanyasp27@gmail.com , +91 8088091773 , AR564543"
    pax, errors = extract_passenger_fields(text)
    assert pax.get("name") == "Soujanya S P"
    assert pax.get("email") == "soujanyasp27@gmail.com"
    assert pax.get("contact") == "+918088091773"
    assert pax.get("passport") == "AR564543"
    assert len(errors) == 0

def test_extract_passenger_fields_labeled():
    text = "Name: Kushal S, Email: kushal@gmail.com, Phone: 9876543210, Passport: M1234567"
    pax, errors = extract_passenger_fields(text)
    assert pax.get("name") == "Kushal S"
    assert pax.get("email") == "kushal@gmail.com"
    assert pax.get("contact") == "+919876543210"
    assert pax.get("passport") == "M1234567"
    assert len(errors) == 0

def test_extract_passenger_fields_space_separated():
    text = "Kushal S kushal@gmail.com 9876543210 M1234567"
    pax, errors = extract_passenger_fields(text)
    assert pax.get("name") == "Kushal S"
    assert pax.get("email") == "kushal@gmail.com"
    assert pax.get("contact") == "+919876543210"
    assert pax.get("passport") == "M1234567"
    assert len(errors) == 0

def test_extract_passenger_step_by_step_no_overwrite():
    # Step 1: User provides name
    pax, _ = extract_passenger_fields("Yadunandan K D", {})
    assert pax.get("name") == "Yadunandan K D"
    
    # Step 2: User provides email
    pax, _ = extract_passenger_fields("yadu87@gmail.com", pax)
    assert pax.get("name") == "Yadunandan K D"
    assert pax.get("email") == "yadu87@gmail.com"
    
    # Step 3: User provides phone
    pax, _ = extract_passenger_fields("+91 8088091773", pax)
    assert pax.get("name") == "Yadunandan K D"
    assert pax.get("email") == "yadu87@gmail.com"
    assert pax.get("contact") == "+918088091773"
    
    # Step 4: User provides passport
    pax, _ = extract_passenger_fields("GR546787", pax)
    assert pax.get("name") == "Yadunandan K D"
    assert pax.get("email") == "yadu87@gmail.com"
    assert pax.get("contact") == "+918088091773"
    assert pax.get("passport") == "GR546787"

def test_hotel_to_flight_isolation_and_passenger_completion():
    """
    Recreate the exact sequence from dump_session.txt:
    1. Hotel was previously selected/booked (Lemon Tree Hotel in state).
    2. User enters flight passenger details.
    3. Verify that the response does NOT mention Lemon Tree Hotel or jump to hotel flow.
    """
    state = {
        "messages": [
            AIMessage(content="Please enter the Full Name for Passenger 2 of 2 (as per government ID/passport):"),
            HumanMessage(content="Yadunandan ,yadu87@gmail.com , +91 8088091773 , GR546787")
        ],
        "session_id": "test_isolation_1",
        "current_step": "awaiting_passenger_details",
        "flight_params": {"origin": "BLR", "destination": "MAA", "departure_date": "2026-09-05", "journey_type": "One Way"},
        "selected_flight": {
            "class": "Economy", "airline": "Air India AI 2840", "price": "INR 13,761.00",
            "flight_numbers": "AI 2840", "departure_time": "22:30", "arrival_time": "08:55",
            "airline_name": "Air India"
        },
        "selected_hotel": {
            "name": "Lemon Tree Hotel, Guindy, Chennai", "price": "₹7,095",
            "guest_name": "Soujanya S P", "guest_email": "soujanyasp27@gmail.com",
            "guest_phone": "+918088091773", "special_requests": "None", "arrival_time": "None"
        },
        "passenger_count": {"adults": 2, "children": 0, "infants": 0, "total": 2},
        "passengers_details": [
            {"name": "Soujanya S P", "email": "soujanyasp27@gmail.com", "contact": "+918088091773", "passport": "AR564543"}
        ],
        "current_passenger_index": 1,
        "pending_clarification": None,
        "flight_result": None,
        "hotel_result": None,
        "options_to_show": [],
        "serpapi_calls": []
    }
    
    new_state = parse_intent(state)
    
    # Verify Passenger 2 was extracted properly
    assert len(new_state["passengers_details"]) == 2
    pax2 = new_state["passengers_details"][1]
    assert pax2.get("name") == "Yadunandan"
    assert pax2.get("email") == "yadu87@gmail.com"
    assert pax2.get("contact") == "+918088091773"
    assert pax2.get("passport") == "GR546787"
    
    # Step should advance to awaiting_payment (for flight)
    assert new_state["current_step"] == "awaiting_payment"
    
    # Handle clarification for flight summary
    resp = handle_flight_clarification(new_state["current_step"], new_state)
    
    # Ensure it produces a flight Booking Summary, NOT a hotel message!
    msg = resp["final_response"]
    assert "Lemon Tree Hotel" not in msg
    assert "📋 Booking Summary" in msg
    assert "✈️ Flight: Air India" in msg
    assert "BLR ➔ MAA" in msg
    assert "Soujanya S P, Yadunandan" in msg
    assert resp["quick_replies"] == ["Payment done"]
    assert len(resp["options_to_show"]) == 1
    assert resp["options_to_show"][0]["type"] == "action_button"

def test_flight_step_by_step_clarification_prompts():
    state = {
        "passenger_count": {"total": 1},
        "current_passenger_index": 0,
        "passengers_details": [{}]
    }
    
    # 1. All 4 missing (start prompt)
    res = handle_flight_clarification("awaiting_passenger_details", state)
    assert "Name, Email, Contact No, Passport No" in res["final_response"]
    assert "Passenger 1 of 1" in res["final_response"]
    
    # 2. Only Name missing
    state["passengers_details"][0] = {"email": "k@g.com", "contact": "+919876543210", "passport": "ABC1234"}
    res = handle_flight_clarification("awaiting_passenger_details", state)
    assert "Full Name" in res["final_response"]
    
    # 3. Missing Email
    state["passengers_details"][0] = {"name": "Kushal S"}
    res = handle_flight_clarification("awaiting_passenger_details", state)
    assert "Email Address for Kushal S" in res["final_response"]
    
    # 4. Missing Phone
    state["passengers_details"][0] = {"name": "Kushal S", "email": "kushal@gmail.com"}
    res = handle_flight_clarification("awaiting_passenger_details", state)
    assert "Contact Number for Kushal S" in res["final_response"]
    
    # 5. Missing Passport
    state["passengers_details"][0] = {"name": "Kushal S", "email": "kushal@gmail.com", "contact": "+919876543210"}
    res = handle_flight_clarification("awaiting_passenger_details", state)
    assert "Passport Number for Kushal S" in res["final_response"]
