from fastapi import APIRouter, HTTPException, Query
from app.schemas.chat import (
    ChatRequest, ChatResponse, PaymentOrderRequest, PaymentVerifyRequest,
    PaymentFailureRequest, PaymentDetails, UpsellDetails, MCPExecuteRequest
)
from app.orchestrator.graph import graph
from app.services.payment_service import payment_service
from app.services.audit_service import audit_service
from app.services.campaign_service import campaign_service
from app.services.email_service import email_service
from app.agents.flight_agent import call_flight_agent
from app.agents.hotel_agent import call_hotel_agent
from app.schemas.chat import TaskRequest
from langchain_core.messages import HumanMessage, AIMessage
import uuid
import pickle
import os
import re
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

router = APIRouter()

SESSIONS_FILE = "sessions.pkl"
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)
sessions = {}

def load_sessions():
    global sessions
    # 1. Load legacy sessions.pkl if it exists
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "rb") as f:
                sessions.update(pickle.load(f))
            print(f"Loaded {len(sessions)} active sessions from legacy {SESSIONS_FILE}")
        except Exception as e:
            print(f"Error loading legacy sessions: {e}")
            
    # 2. Load individual sessions from directory
    try:
        if os.path.exists(SESSIONS_DIR):
            loaded_count = 0
            for filename in os.listdir(SESSIONS_DIR):
                if filename.endswith(".pkl"):
                    session_id = filename[:-4]
                    filepath = os.path.join(SESSIONS_DIR, filename)
                    try:
                        with open(filepath, "rb") as f:
                            sessions[session_id] = pickle.load(f)
                            loaded_count += 1
                    except Exception as e:
                        print(f"Error loading individual session {filename}: {e}")
            print(f"Loaded {loaded_count} individual sessions from {SESSIONS_DIR}. Total in-memory: {len(sessions)}")
    except Exception as e:
        print(f"Error reading sessions directory: {e}")

def save_session(session_id: str):
    if session_id not in sessions:
        return
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{session_id}.pkl")
        with open(session_file, "wb") as f:
            pickle.dump(sessions[session_id], f)
    except Exception as e:
        print(f"Error saving session {session_id} to file: {e}")

# Load sessions on startup
load_sessions()

def extract_price_number(price_str: Any) -> float:
    if not price_str:
        return 0.0
    if isinstance(price_str, (int, float)):
        return float(price_str)
    # Remove currency signs and formatting
    cleaned = re.sub(r"[^\d.]", "", str(price_str).split("/")[0])
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

def get_session_payment_data(state: Dict[str, Any]) -> Optional[PaymentDetails]:
    current_step = state.get("current_step")
    payment_steps = ["awaiting_payment", "flight_awaiting_payment", "flight_summary", "hotel_summary", "hotel_awaiting_payment"]
    
    if current_step not in payment_steps:
        return None

    session_id = state.get("session_id", "default")
    is_hotel = current_step.startswith("hotel_") or current_step == "hotel_summary"
    
    if is_hotel:
        hotel = state.get("selected_hotel") or {}
        price_num = extract_price_number(hotel.get("price") or hotel.get("price_per_night"))
        if price_num <= 0:
            price_num = 5000.0
        item_name = f"Hotel Stay at {hotel.get('name', 'Hotel Reservation')}"
        email = hotel.get("guest_email")
        phone = hotel.get("guest_phone")
        booking_type = "hotel"
    else:
        flight = state.get("selected_flight") or {}
        price_num = extract_price_number(flight.get("price"))
        if price_num <= 0:
            price_num = 4500.0
        
        # Multiply by passenger count
        pax_count = state.get("passenger_count")
        total_pax = 1
        if isinstance(pax_count, dict):
            total_pax = pax_count.get("total", 1)
        elif isinstance(pax_count, int):
            total_pax = pax_count
            
        price_num = price_num * total_pax
        airline = flight.get("airline_name") or flight.get("airline") or "Flight Booking"
        item_name = f"{airline} ({flight.get('flight_numbers', '')}) for {total_pax} passenger(s)"
        
        pax_list = state.get("passengers_details") or []
        email = pax_list[0].get("email") if pax_list else (state.get("passenger_details") or {}).get("email")
        phone = pax_list[0].get("contact") if pax_list else (state.get("passenger_details") or {}).get("contact")
        booking_type = "flight"

    order = payment_service.create_order(
        amount_rupees=price_num,
        session_id=session_id,
        booking_type=booking_type,
        item_name=item_name,
        customer_email=email,
        customer_phone=phone
    )
    
    state["payment_order_id"] = order["order_id"]
    state["payment_amount_rupees"] = price_num
    state["payment_details"] = order

    return PaymentDetails(
        order_id=order["order_id"],
        amount=order["amount"],
        amount_rupees=order["amount_rupees"],
        currency=order["currency"],
        key_id=order["key_id"],
        item_name=order["item_name"],
        customer_email=order["customer_email"],
        customer_phone=order["customer_phone"]
    )

def get_session_upsell_data(state: Dict[str, Any]) -> Optional[UpsellDetails]:
    current_step = state.get("current_step")
    if current_step not in ["booking_confirmed", "hotel_booking_confirmed"]:
        return None
        
    if state.get("upsell_accepted") or state.get("upsell_declined"):
        return None

    session_id = state.get("session_id", "default")
    is_hotel = current_step == "hotel_booking_confirmed"
    
    if is_hotel:
        offer_id = f"upsell_trans_{session_id[:6]}"
        title = "🚗 VIP Airport Pick-up & Transfer"
        desc = "Book a direct private luxury cab from the airport directly to your hotel."
        price = 799.0
        cat = "transfer"
    else:
        offer_id = f"upsell_ins_{session_id[:6]}"
        title = "🛡️ Comprehensive Travel & Baggage Insurance"
        desc = "Coverage up to ₹5,00,000 for trip cancellations, medical emergencies, and lost baggage."
        price = 499.0
        cat = "insurance"

    order = payment_service.create_order(
        amount_rupees=price,
        session_id=session_id,
        booking_type=f"upsell_{cat}",
        item_name=title
    )

    state["upsell_offer"] = {
        "offer_id": offer_id,
        "title": title,
        "price_rupees": price,
        "order_id": order["order_id"]
    }

    return UpsellDetails(
        offer_id=offer_id,
        title=title,
        description=desc,
        price_rupees=price,
        order_id=order["order_id"],
        key_id=order["key_id"],
        category=cat
    )


# ==============================================================================
# 1. CORE CHAT ENDPOINT
# ==============================================================================
@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    
    # Audit log user message
    audit_service.log_event(
        event_type="SEARCH_QUERY",
        session_id=session_id,
        actor="user",
        payload={"message": request.message}
    )

    # Get or create state
    state = sessions.get(session_id, {
        "messages": [],
        "session_id": session_id,
        "intent": None,
        "flight_params": {},
        "hotel_params": {},
        "pending_clarification": None,
        "flight_result": None,
        "hotel_result": None,
        "final_response": None,
        "options_to_show": [],
        "serpapi_calls": []
    })
    
    state["serpapi_calls"] = []
    state["messages"].append(HumanMessage(content=request.message))
    
    import anyio
    new_state = await anyio.to_thread.run_sync(graph.invoke, state)
    
    current_step = new_state.get("current_step")
    if current_step == "booking_confirmed" and not new_state.get("flight_email_sent"):
        pax_list = new_state.get("passengers_details") or []
        if not pax_list:
            pax_list = [new_state.get("passenger_details", {})]
        
        primary_email = pax_list[0].get("email") if pax_list else None
        if primary_email:
            ticket = new_state.get("ticket") or {}
            asyncio.create_task(email_service.send_booking_confirmation(primary_email, ticket))
            new_state["flight_email_sent"] = True
            audit_service.log_event(
                event_type="EMAIL_SENT",
                session_id=session_id,
                actor="system",
                payload={"email": primary_email, "type": "flight_ticket"}
            )
            
    elif current_step == "hotel_booking_confirmed" and not new_state.get("hotel_email_sent"):
        selected_hotel = new_state.get("selected_hotel") or {}
        primary_email = selected_hotel.get("guest_email")
        if primary_email:
            ticket = new_state.get("ticket") or {}
            asyncio.create_task(email_service.send_booking_confirmation(primary_email, ticket))
            new_state["hotel_email_sent"] = True
            new_state["hotel_ticket"] = ticket
            audit_service.log_event(
                event_type="EMAIL_SENT",
                session_id=session_id,
                actor="system",
                payload={"email": primary_email, "type": "hotel_ticket"}
            )

    final_resp = new_state.get("final_response", "I encountered an error processing that.")
    new_state["messages"].append(AIMessage(content=final_resp))
    
    followup_msg = new_state.get("followup_message")
    followup_replies = new_state.get("followup_quick_replies") or []
    
    # Compute real Razorpay payment details and upsell offers
    payment_details = get_session_payment_data(new_state)
    upsell_details = get_session_upsell_data(new_state)

    sessions[session_id] = new_state
    sessions[session_id]["followup_message"] = None
    sessions[session_id]["followup_quick_replies"] = []
    save_session(session_id)
    
    options_to_show = new_state.get("options_to_show") or []
    current_step = new_state.get("current_step")
    
    current_flow = None
    if current_step:
        if current_step.startswith("hotel_"):
            current_flow = "Hotel Booking"
        elif current_step.startswith("itinerary_") or current_step == "plan_itinerary":
            current_flow = "Itinerary Plan"
        elif current_step in ["awaiting_origin_dest", "awaiting_departure_date", "invalid_departure_date", "awaiting_journey_type", "ready_to_search", "flight_selecting", "awaiting_passenger_count", "verify_passenger_count", "awaiting_passenger_details", "awaiting_payment", "flight_summary", "flight_awaiting_payment", "booking_confirmed"]:
            current_flow = "Flight Booking"
            
    ticket = new_state.get("ticket") if current_step in ["booking_confirmed", "hotel_booking_confirmed"] else None
    is_clarifying = current_step not in [
        "ready_to_search", "flight_selecting", "hotel_ready_to_search", "hotel_selecting",
        "booking_confirmed", "hotel_booking_confirmed",
        "plan_itinerary", "general_qa", "start", None
    ]
    clarification_needed = new_state.get("pending_clarification") or is_clarifying
    quick_replies = new_state.get("quick_replies", [])

    return ChatResponse(
        message=final_resp,
        options=options_to_show,
        clarification_needed=bool(clarification_needed),
        quick_replies=quick_replies,
        ticket=ticket,
        followup_message=followup_msg,
        followup_quick_replies=followup_replies,
        current_flow=current_flow,
        payment_details=payment_details,
        upsell_details=upsell_details
    )


# ==============================================================================
# 2. REAL RAZORPAY PAYMENT ENDPOINTS (Gated Order Creation & Signature Verify)
# ==============================================================================
@router.post("/payment/create-order")
async def create_payment_order(req: PaymentOrderRequest):
    session_id = req.session_id
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
        
    state = sessions[session_id]
    payment_details = get_session_payment_data(state)
    if not payment_details:
        raise HTTPException(status_code=400, detail="No payable booking found in current session state")
        
    save_session(session_id)
    return payment_details

@router.post("/payment/verify")
async def verify_payment(req: PaymentVerifyRequest):
    session_id = req.session_id
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
        
    state = sessions[session_id]
    
    # 1. Cryptographic HMAC-SHA256 Signature Verification
    is_valid = payment_service.verify_signature(
        order_id=req.razorpay_order_id,
        payment_id=req.razorpay_payment_id,
        signature=req.razorpay_signature,
        session_id=session_id,
        actor="user"
    )
    
    if not is_valid:
        raise HTTPException(status_code=400, detail="Payment verification failed: Invalid cryptographic signature")
        
    # 2. Handle Upsell Payment vs Main Booking Payment
    if req.is_upsell:
        state["upsell_accepted"] = True
        state["upsell_payment_id"] = req.razorpay_payment_id
        ticket = state.get("ticket") or {}
        if req.upsell_type == "transfer":
            ticket["add_on"] = "🚗 VIP Airport Pick-up & Transfer Included"
        else:
            ticket["add_on"] = "🛡️ Comprehensive Travel Insurance Active"
        state["ticket"] = ticket
        save_session(session_id)
        
        audit_service.log_event(
            event_type="UPSELL_PAID",
            session_id=session_id,
            actor="user",
            payload={
                "upsell_type": req.upsell_type or "insurance",
                "payment_id": req.razorpay_payment_id
            },
            status="success"
        )
        return {
            "status": "success",
            "message": "Add-on successfully added and charged!",
            "ticket": ticket
        }

    # 3. Main Booking Payment: Transition state to confirmed and issue ticket
    is_hotel = state.get("current_step", "").startswith("hotel_") or state.get("current_step") == "hotel_summary"
    
    # Force step to confirm booking via LangGraph parse_intent
    state["payment_id"] = req.razorpay_payment_id
    state["payment_status"] = "verified"
    
    # Feed payment_done intent into graph to issue full ticket
    state["messages"].append(HumanMessage(content="Payment done"))
    import anyio
    new_state = await anyio.to_thread.run_sync(graph.invoke, state)
    
    # Send ticket confirmation email
    current_step = new_state.get("current_step")
    ticket = new_state.get("ticket") or {}
    
    primary_email = None
    if current_step == "booking_confirmed":
        pax_list = new_state.get("passengers_details") or []
        if pax_list:
            primary_email = pax_list[0].get("email")
    elif current_step == "hotel_booking_confirmed":
        hotel = new_state.get("selected_hotel") or {}
        primary_email = hotel.get("guest_email")
        
    if primary_email and not new_state.get("flight_email_sent") and not new_state.get("hotel_email_sent"):
        asyncio.create_task(email_service.send_booking_confirmation(primary_email, ticket))
        if current_step == "booking_confirmed":
            new_state["flight_email_sent"] = True
        else:
            new_state["hotel_email_sent"] = True

    audit_service.log_event(
        event_type="BOOKING_CONFIRMED",
        session_id=session_id,
        actor="system",
        payload={
            "ticket": ticket,
            "payment_id": req.razorpay_payment_id,
            "order_id": req.razorpay_order_id
        },
        status="success"
    )

    upsell = get_session_upsell_data(new_state)
    sessions[session_id] = new_state
    save_session(session_id)
    
    return {
        "status": "success",
        "message": new_state.get("final_response", "Payment verified and booking confirmed!"),
        "ticket": ticket,
        "upsell_details": upsell
    }

@router.post("/payment/failure")
async def record_payment_failure(req: PaymentFailureRequest):
    session_id = req.session_id
    if session_id in sessions:
        state = sessions[session_id]
        state["payment_status"] = "failed"
        save_session(session_id)
        
    res = payment_service.handle_payment_failure(
        order_id=req.order_id,
        reason=req.error_description,
        session_id=session_id,
        error_code=req.error_code
    )
    return res


# ==============================================================================
# 3. STRUCTURED CATALOG ENDPOINTS (Agent-Readable JSON for AI Buyers)
# ==============================================================================
@router.get("/catalog/flights")
async def get_flight_catalog(
    origin: str = Query(..., description="3-letter IATA origin code, e.g. DEL, BLR"),
    destination: str = Query(..., description="3-letter IATA destination code, e.g. BOM, GOI"),
    departure_date: Optional[str] = Query(None, description="Departure date (YYYY-MM-DD)"),
    max_price: Optional[float] = Query(None, description="Max price filter in INR"),
    airline: Optional[str] = Query(None, description="Filter by airline name")
):
    actual_origin = origin if isinstance(origin, str) else "DEL"
    actual_destination = destination if isinstance(destination, str) else "BOM"
    actual_departure_date = departure_date if isinstance(departure_date, str) else None
    actual_max_price = max_price if isinstance(max_price, (int, float)) else None
    actual_airline = airline if isinstance(airline, str) else None

    audit_service.log_event(
        event_type="CATALOG_BROWSE",
        session_id="catalog_agent",
        actor="agent",
        payload={"type": "flight", "origin": actual_origin, "destination": actual_destination, "date": actual_departure_date}
    )
    
    req = TaskRequest(
        task_id=f"cat_fl_{int(datetime.now().timestamp())}",
        task_type="flight_search",
        session_id="catalog_session",
        parameters={
            "origin": actual_origin.upper(),
            "destination": actual_destination.upper(),
            "departure_date": actual_departure_date or datetime.now().strftime("%Y-%m-%d"),
            "journey_type": "One Way"
        }
    )
    res = call_flight_agent(req)
    items = res.results or []
    
    # Filter by price and airline if requested
    filtered = []
    for item in items:
        price_val = extract_price_number(item.get("price"))
        if actual_max_price and price_val > actual_max_price:
            continue
        if actual_airline and actual_airline.lower() not in item.get("airline_name", "").lower():
            continue
        filtered.append({
            "flight_id": f"{item.get('airline_name', '')}_{item.get('flight_numbers', '')}",
            "airline": item.get("airline_name"),
            "flight_number": item.get("flight_numbers"),
            "departure_time": item.get("departure_time"),
            "arrival_time": item.get("arrival_time"),
            "duration": item.get("duration"),
            "stops": item.get("stops"),
            "price_inr": price_val,
            "pricing_classes": item.get("pricing", []),
            "origin": actual_origin.upper(),
            "destination": actual_destination.upper(),
            "booking_link": item.get("booking_link")
        })
    return {
        "catalog_type": "flights",
        "total_results": len(filtered),
        "results": filtered
    }

@router.get("/catalog/hotels")
async def get_hotel_catalog(
    city: str = Query(..., description="City or destination name, e.g. Mumbai, Goa"),
    check_in_date: Optional[str] = Query(None, description="Check-in date (YYYY-MM-DD)"),
    check_out_date: Optional[str] = Query(None, description="Check-out date (YYYY-MM-DD)"),
    max_price: Optional[float] = Query(None, description="Max price per night in INR"),
    min_rating: Optional[float] = Query(None, description="Minimum star rating (1-5)")
):
    actual_city = city if isinstance(city, str) else "Mumbai"
    actual_check_in = check_in_date if isinstance(check_in_date, str) else None
    actual_check_out = check_out_date if isinstance(check_out_date, str) else None
    actual_max_price = max_price if isinstance(max_price, (int, float)) else None
    actual_min_rating = min_rating if isinstance(min_rating, (int, float)) else None

    audit_service.log_event(
        event_type="CATALOG_BROWSE",
        session_id="catalog_agent",
        actor="agent",
        payload={"type": "hotel", "city": actual_city, "check_in": actual_check_in}
    )

    req = TaskRequest(
        task_id=f"cat_ht_{int(datetime.now().timestamp())}",
        task_type="hotel_search",
        session_id="catalog_session",
        parameters={
            "city": actual_city,
            "check_in_date": actual_check_in or datetime.now().strftime("%Y-%m-%d"),
            "check_out_date": actual_check_out or datetime.now().strftime("%Y-%m-%d")
        }
    )
    res = call_hotel_agent(req)
    items = res.results or []
    
    filtered = []
    for item in items:
        price_val = extract_price_number(item.get("price_per_night") or item.get("price"))
        star = float(item.get("star_rating") or 3.0)
        if actual_max_price and price_val > actual_max_price:
            continue
        if actual_min_rating and star < actual_min_rating:
            continue
        filtered.append({
            "hotel_id": item.get("name", "").replace(" ", "_").lower(),
            "name": item.get("name"),
            "city": actual_city.title(),
            "star_rating": star,
            "guest_rating": item.get("guest_rating", "4.5"),
            "price_per_night_inr": price_val,
            "amenities": item.get("amenities", []),
            "booking_url": item.get("booking_url")
        })
    return {
        "catalog_type": "hotels",
        "total_results": len(filtered),
        "results": filtered
    }


# ==============================================================================
# 4. MCP TOOL DEFINITIONS & EXECUTION (Model Context Protocol for External AI)
# ==============================================================================
@router.get("/mcp/tools")
def get_mcp_tools():
    """
    Returns standard Model Context Protocol (MCP) tool schemas for external AI agents.
    """
    return {
        "tools": [
            {
                "name": "search_flight_catalog",
                "description": "Search available flights with pricing, classes, and schedules.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "origin": {"type": "string", "description": "3-letter IATA code, e.g. DEL, BLR"},
                        "destination": {"type": "string", "description": "3-letter IATA code, e.g. BOM, GOI"},
                        "departure_date": {"type": "string", "description": "YYYY-MM-DD"}
                    },
                    "required": ["origin", "destination"]
                }
            },
            {
                "name": "search_hotel_catalog",
                "description": "Search available hotel properties with amenities and prices.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name, e.g. Mumbai, Goa"},
                        "check_in_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "check_out_date": {"type": "string", "description": "YYYY-MM-DD"}
                    },
                    "required": ["city"]
                }
            },
            {
                "name": "create_ai_buyer_order",
                "description": "Create a gated Razorpay order to book a selected flight or hotel directly via AI.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "booking_type": {"type": "string", "enum": ["flight", "hotel"]},
                        "item_name": {"type": "string", "description": "Airline and flight number or hotel name"},
                        "amount_rupees": {"type": "number", "description": "Exact price in INR"},
                        "passenger_name": {"type": "string"},
                        "passenger_email": {"type": "string"}
                    },
                    "required": ["booking_type", "item_name", "amount_rupees", "passenger_name", "passenger_email"]
                }
            },
            {
                "name": "verify_ai_buyer_payment",
                "description": "Verify cryptographic payment signature and generate travel boarding pass or hotel ticket.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "payment_id": {"type": "string"},
                        "signature": {"type": "string"},
                        "session_id": {"type": "string"}
                    },
                    "required": ["order_id", "payment_id", "signature", "session_id"]
                }
            }
        ]
    }

@router.post("/mcp/execute")
async def execute_mcp_tool(req: MCPExecuteRequest):
    """
    Executes an MCP tool requested by an external AI buyer agent.
    """
    tool_name = req.tool_name
    params = req.parameters
    agent_id = req.agent_id or "external_mcp_agent"
    
    audit_service.log_event(
        event_type="MCP_TOOL_CALL",
        session_id=agent_id,
        actor="mcp_buyer_agent",
        payload={"tool_name": tool_name, "parameters": params}
    )

    if tool_name == "search_flight_catalog":
        return await get_flight_catalog(
            origin=params.get("origin", "DEL"),
            destination=params.get("destination", "BOM"),
            departure_date=params.get("departure_date")
        )
    elif tool_name == "search_hotel_catalog":
        return await get_hotel_catalog(
            city=params.get("city", "Mumbai"),
            check_in_date=params.get("check_in_date"),
            check_out_date=params.get("check_out_date")
        )
    elif tool_name == "create_ai_buyer_order":
        order = payment_service.create_order(
            amount_rupees=float(params.get("amount_rupees", 4500.0)),
            session_id=f"mcp_{uuid.uuid4().hex[:6]}",
            booking_type=params.get("booking_type", "flight"),
            item_name=params.get("item_name", "AI Agent Booking"),
            customer_email=params.get("passenger_email"),
            notes={"buyer": "autonomous_ai_agent"}
        )
        return {"status": "order_created", "order": order}
    elif tool_name == "verify_ai_buyer_payment":
        is_valid = payment_service.verify_signature(
            order_id=params.get("order_id", ""),
            payment_id=params.get("payment_id", ""),
            signature=params.get("signature", ""),
            session_id=params.get("session_id", "mcp_session"),
            actor="mcp_buyer_agent"
        )
        return {
            "status": "success" if is_valid else "failed",
            "verified": is_valid,
            "message": "Payment verified and booking confirmed by Sara AI" if is_valid else "Signature verification mismatch"
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")


# ==============================================================================
# 5. UNIFIED AUDIT TRAIL & ABANDONMENT RECOVERY
# ==============================================================================
@router.get("/audit")
def get_audit_trail(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, description="Max records to return")
):
    """
    Returns the unified, immutable audit trail for transactions, AI tool calls, and payments.
    """
    logs = audit_service.get_logs(session_id=session_id, event_type=event_type, status=status, limit=limit)
    return {
        "total_records": len(logs),
        "audit_logs": logs
    }

@router.post("/campaigns/check-abandoned")
async def trigger_abandonment_campaign():
    """
    Scans active sessions in payment steps and triggers Brevo re-engagement emails.
    """
    recovered = await campaign_service.check_and_recover_abandoned_sessions(sessions)
    return {
        "status": "completed",
        "recovered_count": len(recovered),
        "recovered_sessions": recovered
    }
