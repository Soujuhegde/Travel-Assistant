import re
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Literal, List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, BaseMessage
from langchain_groq import ChatGroq
from app.orchestrator.flight_flow import get_next_flight_step
from app.config import settings

class ExtractedInfo(BaseModel):
    intent: Literal["book_flight", "book_hotel", "plan_itinerary", "general_qa", "select_flight", "select_hotel", "provide_details", "payment_done", "provide_passenger_count", "confirm", "reject"] = "general_qa"
    origin: str | None = Field(description="The 3-letter IATA code of the origin city or airport (e.g. 'BLR', 'DEL', 'JFK', 'TYO'). ALWAYS convert full city or country names to their primary 3-letter IATA code.", default=None)
    destination: str | None = Field(description="The 3-letter IATA code of the destination city or airport (e.g. 'BLR', 'DEL', 'JFK', 'TYO'). ALWAYS convert full city or country names to their primary 3-letter IATA code.", default=None)
    departure_date: str | None = Field(description="The departure date in YYYY-MM-DD format. CRITICAL: ONLY extract this if the user EXPLICITLY mentions a date or time expression in their message (e.g. 'tomorrow', 'next Monday', '20th Sept'). If no date was explicitly stated by the user, leave as null. NEVER invent or assume a date.", default=None)
    return_date: str | None = Field(description="The return date in YYYY-MM-DD format. ONLY extract this if the user explicitly specifies a return date or relative return duration. Otherwise leave as null.", default=None)
    limit: int | None = Field(description="The number of flights the user wants to see, if they explicitly mention a number (e.g. 'show me 5 flights').", default=None)
    journey_type: Literal["One Way", "Round Trip"] | None = Field(description="The type of journey. ONLY populate this if the user explicitly mentions 'one way', 'round trip', 'return', 'single ticket', etc. Otherwise, set to null.", default=None)
    selected_class: str | None = None
    selected_airline: str | None = None
    selected_price: Optional[str] = Field(description="The price of the flight", default=None)
    booking_link: Optional[str] = Field(description="The booking URL link if provided in the message", default=None)
    passenger_name: Optional[str] = Field(description="Name of the passenger. ONLY extract this if it is explicitly provided in the latest user message. Do NOT carry over names from previous messages in the history.", default=None)
    passenger_email: str | None = Field(description="Email of the passenger. ONLY extract this if it is explicitly provided in the latest user message. Do NOT carry over emails from previous messages in the history.", default=None)
    passenger_contact: str | None = Field(description="Contact/phone of the passenger. ONLY extract this if it is explicitly provided in the latest user message. Do NOT carry over contacts from previous messages in the history.", default=None)
    passenger_passport: str | None = Field(description="Passport number of the passenger. ONLY extract this if it is explicitly provided in the latest user message. Do NOT carry over passports from previous messages in the history.", default=None)
    adults_count: int | None = None
    children_count: int | None = None
    infants_count: int | None = None
    hotel_city: str | None = None
    check_in_date: str | None = None
    check_out_date: str | None = None
    selected_option_index: int | None = Field(description="The index (0-based) of the flight or hotel option the user wants to select from the options presented, or null if they are not selecting an option.", default=None)

try:
    llm = ChatGroq(model=settings.LLM_MODEL, temperature=0)
except Exception as e:
    print(f"Warning: Failed to initialize ChatGroq with model {settings.LLM_MODEL}. {e}")
    llm = None

def is_question(text: str) -> bool:
    text_clean = text.strip().lower()
    if "?" in text_clean:
        return True
    question_words = ["what", "which", "who", "where", "why", "how", "is", "are", "can", "could", "would", "should", "do", "does", "did", "tell", "show", "describe", "explain", "suggest", "recommend", "weather"]
    words = re.findall(r"\b\w+\b", text_clean)
    if words and any(w in question_words for w in words):
        return True
    return False

def resolve_relative_checkout(check_in_str: str, user_text: str) -> str | None:
    if not check_in_str or not user_text:
        return None
    try:
        c_in_dt = datetime.strptime(check_in_str, "%Y-%m-%d")
        msg_clean = user_text.strip().lower()
        if msg_clean == "tomorrow":
            return (c_in_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        
        match = re.search(r"\b(\d+)\s*(?:day|night|night's|days|nights)", msg_clean)
        if match:
            days = int(match.group(1))
            return (c_in_dt + timedelta(days=days)).strftime("%Y-%m-%d")
            
        if "week" in msg_clean:
            return (c_in_dt + timedelta(days=7)).strftime("%Y-%m-%d")
    except Exception as e:
        print(f"Error resolving relative checkout date: {e}")
    return None

def extract_passenger_fields(raw_text: str, existing_pax: Dict[str, Any] | None = None) -> tuple[Dict[str, Any], List[str]]:
    """
    Robust deterministic extractor for passenger details in flight bookings.
    Handles:
      - Single-field entry (e.g. user enters only Name, or only Email, or only Phone, or only Passport)
      - Multi-field comma-separated entry (e.g. "Soujanya S P, soujanya@gmail.com, +91 8088091773, AR564543")
      - Key-value labeled entry (e.g. "Name: Kushal S, Email: kushal@gmail.com, Phone: 9876543210, Passport: M1234567")
      - Space-separated entry (e.g. "Kushal S kushal@gmail.com +919876543210 M1234567")
    NEVER overwrites already-populated valid fields with wrong types.
    """
    pax = dict(existing_pax or {})
    errors = []
    text = raw_text.strip()
    
    # 1. Email extraction
    email_match = re.search(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b", text)
    if email_match:
        pax["email"] = email_match.group(0).strip()
        
    # 2. Phone / Contact extraction
    phone_match = re.search(r"(\+?\d{1,4}[- ]?\d{10})\b", text)
    if not phone_match:
        phone_match = re.search(r"\b\d{10}\b", text)
    if phone_match:
        clean_phone = re.sub(r"[^\d+]", "", phone_match.group(0))
        if len(clean_phone) == 10:
            pax["contact"] = f"+91{clean_phone}"
        elif len(clean_phone) > 10:
            if not clean_phone.startswith("+"):
                clean_phone = f"+{clean_phone}"
            pax["contact"] = clean_phone

    # 3. Passport extraction
    # A. Explicit label: "passport: ABC12345" or "passport no: AR564543"
    passport_label_match = re.search(r"\b(?:passport(?:\s*(?:no|number|num))?[:\s\-]+)([A-Za-z0-9]{6,15})\b", text, re.I)
    if passport_label_match:
        pax["passport"] = passport_label_match.group(1).upper()
    else:
        # B. Token-based detection
        non_passport_words = {
            "PASSENGER", "PASSPORT", "CONTACT", "NUMBER", "EMAIL", "NAME", "ADULT", "CHILD",
            "INFANT", "PLEASE", "FLIGHT", "HOTEL", "INDIA", "ONE", "TWO", "THREE", "FOUR",
            "TODAY", "TOMORROW", "AIRLINE", "TICKET", "BOOKING", "ECONOMY", "BUSINESS",
            "GUEST", "FIRST", "SECOND", "THIRD", "PROCEED", "PAYMENT", "DONE", "SELECT"
        }
        passport_tokens = re.findall(r"\b[A-Za-z0-9]{6,15}\b", text)
        for tok in passport_tokens:
            tok_upper = tok.upper()
            if tok_upper in non_passport_words:
                continue
            if email_match and tok.lower() in email_match.group(0).lower():
                continue
            if phone_match and tok in re.sub(r"[^\d]", "", phone_match.group(0)):
                continue
            # Prefer tokens with both letters and numbers, or standalone alphanumeric codes
            has_letters = any(c.isalpha() for c in tok)
            has_digits = any(c.isdigit() for c in tok)
            if has_letters and has_digits:
                pax["passport"] = tok_upper
                break
            elif not pax.get("passport") and has_digits and len(tok) >= 6:
                pax["passport"] = tok_upper

    # 4. Name extraction
    # A. Explicit label: "name: Kushal S" or "name of the passenger: Yadunandan K D" or "passenger name: ..."
    name_label_match = re.search(r"\b(?:name\s*(?:of\s*(?:the\s*)?passenger)?[:\s\-]+|passenger\s*name[:\s\-]+|mr\.\s*|ms\.\s*|mrs\.\s*)([A-Za-z\s\.]+)", text, re.I)
    if name_label_match:
        cand_name = name_label_match.group(1).strip()
        cand_name = cand_name.split(",")[0].strip()
        if len(cand_name) >= 2 and not any(w in cand_name.lower() for w in ["@"]):
            pax["name"] = cand_name

    # B. Comma-separated structure: "Soujanya S P, soujanya@gmail.com, +91 8088091773, AR564543"
    elif "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        for p in parts:
            p_clean = re.sub(r"^(?:name\s*(?:of\s*(?:the\s*)?passenger)?[:\s\-]*|passenger\s*name[:\s\-]*|mr\.\s*|ms\.\s*|mrs\.\s*)", "", p, flags=re.I).strip()
            if email_match and p_clean.lower() in email_match.group(0).lower():
                continue
            if phone_match and p_clean in phone_match.group(0):
                continue
            if pax.get("passport") and p_clean.upper() == pax["passport"]:
                continue
            if len(p_clean) >= 2 and not re.search(r"\d{4,}", p_clean) and not any(p_clean.lower().startswith(w) for w in ["yes", "no", "skip", "book", "select", "payment"]):
                pax["name"] = p_clean
                break

    # C. Single-field / dedicated input when Name is missing and no other contact fields are present
    elif not pax.get("name") and not email_match and not phone_match:
        p_clean = re.sub(r"^(?:name\s*(?:of\s*(?:the\s*)?passenger)?[:\s\-]*|passenger\s*name[:\s\-]*|mr\.\s*|ms\.\s*|mrs\.\s*)", "", text, flags=re.I).strip()
        is_passport_cand = bool(pax.get("passport") and p_clean.upper() == pax["passport"]) or bool(re.match(r"^[A-Za-z]{1,3}\d{6,10}$", p_clean))
        if not is_passport_cand:
            if len(p_clean) >= 2 and not any(p_clean.lower().startswith(w) for w in ["yes", "no", "skip", "book", "select", "payment", "proceed"]):
                pax["name"] = p_clean

    # D. Multi-field space-separated extraction (remove email, phone, passport from text)
    if not pax.get("name"):
        rem_text = text
        if email_match:
            rem_text = rem_text.replace(email_match.group(0), "")
        if phone_match:
            rem_text = rem_text.replace(phone_match.group(0), "")
        if pax.get("passport"):
            rem_text = re.sub(re.escape(pax["passport"]), "", rem_text, flags=re.I)
        rem_text = re.sub(r"[,:\-_]+", " ", rem_text).strip()
        rem_text = re.sub(r"^(?:name\s*(?:of\s*(?:the\s*)?passenger)?[:\s\-]*|passenger\s*name[:\s\-]*|mr\.\s*|ms\.\s*|mrs\.\s*)", "", rem_text, flags=re.I).strip()
        if len(rem_text) >= 2 and not re.search(r"\d{4,}", rem_text):
            pax["name"] = rem_text

    # Validation checks on populated fields
    if pax.get("name") and len(pax["name"]) < 2:
        errors.append("Name must be at least 2 characters long.")
    if pax.get("email") and not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", pax["email"]):
        errors.append("Email address is invalid.")
    if pax.get("contact") and not re.match(r"^\+?\d{1,4}\d{10}$", pax["contact"]):
        errors.append("Contact number must include a country code followed strictly by 10 digits (e.g. +919876543210).")
    if pax.get("passport") and (len(pax["passport"]) < 6 or len(pax["passport"]) > 15 or not pax["passport"].isalnum()):
        errors.append("Passport number must be 6-15 alphanumeric characters.")

    return pax, errors

def rule_based_fallback(text: str, step: str | None, state: Dict[str, Any]) -> ExtractedInfo:
    text_clean = text.strip()
    text_lower = text_clean.lower()
    
    # Initialize ExtractedInfo with default general_qa intent
    res = ExtractedInfo(intent="general_qa")
    
    # 1. Simple Confirmation / Rejection
    is_confirm = text_lower in ["yes", "y", "yeah", "correct", "right", "ok", "okay", "sure", "proceed", "yes please", "confirm", "proceed with this option"] or "yes" in text_lower
    is_reject = text_lower in ["no", "n", "nope", "wrong", "wait", "decline", "cancel", "no thank you", "no thanks"] or "no" in text_lower
    
    # 2. City Mapping to IATA codes
    city_to_iata = {
        "mumbai": "BOM", "bombay": "BOM", "delhi": "DEL", "new delhi": "DEL",
        "bangalore": "BLR", "bengaluru": "BLR", "singapore": "SIN", "pune": "PNQ",
        "goa": "GOI", "hyderabad": "HYD", "chennai": "MAA", "madras": "MAA",
        "kolkata": "CCU", "calcutta": "CCU", "ahmedabad": "AMD", "kochi": "COK",
        "cochin": "COK", "jaipur": "JAI", "mangalore": "IXE", "mangaluru": "IXE",
        "london": "LHR", "paris": "CDG", "dubai": "DXB", "new york": "JFK",
        "los angeles": "LAX", "sydney": "SYD", "tokyo": "NRT"
    }

    # Find all cities in text in order of appearance
    found_cities = []
    # Check for multi-word cities first by sorting by length descending
    for city in sorted(city_to_iata.keys(), key=len, reverse=True):
        if city in text_lower:
            idx = text_lower.find(city)
            found_cities.append((idx, city))
            
    # Sort by index to get order of appearance
    found_cities.sort()
    found_cities = [c[1] for c in found_cities]
            
    if len(found_cities) >= 2:
        res.origin = city_to_iata[found_cities[0]]
        res.destination = city_to_iata[found_cities[1]]
        res.hotel_city = city_to_iata[found_cities[1]]
        res.intent = "book_flight"
    elif len(found_cities) == 1:
        res.destination = city_to_iata[found_cities[0]]
        res.hotel_city = city_to_iata[found_cities[0]]

    hotel_city_match = re.search(r"hotel\s+(?:in|at|near)\s+([a-zA-Z\s]+)", text_lower)
    if hotel_city_match:
        city_candidate = hotel_city_match.group(1).strip()
        if city_candidate in city_to_iata:
            res.hotel_city = city_to_iata[city_candidate]
        else:
            res.hotel_city = city_candidate.title()
        res.intent = "book_hotel"

    itin_city_match = re.search(r"(?:itinerary|itineary|plan)\s+(?:for|in|at)\s+([a-zA-Z\s]+)", text_lower)
    if itin_city_match:
        city_candidate = itin_city_match.group(1).strip()
        if city_candidate in city_to_iata:
            res.hotel_city = city_to_iata[city_candidate]
        else:
            res.hotel_city = city_candidate.title()
        res.intent = "plan_itinerary"

    # 3. Simple Journey Type
    if "one way" in text_lower or "oneway" in text_lower or "single journey" in text_lower or "single ticket" in text_lower:
        res.journey_type = "One Way"
        res.intent = "book_flight"
    elif "round trip" in text_lower or "roundtrip" in text_lower or "return" in text_lower or "two way" in text_lower:
        res.journey_type = "Round Trip"
        res.intent = "book_flight"
        
    # 4. Simple Intents based on keywords
    if "flight" in text_lower or "fly" in text_lower or "ticket" in text_lower:
        res.intent = "book_flight"
    elif "hotel" in text_lower or "stay" in text_lower or "hostel" in text_lower or "resort" in text_lower or "room" in text_lower:
        res.intent = "book_hotel"
    elif "itinerary" in text_lower or "itineary" in text_lower or "plan" in text_lower:
        res.intent = "plan_itinerary"
        
    # 5. Confirmation / Rejection overrides
    if is_confirm:
        res.intent = "confirm"
    elif is_reject:
        res.intent = "reject"
        
    # 6. Date parsing (very important for flight departure, hotel check-in/out)
    parsed_date = None
    
    # Pattern A: YYYY-MM-DD
    match_ymd = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text_clean)
    if match_ymd:
        parsed_date = match_ymd.group(0)
    else:
        # Pattern B: DD-MM-YYYY or DD/MM/YYYY or DD-MM-YY
        match_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", text_clean)
        if match_dmy:
            d, m, y = match_dmy.groups()
            if len(y) == 2:
                y = "20" + y
            try:
                parsed_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            except ValueError:
                pass
        else:
            # Pattern C: Month Day (e.g. August 14 or August 14 2026 or 14 August)
            months_map = {
                "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
                "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
                "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
                "nov": 11, "november": 11, "dec": 12, "december": 12
            }
            matched_month_day = False
            for m_name, m_val in months_map.items():
                pattern1 = rf"\b{m_name}\b\s*(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{{4}}))?"
                pattern2 = rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*\b{m_name}\b(?:\s*,?\s*(\d{{4}}))?"
                
                match1 = re.search(pattern1, text_lower)
                match2 = re.search(pattern2, text_lower)
                
                if match1:
                    d = int(match1.group(1))
                    y = int(match1.group(2)) if match1.group(2) else datetime.now().year
                    parsed_date = f"{y:04d}-{m_val:02d}-{d:02d}"
                    matched_month_day = True
                    break
                elif match2:
                    d = int(match2.group(1))
                    y = int(match2.group(2)) if match2.group(2) else datetime.now().year
                    parsed_date = f"{y:04d}-{m_val:02d}-{d:02d}"
                    matched_month_day = True
                    break
            
            # Pattern D: relative words
            if not matched_month_day:
                today = datetime.now()
                if "today" in text_lower:
                    parsed_date = today.strftime("%Y-%m-%d")
                elif "tomorrow" in text_lower:
                    parsed_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                elif "next monday" in text_lower:
                    days_ahead = 0 - today.weekday() + 7
                    parsed_date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                
    if parsed_date:
        if step in ["awaiting_departure_date", "invalid_departure_date"]:
            res.departure_date = parsed_date
            res.intent = "book_flight"
        elif step == "hotel_awaiting_check_in":
            res.check_in_date = parsed_date
            res.intent = "book_hotel"
        elif step == "hotel_awaiting_check_out":
            res.check_out_date = parsed_date
            res.intent = "book_hotel"
        else:
            res.departure_date = parsed_date
            res.check_in_date = parsed_date
            
    # 7. Passenger Count parsing
    if step == "awaiting_passenger_count" or "adult" in text_lower or "child" in text_lower or "infant" in text_lower or "passenger" in text_lower:
        adults = 1
        children = 0
        infants = 0
        
        adult_match = re.search(r"(\d+)\s*(?:adult|pax)", text_lower)
        child_match = re.search(r"(\d+)\s*(?:child|kid|children)", text_lower)
        infant_match = re.search(r"(\d+)\s*infant", text_lower)
        
        if adult_match: adults = int(adult_match.group(1))
        if child_match: children = int(child_match.group(1))
        if infant_match: infants = int(infant_match.group(1))
        
        if not adult_match and not child_match and not infant_match:
            single_num_match = re.match(r"^\s*(\d+)\s*$", text_lower)
            if single_num_match:
                adults = int(single_num_match.group(1))
                
        res.adults_count = adults
        res.children_count = children
        res.infants_count = infants
        res.intent = "provide_passenger_count"
        
    # 8. Passenger details parsing
    if step == "awaiting_passenger_details":
        res.intent = "provide_details"
        pax_extracted, _ = extract_passenger_fields(text_clean)
        if pax_extracted.get("name"):
            res.passenger_name = pax_extracted["name"]
        if pax_extracted.get("email"):
            res.passenger_email = pax_extracted["email"]
        if pax_extracted.get("contact"):
            res.passenger_contact = pax_extracted["contact"]
        if pax_extracted.get("passport"):
            res.passenger_passport = pax_extracted["passport"]
                        
    # 9. Option select by index
    if step in ["flight_selecting", "hotel_selecting"]:
        index_val = None
        if "first" in text_lower or "1st" in text_lower:
            index_val = 0
        elif "second" in text_lower or "2nd" in text_lower:
            index_val = 1
        elif "third" in text_lower or "3rd" in text_lower:
            index_val = 2
        else:
            # Match if the message is strictly a single number, e.g. "1" or "2"
            num_match_strict = re.match(r"^\s*#?(\d{1,2})\s*$", text_lower)
            # Or matches "option 1", "flight 2", etc.
            num_match_context = re.search(r"\b(?:option|no|number|select|choose|flight|hotel|opt)\s*#?(\d{1,2})\b", text_lower)
            
            if num_match_strict:
                val = int(num_match_strict.group(1))
                if 1 <= val <= 10:
                    index_val = val - 1
            elif num_match_context:
                val = int(num_match_context.group(1))
                if 1 <= val <= 10:
                    index_val = val - 1
        if index_val is not None:
            res.selected_option_index = index_val
            res.intent = "select_flight" if step == "flight_selecting" else "select_hotel"
            
    # 10. Payment
    if "payment done" in text_lower or "paid" in text_lower or "payment completed" in text_lower:
        res.intent = "payment_done"

    return res

def parse_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    if not llm:
        print("Warning: LLM is not configured. Proceeding with rule-based fallback.")
    
    step = state.get("current_step")
    from langchain_core.messages import HumanMessage
    if step in ["awaiting_passenger_details", "hotel_awaiting_guest_name", "hotel_awaiting_guest_email", "hotel_awaiting_guest_phone"]:
        recent_messages = state["messages"][-2:]
    else:
        recent_messages = state["messages"][-5:]
    flight_params = state.get("flight_params") or {}
    passenger_details = state.get("passenger_details") or {}
    selected_flight = state.get("selected_flight") or {}
    
    # FIX H-001: Snapshot original flight destination BEFORE LLM extraction modifies it
    _original_flight_destination = flight_params.get("destination")
    _original_flight_has_airline = bool((state.get("selected_flight") or {}).get("airline_name"))
    
    hotel_params = state.get("hotel_params") or {}
    hotel_result = state.get("hotel_result") or {}
    selected_hotel = state.get("selected_hotel") or {}
    
    # FIX I-01: Snapshot original dates BEFORE LLM extraction
    _original_check_in_date = hotel_params.get("check_in_date")
    _original_departure_date = flight_params.get("departure_date")
    
    passenger_count = state.get("passenger_count") or {}
    passengers_details = state.get("passengers_details") or []
    current_passenger_index = state.get("current_passenger_index") or 0
    pending_clarification = state.get("pending_clarification")
    
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "content"):
        user_msg_text = last_msg.content.strip()
    elif isinstance(last_msg, dict):
        user_msg_text = str(last_msg.get("content", "")).strip()
    else:
        user_msg_text = str(last_msg).strip()
    msg_text_lower = user_msg_text.lower()
    
    print("\n=== DEBUG parse_intent ===")
    safe_user_msg = user_msg_text.encode('ascii', errors='backslashreplace').decode('ascii')
    print(f"User Message: {safe_user_msg}")
    print(f"Current Step: {state.get('current_step')}")
    print(f"flight_params: {flight_params}")
    print(f"selected_flight: {selected_flight}")
    print("===========================\n")
    
    today = datetime.now()
    today_date = today.strftime("%A, %Y-%m-%d")
    tomorrow_date = (today + timedelta(days=1)).strftime("%A, %Y-%m-%d")
    
    upcoming_days = []
    for i in range(7):
        day = today + timedelta(days=i)
        upcoming_days.append(f"{day.strftime('%A')} ({day.strftime('%Y-%m-%d')})")
    upcoming_str = ", ".join(upcoming_days)
    
    options_to_show = state.get("options_to_show") or []
    options_str = ""
    if options_to_show:
        options_str = "\n    Suggested Options currently visible to the user:\n"
        for idx, opt in enumerate(options_to_show):
            if opt.get("type") == "flight" or "pricing" in opt:
                pricing_str = ", ".join(f"{p['class']}: {p['price']}" for p in opt.get("pricing", []))
                options_str += f"    - [Option {idx}] Airline: {opt.get('airline_name')}, Flight No: {opt.get('flight_numbers')}, Dep: {opt.get('departure_time')}, Arr: {opt.get('arrival_time')}, Base Price: {opt.get('price')} ({pricing_str})\n"
            else:
                options_str += f"    - [Option {idx}] Hotel: {opt.get('name')}, Rating: {opt.get('star_rating')}, Price per night: {opt.get('price_per_night')}, Amenities: {', '.join(opt.get('amenities', []))}\n"

    prompt = f"""You are a helpful travel assistant. Analyze the user's latest message and extract their intent and any travel details.
    
    Current known flight params: {flight_params}
    Current known hotel params: {hotel_params}
    Current known passenger count: {passenger_count}
    Current passenger index being filled: {current_passenger_index + 1}
    Current Date: {today_date}
    Tomorrow's Date: {tomorrow_date}
    Upcoming 7 days reference: {upcoming_str}
    {options_str}
    
    Intents:
    - book_flight: user wants to search for flights.
    - book_hotel: user wants to search for hotels.
    - select_flight: user selects a specific flight and class. You can also match conversational selection (e.g. 'the expensive one', 'indigo', 'the second option') if flights are visible.
    - select_hotel: user selects a specific hotel. You can also match conversational selection (e.g. 'the cheapest one', 'Royal Hometel', 'the first hotel') if hotels are visible.
    - provide_passenger_count: user tells you how many adults/children/infants. Extract this into adults_count, children_count, infants_count.
    - provide_details: user provides their passenger info (name, email, contact, passport).
    - payment_done: user says payment is done.
    - confirm: user explicitly says yes/correct.
    - reject: user explicitly says no/wrong.
    - general_qa: anything else.
    
    Rules for Option Selection:
    - ONLY classify as 'select_flight' or 'select_hotel' if the user explicitly wants to book, select, choose, or proceed with a specific option (e.g. 'choose the expensive one', 'book the cheapest flight', 'select option 1', 'let's go with Indigo').
    - If the user is just asking a question about the options to compare them or seek information (e.g., 'which is the expensive one in this?', 'which is the cheapest?', 'what is the Indigo flight's duration?', 'which is the highest rated hotel?'), classify the intent as 'general_qa' (not select_flight or select_hotel), so we can answer their question without proceeding to selection.
    - If the user is selecting an option, populate 'selected_option_index' with the 0-based index of the selected option, and if they specify a class like 'economy' or 'business', extract it into 'selected_class'.
 
    Rules for Date Extraction:
    - CRITICAL: ONLY extract departure_date, check_in_date, and check_out_date if the user EXPLICITLY mentions a date, day of week, or relative time phrase in their message (e.g. 'tomorrow', 'next Friday', '20th Sept'). If the user has NOT provided a date (e.g., they only said 'Bengaluru to Goa' or 'One Way'), set departure_date to null. NEVER assume, guess, or invent a departure date.
    - ALWAYS convert explicit departure_date, check_in_date, and check_out_date strictly to YYYY-MM-DD format.
    - If check_out_date is described relative to check_in_date (e.g. "for 2 nights", "in 2 days", "tomorrow" relative to check_in), calculate check_out_date by adding that duration to check_in_date.
    - If the user says "next [day]" (e.g., "next monday"), use the exact date for that day from the "Upcoming 7 days reference". Do NOT add an extra week.
    - Convert all origin and destination cities/countries/airports strictly to their most prominent 3-letter IATA airport code.
    - If a country is provided (e.g., 'India', 'France'), output its major international airport code (e.g., 'DEL' for India, 'CDG' for France).
    - If a city has multiple airports, output the primary airport code (e.g., 'LHR' for London, 'JFK' for New York) or the city code.
    - Be extremely careful with spelling and similar-sounding names (e.g., 'Mangalore' is 'IXE' and must not be confused with 'Bangalore' 'BLR'; 'Goa' is 'GOI' and not 'Genoa'; 'Manali' is 'KUU' (Kullu) and MUST NOT be confused with 'Belagavi' 'IXG').
    - Use your comprehensive knowledge to map ANY global city or country correctly.
    
    Rules for Passenger Details Extraction:
    - ONLY extract passenger_name, passenger_email, passenger_contact, and passenger_passport if they are explicitly written in the latest user message. 
    - DO NOT extract or repeat details from previous messages in the history. If a detail is missing in the latest message, leave it as null."""
    
    messages = [SystemMessage(content=prompt)] + recent_messages
    
    try:
        if not llm:
            raise ValueError("LLM is not configured")
        structured_llm = llm.with_structured_output(ExtractedInfo)
        result = structured_llm.invoke(messages)
    except Exception as e:
        safe_err = str(e).encode('ascii', 'ignore').decode('ascii')
        print(f"Structured LLM failed: {safe_err}. Using rule-based fallback parser.")
        result = rule_based_fallback(user_msg_text, step, state)
    
    step = state.get("current_step", "start")
    
    is_confirmation = result.intent == "confirm" or msg_text_lower in ["yes", "y", "yeah", "correct", "right", "ok", "okay", "sure", "proceed"] or "yes" in msg_text_lower
    is_rejection = result.intent == "reject" or msg_text_lower in ["no", "n", "nope", "wrong", "wait"] or "no" in msg_text_lower
    is_show_others = is_rejection or "select another" in msg_text_lower or "other options" in msg_text_lower or "show others" in msg_text_lower or "see all options" in msg_text_lower or "see all" in msg_text_lower

    # Initialize sub-flow parameters from state to avoid unbound variables
    is_gathering_details = state.get("current_step") in [
        "awaiting_origin_dest", "awaiting_departure_date", "invalid_departure_date", "awaiting_journey_type",
        "awaiting_passenger_count", "awaiting_passenger_details", "verify_passenger_count",
        "awaiting_payment", "hotel_confirm_city", "hotel_confirm_dates"
    ] or (state.get("current_step") is not None and state.get("current_step").startswith("hotel_awaiting_"))

    # FIX H-001: Only set flight origin/destination when intent is NOT hotel booking
    # The LLM sometimes extracts destination IATA codes from hotel messages (e.g., "hotel in Goa" → GOI)
    _is_hotel_intent = result.intent in ("book_hotel",) or "hotel" in msg_text_lower
    if result.origin and (not flight_params.get("origin") or step == "awaiting_origin_dest") and not _is_hotel_intent: 
        flight_params["origin"] = result.origin
    if result.destination and (not flight_params.get("destination") or step == "awaiting_origin_dest") and not _is_hotel_intent: 
        flight_params["destination"] = result.destination
    if result.limit: 
        flight_params["limit"] = result.limit
    
    if result.hotel_city and (not hotel_params.get("city") or step == "hotel_awaiting_city" or step.startswith("hotel_")): 
        hotel_params["city"] = result.hotel_city
        if step.startswith("hotel_") and step not in ["hotel_awaiting_city", "hotel_awaiting_check_in", "hotel_awaiting_check_out"]:
            step = "hotel_ready_to_search"
            
    if result.check_in_date and (not hotel_params.get("check_in_date") or step == "hotel_awaiting_check_in" or step.startswith("hotel_")):
        try:
            datetime.strptime(result.check_in_date, "%Y-%m-%d")
            hotel_params["check_in_date"] = result.check_in_date
            if step.startswith("hotel_") and step not in ["hotel_awaiting_check_in", "hotel_awaiting_check_out"]:
                step = "hotel_ready_to_search"
        except ValueError:
            pass

    # Programmatically resolve check_out_date if missing or relative
    c_out_val = result.check_out_date
    c_in_str = hotel_params.get("check_in_date") or result.check_in_date
    if c_in_str and not c_out_val:
        c_out_val = resolve_relative_checkout(c_in_str, user_msg_text)
        
    if c_out_val and (not hotel_params.get("check_out_date") or step == "hotel_awaiting_check_out" or step.startswith("hotel_")):
        try:
            dt_out = datetime.strptime(c_out_val, "%Y-%m-%d")
            c_in = hotel_params.get("check_in_date") or result.check_in_date
            valid = True
            if c_in:
                dt_in = datetime.strptime(c_in, "%Y-%m-%d")
                if dt_out <= dt_in:
                    valid = False
            if valid:
                hotel_params["check_out_date"] = c_out_val
                if step.startswith("hotel_") and step not in ["hotel_awaiting_check_in", "hotel_awaiting_check_out"]:
                    step = "hotel_ready_to_search"
        except ValueError:
            pass
    
    # Only accept departure_date when we are at a flight detail-gathering step or at the start.
    _date_accepting_steps = {"awaiting_departure_date", "invalid_departure_date", "awaiting_origin_dest", "start", "general_qa", None}
    invalid_date = False
    if result.departure_date and step in _date_accepting_steps:
        try:
            date_obj = datetime.strptime(result.departure_date, "%Y-%m-%d").date()
            if date_obj < datetime.now().date():
                flight_params["departure_date"] = None
                invalid_date = True
            else:
                flight_params["departure_date"] = result.departure_date
        except ValueError:
            flight_params["departure_date"] = result.departure_date

    # Accept journey_type when inside the flight flow or from the initial message
    _journey_accepting_steps = {"awaiting_origin_dest", "awaiting_departure_date", "invalid_departure_date", "awaiting_journey_type", "awaiting_return_date", "invalid_return_date", "start", "general_qa", None}
    if result.journey_type and step in _journey_accepting_steps:
        flight_params["journey_type"] = result.journey_type

    # Accept return_date for Round Trip
    _return_accepting_steps = {"awaiting_return_date", "invalid_return_date", "awaiting_journey_type", "awaiting_departure_date", "start", "general_qa", None}
    invalid_return_date = False
    
    # Check relative return date phrases (e.g. "in 3 days", "in 1 week", "tomorrow")
    if step in ["awaiting_return_date", "invalid_return_date"] or (flight_params.get("journey_type") == "Round Trip" and not flight_params.get("return_date")):
        dep_date_str = flight_params.get("departure_date") or _original_departure_date or datetime.now().strftime("%Y-%m-%d")
        try:
            dep_dt = datetime.strptime(dep_date_str, "%Y-%m-%d").date()
        except:
            dep_dt = datetime.now().date()
            
        rel_days = re.search(r"\b(?:in\s+)?(\d+)\s*(?:day|days|night|nights)\b", msg_text_lower)
        rel_weeks = re.search(r"\b(?:in\s+)?(\d+)\s*(?:week|weeks)\b", msg_text_lower)
        if rel_days:
            result.return_date = (dep_dt + timedelta(days=int(rel_days.group(1)))).strftime("%Y-%m-%d")
        elif rel_weeks:
            result.return_date = (dep_dt + timedelta(days=int(rel_weeks.group(1)) * 7)).strftime("%Y-%m-%d")
        elif "tomorrow" in msg_text_lower and step in ["awaiting_return_date", "invalid_return_date"]:
            result.return_date = (dep_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        elif not result.return_date and result.departure_date and step in ["awaiting_return_date", "invalid_return_date"]:
            result.return_date = result.departure_date

    if result.return_date and (step in _return_accepting_steps or flight_params.get("journey_type") == "Round Trip"):
        try:
            r_obj = datetime.strptime(result.return_date, "%Y-%m-%d").date()
            dep_str = flight_params.get("departure_date") or _original_departure_date or datetime.now().strftime("%Y-%m-%d")
            dep_obj = datetime.strptime(dep_str, "%Y-%m-%d").date()
            if r_obj < dep_obj:
                flight_params["return_date"] = None
                invalid_return_date = True
            else:
                flight_params["return_date"] = result.return_date
        except ValueError:
            flight_params["return_date"] = result.return_date
    
    step = state.get("current_step", "start")
    incoming_step = step
    
    # Override for hotel suggestions requests
    suggest_keywords = ["suggest", "recommend", "places to stay", "where to stay", "find me a stay", "hostel", "hostels"]
    is_suggest_query = any(k in msg_text_lower for k in suggest_keywords)
    target_city = result.hotel_city or result.destination or (flight_params.get("destination") if is_suggest_query else None)
    
    is_in_hotel_flow = step is not None and (step.startswith("hotel_") or step in ["hotel_summary", "hotel_awaiting_payment", "hotel_booking_confirmed"])
    
    if is_suggest_query and target_city and not is_gathering_details and not is_in_hotel_flow and not any(w in msg_text_lower for w in ["flight", "plane", "ticket"]):
        result.intent = "book_hotel"
        hotel_params["city"] = target_city
        today = datetime.now()
        hotel_params["check_in_date"] = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        hotel_params["check_out_date"] = (today + timedelta(days=8)).strftime("%Y-%m-%d")
        hotel_params["rooms"] = "1 Room"
        hotel_params["guests"] = "1 Adult"
        step = "hotel_ready_to_search"
    
    if any(w in msg_text_lower for w in ["edit date", "edit dates", "change date", "change dates", "modify date", "modify dates", "✏️ edit dates"]):
        if is_in_hotel_flow or (step and step.startswith("hotel_")):
            result.intent = "book_hotel"
            hotel_params["check_in_date"] = None
            hotel_params["check_out_date"] = None
            step = "hotel_awaiting_check_in"
        elif step in ["awaiting_origin_dest", "awaiting_departure_date", "invalid_departure_date", "awaiting_journey_type", "ready_to_search", "flight_selecting", "flight_summary", "awaiting_payment", "flight_awaiting_payment"]:
            result.intent = "book_flight"
            flight_params["departure_date"] = None
            step = "awaiting_departure_date"

    _itinerary_steps = {"itinerary_awaiting_city", "itinerary_awaiting_start_date", "itinerary_awaiting_days", "plan_itinerary"}
    if any(w in msg_text_lower for w in ["plan an itinerary", "plan itinerary", "itinerary plan", "itinerary", "itineary", "plan an itineary", "plan itineary", "itineary plan"]) and step not in _itinerary_steps:
        result.intent = "plan_itinerary"
        pending_clarification = None
        days_match = re.search(r"\b(\d+)\s*day", msg_text_lower)
        if days_match:
            hotel_params["itinerary_days"] = int(days_match.group(1))

        existing_city = hotel_params.get("city") or flight_params.get("destination")
        # FIX I-01: Use pre-extraction snapshots so LLM-extracted dates from this message don't count
        existing_date = _original_check_in_date or _original_departure_date

        if not existing_city:
            step = "itinerary_awaiting_city"
        elif not existing_date:
            # Always ask for start date if no prior booking date exists
            step = "itinerary_awaiting_start_date"
        elif not hotel_params.get("itinerary_days"):
            step = "itinerary_awaiting_days"
        else:
            step = "plan_itinerary"
    elif user_msg_text.startswith("I would like to select hotel "):
        result.intent = "select_hotel"
        try:
            parts = user_msg_text.replace("I would like to select hotel ", "").split(" for ")
            hotel_name = parts[0]
            price = parts[1]
            selected_hotel["name"] = hotel_name
            selected_hotel["price"] = price
            
            hr = state.get("hotel_result") or {}
            for h in hr.get("results", []):
                if hotel_name in h.get("name", ""):
                    selected_hotel["booking_link"] = h.get("booking_url") or "https://booking.com"
                    selected_hotel["star_rating"] = h.get("star_rating", "3-star")
                    selected_hotel["amenities"] = h.get("amenities", [])
                    break
        except Exception as e:
            print(f"Error parsing manual hotel selection: {e}")
            
    elif user_msg_text.startswith("I would like to select "):
        result.intent = "select_flight"
        try:
            parts = user_msg_text.replace("I would like to select ", "").split(" class on ")
            cls = parts[0]
            rest = parts[1].split(" for ")
            airline_flight = rest[0]
            price = rest[1]
            selected_flight["class"] = cls
            selected_flight["airline"] = airline_flight
            selected_flight["price"] = price
            
            fr = state.get("flight_result") or {}
            for f in fr.get("results", []):
                if airline_flight in f.get("airline_name", "") or airline_flight in f.get("flight_numbers", "") or f.get("flight_numbers") in airline_flight:
                    selected_flight["booking_link"] = f.get("booking_link") or "https://flights.google.com"
                    selected_flight["flight_numbers"] = f.get("flight_numbers", "N/A")
                    selected_flight["departure_time"] = f.get("departure_time", "00:00")
                    selected_flight["arrival_time"] = f.get("arrival_time", "00:00")
                    selected_flight["origin_airport"] = f.get("origin_airport", "Origin")
                    selected_flight["destination_airport"] = f.get("destination_airport", "Destination")
                    selected_flight["airline_logo"] = f.get("airline_logo", "")
                    selected_flight["airline_name"] = f.get("airline_name", airline_flight)
                    break
        except Exception as e:
            print(f"Error parsing manual flight selection: {e}")
            
    if len(options_to_show) == 1 and step in ["flight_selecting", "hotel_selecting"]:
        if is_confirmation or user_msg_text.lower() in ["proceed", "proceed with this option", "proceed with this one", "book this", "yes"]:
            result.intent = "select_flight" if step == "flight_selecting" else "select_hotel"
            result.selected_option_index = 0
        elif is_show_others:
            if step == "flight_selecting":
                fr = state.get("flight_result") or {}
                original_results = fr.get("results", [])
                for r in original_results:
                    r["type"] = "flight"
                options_to_show = original_results
            else:
                hr = state.get("hotel_result") or {}
                original_results = hr.get("results", [])
                for r in original_results:
                    r["type"] = "hotel"
                options_to_show = original_results[:3]

    elif result.intent in ["select_flight", "select_hotel"] and result.selected_option_index is not None and 0 <= result.selected_option_index < len(options_to_show):
        opt = options_to_show[result.selected_option_index]
        if opt.get("type") == "flight" or "pricing" in opt:
            result.intent = "select_flight"
            pricing = opt.get("pricing", [])
            selected_cls = "Economy"
            selected_pr = opt.get("price")
            for p in pricing:
                if result.selected_class and result.selected_class.lower() in p["class"].lower():
                    selected_cls = p["class"]
                    selected_pr = p["price"]
                    break
            if not selected_pr and pricing:
                selected_cls = pricing[0]["class"]
                selected_pr = pricing[0]["price"]
            
            selected_flight["class"] = selected_cls
            selected_flight["airline"] = opt.get("airline_name")
            selected_flight["price"] = selected_pr
            selected_flight["booking_link"] = opt.get("booking_link") or "https://flights.google.com"
            selected_flight["flight_numbers"] = opt.get("flight_numbers", "N/A")
            selected_flight["departure_time"] = opt.get("departure_time", "00:00")
            selected_flight["arrival_time"] = opt.get("arrival_time", "00:00")
            selected_flight["origin_airport"] = opt.get("origin_airport", "Origin")
            selected_flight["destination_airport"] = opt.get("destination_airport", "Destination")
            selected_flight["airline_logo"] = opt.get("airline_logo", "")
            selected_flight["airline_name"] = opt.get("airline_name")
        else:
            result.intent = "select_hotel"
            selected_hotel["name"] = opt.get("name")
            selected_hotel["price"] = opt.get("price_per_night")
            selected_hotel["booking_link"] = opt.get("booking_url") or "https://booking.com"
            selected_hotel["star_rating"] = opt.get("star_rating", "3-star")
            selected_hotel["amenities"] = opt.get("amenities", [])
            
    if step == "awaiting_passenger_count" and not user_msg_text.startswith("I would like to select "):
        if result.intent in ["general_qa", "select_flight", "select_hotel"] and is_question(user_msg_text):
            pass
        else:
            result.intent = "provide_passenger_count"
            
    is_confirmation = result.intent == "confirm" or msg_text_lower in ["yes", "y", "yeah", "correct", "right", "ok", "okay", "sure", "proceed"] or "yes" in msg_text_lower
    is_rejection = result.intent == "reject" or msg_text_lower in ["no", "n", "nope", "wrong", "wait"] or "no" in msg_text_lower

    if step == "verify_passenger_count":
        if is_confirmation:
            step = "awaiting_passenger_details"
            result.intent = "confirm"
        elif is_rejection:
            step = "awaiting_passenger_count"
            result.intent = "reject"
        elif result.intent == "provide_details":
            step = "awaiting_passenger_details"
        elif result.intent == "select_flight" and not user_msg_text.startswith("I would like to select "):
            step = "verify_passenger_count"
        elif result.intent == "provide_passenger_count" or result.adults_count or result.children_count or result.infants_count:
            adults = result.adults_count or 0
            children = result.children_count or 0
            infants = result.infants_count or 0
            if adults == 0 and children == 0 and infants == 0:
                adults = 1
            total = adults + children + infants
            passenger_count = {"adults": adults, "children": children, "infants": infants, "total": total}
            passengers_details = []
            current_passenger_index = 0
            step = "verify_passenger_count"
            result.intent = "provide_passenger_count"

    if step in ["plan_itinerary", "itinerary_awaiting_days", "itinerary_awaiting_city", "itinerary_awaiting_start_date"]:
        if step == "itinerary_awaiting_city" and incoming_step == "itinerary_awaiting_city":
            city_val = user_msg_text.strip()
            if len(city_val) >= 2:
                hotel_params["city"] = city_val
                pending_clarification = None
                existing_date = hotel_params.get("check_in_date") or flight_params.get("departure_date")
                # FIX I-01: Always ask for start date if unknown
                if not existing_date:
                    step = "itinerary_awaiting_start_date"
                elif not hotel_params.get("itinerary_days"):
                    step = "itinerary_awaiting_days"
                else:
                    step = "plan_itinerary"
            else:
                pending_clarification = "⚠️ Validation Error:\n- Please enter a valid city name."

        elif step == "itinerary_awaiting_start_date" and incoming_step == "itinerary_awaiting_start_date":
            date_val = result.departure_date or result.check_in_date or user_msg_text.strip()
            try:
                date_obj = datetime.strptime(date_val, "%Y-%m-%d").date()
                if date_obj < datetime.now().date():
                    pending_clarification = "⚠️ Validation Error:\n- Please enter a present or future date."
                else:
                    hotel_params["check_in_date"] = date_val
                    pending_clarification = None
                    if not hotel_params.get("itinerary_days"):
                        step = "itinerary_awaiting_days"
                    else:
                        step = "plan_itinerary"
            except ValueError:
                pending_clarification = "⚠️ Validation Error:\n- Please enter a valid date (e.g. 2025-08-15 or 'next Monday')."

        elif step == "itinerary_awaiting_days" and incoming_step == "itinerary_awaiting_days":
            days_match = re.search(r"\b(\d+)\b", user_msg_text)
            if days_match:
                hotel_params["itinerary_days"] = int(days_match.group(1))
                step = "plan_itinerary"
                pending_clarification = None
            else:
                pending_clarification = "⚠️ Validation Error:\n- Please enter a valid number of days (e.g. 3 or '5 days')."
        else:
            pass
    elif step in ["awaiting_origin_dest", "awaiting_departure_date", "invalid_departure_date", "awaiting_journey_type", "awaiting_return_date", "invalid_return_date"]:
        step = get_next_flight_step(flight_params, invalid_date, invalid_return_date)
    elif step != "verify_passenger_count" and result.intent == "select_flight":
        is_button_select = user_msg_text.startswith("I would like to select ")
        if result.selected_airline and not is_button_select: selected_flight["airline"] = result.selected_airline
        if result.selected_class and not is_button_select: selected_flight["class"] = result.selected_class
        if result.selected_price and not is_button_select: selected_flight["price"] = result.selected_price
        if hasattr(result, "booking_link") and result.booking_link and not is_button_select: selected_flight["booking_link"] = result.booking_link

        step = "awaiting_passenger_count"
        
    elif step != "verify_passenger_count" and result.intent == "select_hotel" and (incoming_step in ["hotel_selecting", "hotel_confirm_city", "hotel_confirm_dates"] or (incoming_step and incoming_step.startswith("hotel_"))) and not step.startswith("hotel_awaiting_") and step != "hotel_summary":
        old_ticket = state.get("hotel_ticket")
        if old_ticket and old_ticket.get("hotel_name"):
            # Save the new hotel choice temporarily
            state["temp_new_hotel"] = selected_hotel.copy()
            # Restore the selected_hotel back to the old one for now
            selected_hotel = state.get("selected_hotel", {}).copy()
            step = "hotel_confirm_change"
        else:
            is_button_select_hotel = user_msg_text.startswith("I would like to select hotel ")
            pax = passengers_details[0] if passengers_details else (passenger_details or {})
            if pax.get("name") and not selected_hotel.get("guest_name"):
                selected_hotel["guest_name"] = pax.get("name")
            if pax.get("email") and not selected_hotel.get("guest_email"):
                selected_hotel["guest_email"] = pax.get("email")
            if pax.get("contact") and not selected_hotel.get("guest_phone"):
                selected_hotel["guest_phone"] = pax.get("contact")

            if not selected_hotel.get("guest_name"): step = "hotel_awaiting_guest_name"
            elif not selected_hotel.get("guest_email"): step = "hotel_awaiting_guest_email"
            elif not selected_hotel.get("guest_phone"): step = "hotel_awaiting_guest_phone"
            elif "special_requests" not in selected_hotel: step = "hotel_awaiting_special_requests"
            elif "arrival_time" not in selected_hotel: step = "hotel_awaiting_arrival_time"
            else: step = "hotel_summary"
            
    elif (
        # FIX H-001/H-003: Never fire flight passenger count logic when inside any hotel step
        not incoming_step.startswith("hotel_") if incoming_step else True
    ) and (
        (result.intent == "provide_passenger_count" and step in ["awaiting_passenger_count", "start", "verify_passenger_count"])
        or (step == "awaiting_passenger_count" and result.intent != "general_qa")
    ):
        adults = result.adults_count or 1
        children = result.children_count or 0
        infants = result.infants_count or 0
        total = adults + children + infants
        if total == 0:
            total = 1
            adults = 1
        
        passenger_count = {"adults": adults, "children": children, "infants": infants, "total": total}
        passengers_details = []
        current_passenger_index = 0
        step = "verify_passenger_count"
            
    elif (
        # FIX H-001/H-003: Never fire flight passenger details logic when inside any hotel step
        not incoming_step.startswith("hotel_") if incoming_step else True
    ) and not step.startswith("hotel_") and step != "hotel_booking_confirmed" and incoming_step != "verify_passenger_count" and (
        result.intent == "provide_details" or
        (step == "awaiting_passenger_details" and (
            result.intent != "general_qa" or
            any([result.passenger_name, result.passenger_email, result.passenger_contact, result.passenger_passport])
        ))
    ):
        result.intent = "provide_details"
        total_pax = passenger_count.get("total") if isinstance(passenger_count, dict) else (int(passenger_count) if passenger_count else 1)
        
        while len(passengers_details) <= current_passenger_index:
            passengers_details.append({})
            
        pax = passengers_details[current_passenger_index]
        raw_text = user_msg_text.strip()
        
        # Extract fields using deterministic extractor
        updated_pax, errors = extract_passenger_fields(raw_text, pax)
        
        # Fallback to LLM-extracted fields if still missing
        if not updated_pax.get("name") and result.passenger_name:
            updated_pax["name"] = result.passenger_name
        if not updated_pax.get("email") and result.passenger_email:
            updated_pax["email"] = result.passenger_email
        if not updated_pax.get("contact") and result.passenger_contact:
            updated_pax["contact"] = result.passenger_contact
        if not updated_pax.get("passport") and result.passenger_passport:
            updated_pax["passport"] = result.passenger_passport
                
        # Re-run validation on all populated fields
        errors = []
        if updated_pax.get("name") and len(updated_pax["name"]) < 2:
            errors.append("Name must be at least 2 characters long.")
        if updated_pax.get("email") and not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", updated_pax["email"]):
            errors.append("Email address is invalid.")
        if updated_pax.get("contact") and not re.match(r"^\+?\d{1,4}\d{10}$", updated_pax["contact"]):
            errors.append("Contact number must include a country code followed strictly by 10 digits (e.g. +919876543210).")
        if updated_pax.get("passport") and (len(updated_pax["passport"]) < 6 or len(updated_pax["passport"]) > 15 or not updated_pax["passport"].isalnum()):
            errors.append("Passport number must be 6-15 alphanumeric characters.")
            
        passengers_details[current_passenger_index] = updated_pax
        pax = updated_pax
        
        if errors:
            pending_clarification = "⚠️ Validation Error:\n" + "\n".join([f"- {err}" for err in errors])
            step = "awaiting_passenger_details"
        else:
            pending_clarification = None
            if not pax.get("name") or not pax.get("email") or not pax.get("contact") or not pax.get("passport"):
                step = "awaiting_passenger_details"
            else:
                current_passenger_index += 1
                if current_passenger_index >= total_pax:
                    step = "awaiting_payment"
                else:
                    step = "awaiting_passenger_details"
                
    elif result.intent == "payment_done" or user_msg_text.strip().lower() == "payment done":
        # Check if we are in hotel flow vs flight flow
        is_hotel_payment = step.startswith("hotel_") or step in ["hotel_awaiting_payment", "hotel_summary"]
        
        if is_hotel_payment:
            # Hotel payment: confirm the hotel booking
            step = "hotel_booking_confirmed"
        else:
            # Flight payment: validate all passenger details are complete
            total_pax = passenger_count.get("total") if isinstance(passenger_count, dict) else (int(passenger_count) if passenger_count else 1)
            details_complete = True
            if not passengers_details or len(passengers_details) < total_pax:
                details_complete = False
            else:
                for p in passengers_details:
                    if not p.get("name") or not p.get("email") or not p.get("contact") or not p.get("passport"):
                        details_complete = False
                        break
            
            if not details_complete:
                pending_clarification = "⚠️ Validation Error:\n- Please complete the passenger details for all passengers before typing 'payment done'."
                step = "awaiting_passenger_details"
            else:
                step = "booking_confirmed"
    elif step == "hotel_confirm_change":
        if is_confirmation or "yes" in msg_text_lower:
            old_ticket = state.get("hotel_ticket") or {}
            selected_hotel = state.get("temp_new_hotel", {}).copy()
            
            # Auto-populate guest details from the old ticket
            selected_hotel["guest_name"] = old_ticket.get("guest_name") or selected_hotel.get("guest_name")
            selected_hotel["guest_email"] = old_ticket.get("guest_email") or selected_hotel.get("guest_email")
            selected_hotel["guest_phone"] = old_ticket.get("guest_phone") or selected_hotel.get("guest_phone")
            selected_hotel["special_requests"] = old_ticket.get("special_requests") or selected_hotel.get("special_requests", "None")
            selected_hotel["arrival_time"] = old_ticket.get("arrival_time") or selected_hotel.get("arrival_time", "None")
            
            # Reset email send flag so confirmation is sent for the new booking
            state["hotel_email_sent"] = False
            state["ticket"] = None
            state["hotel_ticket"] = None
            state["temp_new_hotel"] = None
            
            # Transition directly to hotel summary checkout
            step = "hotel_summary"
            pending_clarification = None
        else:
            # Revert change: clean up temp variables and keep existing confirmed booking
            state["temp_new_hotel"] = None
            old_ticket = state.get("hotel_ticket") or {}
            state["ticket"] = old_ticket
            selected_hotel = state.get("selected_hotel", {}).copy()
            step = "start"
            pending_clarification = None

    elif step.startswith("hotel_"):
        if step in ("hotel_awaiting_budget", "hotel_awaiting_custom_budget") and ("budget" in msg_text_lower or any(b in user_msg_text for b in ["₹", "Rs", "budget"])):
            matched = False
            for b_range in ["₹2,000–₹5,000", "₹5,000–₹8,000", "₹8,000–₹12,000", "₹12,000+", "I'll decide later"]:
                if b_range in user_msg_text or (b_range.replace("₹", "") in user_msg_text):
                    hotel_params["budget"] = b_range
                    step = "hotel_ready_to_search"
                    matched = True
                    break
            if not matched:
                prices = re.findall(r"[\d,]+", user_msg_text)
                if prices:
                    hotel_params["budget"] = user_msg_text.strip()
                    step = "hotel_ready_to_search"
                    matched = True
                    
        elif step == "hotel_confirm_city":
            if is_confirmation or user_msg_text.strip() == "✅ Yes" or "yes" in msg_text_lower:
                dest = flight_params.get("destination", "Pune")
                # FIX H-002: Expanded city_map with all major Indian + international airports
                city_map = {
                    "BOM": "Mumbai", "DEL": "Delhi", "BLR": "Bangalore", "SIN": "Singapore",
                    "PNQ": "Pune", "GOI": "Goa", "HYD": "Hyderabad", "MAA": "Chennai",
                    "CCU": "Kolkata", "AMD": "Ahmedabad", "COK": "Kochi", "JAI": "Jaipur",
                    "IXE": "Mangalore", "TRV": "Thiruvananthapuram", "NAG": "Nagpur",
                    "BBI": "Bhubaneswar", "VTZ": "Visakhapatnam", "STV": "Surat",
                    "PAT": "Patna", "GAU": "Guwahati", "IXB": "Siliguri",
                    "LHR": "London", "CDG": "Paris", "DXB": "Dubai", "JFK": "New York",
                    "LAX": "Los Angeles", "SYD": "Sydney", "NRT": "Tokyo",
                    "FRA": "Frankfurt", "AMS": "Amsterdam", "ICN": "Seoul",
                    "BKK": "Bangkok", "KUL": "Kuala Lumpur", "HKG": "Hong Kong",
                    "DOH": "Doha", "AUH": "Abu Dhabi"
                }
                hotel_params["city"] = city_map.get(dest.upper(), dest)

                # Check if there's a date to suggest (return date for round trip, otherwise departure date)
                hotel_arrival_date = flight_params.get("return_date") or flight_params.get("departure_date")
                if hotel_arrival_date:
                    step = "hotel_confirm_dates"
                else:
                    step = "hotel_awaiting_check_in"
            else:
                step = "hotel_awaiting_city"
                
        elif step == "hotel_confirm_dates":
            if is_confirmation or user_msg_text.strip() == "✅ Yes" or "yes" in msg_text_lower:
                # Use return_date for round-trip (that's when they arrive at destination)
                hotel_params["check_in_date"] = flight_params.get("return_date") or flight_params.get("departure_date")
                step = "hotel_awaiting_check_out"
            else:
                step = "hotel_awaiting_check_in"
                
        elif step == "hotel_awaiting_city":
            hotel_params["city"] = user_msg_text.strip()
            step = "hotel_awaiting_check_in"
            
        elif step == "hotel_awaiting_check_in":
            c_in = result.check_in_date or user_msg_text.strip()
            try:
                datetime.strptime(c_in, "%Y-%m-%d")
                hotel_params["check_in_date"] = c_in
                pending_clarification = None
                step = "hotel_awaiting_check_out"
            except:
                pending_clarification = "⚠️ Validation Error:\n- Please enter a valid date in YYYY-MM-DD format."
            
        elif step == "hotel_awaiting_check_out":
            c_in_str = hotel_params.get("check_in_date")
            c_out = result.check_out_date or user_msg_text.strip()
            if c_in_str and not result.check_out_date:
                resolved = resolve_relative_checkout(c_in_str, user_msg_text)
                if resolved:
                    c_out = resolved
                    
            valid = True
            try:
                dt_in = datetime.strptime(c_in_str, "%Y-%m-%d")
                dt_out = datetime.strptime(c_out, "%Y-%m-%d")
                if dt_out <= dt_in:
                    valid = False
            except:
                valid = False
                
            if valid:
                hotel_params["check_out_date"] = c_out
                pending_clarification = None
                step = "hotel_awaiting_guests"
            else:
                pending_clarification = "⚠️ Validation Error:\n- Check-out date must be a valid date after the check-in date."
            
        elif step == "hotel_awaiting_guests":
            val = user_msg_text.replace("👤 ", "").replace("👥 ", "").replace("👨👩👧 ", "").replace("➕ ", "").strip()
            hotel_params["guests"] = val
            step = "hotel_awaiting_rooms"
            
        elif step == "hotel_awaiting_rooms":
            hotel_params["rooms"] = user_msg_text.strip()
            step = "hotel_awaiting_room_type"

        elif step == "hotel_awaiting_room_type":
            hotel_params["room_type"] = user_msg_text.strip()
            step = "hotel_awaiting_budget"
            
        elif step == "hotel_awaiting_budget":
            val = user_msg_text.strip()
            if "custom" in val.lower() or "✏️" in val:
                step = "hotel_awaiting_custom_budget"
            else:
                hotel_params["budget"] = val
                step = "hotel_awaiting_area"
                
        elif step == "hotel_awaiting_custom_budget":
            hotel_params["budget"] = user_msg_text.strip()
            step = "hotel_awaiting_area"
            
        elif step == "hotel_awaiting_area":
            hotel_params["area"] = user_msg_text.strip()
            step = "hotel_awaiting_category"
            
        elif step == "hotel_awaiting_category":
            hotel_params["category"] = user_msg_text.strip()
            step = "hotel_ready_to_search"
            
        elif step == "hotel_awaiting_guest_name":
            name_clean = user_msg_text.strip()
            if len(name_clean) >= 2:
                selected_hotel["guest_name"] = name_clean
                pending_clarification = None
            else:
                pending_clarification = "⚠️ Validation Error:\n- Name must be at least 2 characters long."
                
        elif step == "hotel_awaiting_guest_email":
            email_clean = user_msg_text.strip()
            if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email_clean):
                selected_hotel["guest_email"] = email_clean
                pending_clarification = None
            else:
                pending_clarification = "⚠️ Validation Error:\n- Email address is invalid."
                
        elif step == "hotel_awaiting_guest_phone":
            contact_clean = re.sub(r"[^\d+]", "", user_msg_text.strip())
            if re.match(r"^\+?\d{1,4}\d{10}$", contact_clean):
                selected_hotel["guest_phone"] = contact_clean
                pending_clarification = None
            else:
                pending_clarification = "⚠️ Validation Error:\n- Contact number must include a country code followed strictly by 10 digits."
                
        elif step == "hotel_awaiting_special_requests":
            val = user_msg_text.strip()
            selected_hotel["special_requests"] = "None" if val.lower() in ["skip", "none", "no special request", "no"] else val
            
        elif step == "hotel_awaiting_arrival_time":
            val = user_msg_text.strip()
            selected_hotel["arrival_time"] = "None" if val.lower() in ["skip", "none", "no"] else val
            
        if incoming_step and (incoming_step.startswith("hotel_awaiting_guest_") or incoming_step in ["hotel_awaiting_special_requests", "hotel_awaiting_arrival_time", "hotel_summary"]):
            if not selected_hotel.get("guest_name"): step = "hotel_awaiting_guest_name"
            elif not selected_hotel.get("guest_email"): step = "hotel_awaiting_guest_email"
            elif not selected_hotel.get("guest_phone"): step = "hotel_awaiting_guest_phone"
            elif "special_requests" not in selected_hotel: step = "hotel_awaiting_special_requests"
            elif "arrival_time" not in selected_hotel: step = "hotel_awaiting_arrival_time"
            else: step = "hotel_summary"
            
    is_active_flow = is_gathering_details or step in [
        "ready_to_search", "flight_selecting", "hotel_ready_to_search", "hotel_selecting", 
        "hotel_summary", "hotel_awaiting_payment",
        "itinerary_awaiting_city", "itinerary_awaiting_start_date", "itinerary_awaiting_days",
        "plan_itinerary"  # include plan_itinerary so "7 Days" quick reply isn't overridden by general_qa
    ] or incoming_step in ["itinerary_awaiting_days", "itinerary_awaiting_city", "itinerary_awaiting_start_date"]

    interruption_question = None

    # FIX F-002: Detect greetings mid-active-flow and route them to interruption handling
    _GREETING_WORDS = {"hello", "hi", "hey", "howdy", "good morning", "good afternoon", "good evening", "greetings"}
    _is_pure_greeting = msg_text_lower.strip() in _GREETING_WORDS

    if result.intent == "general_qa" and not is_active_flow:
        step = "general_qa"
    elif result.intent == "general_qa" and is_active_flow:
        is_providing_parameter = False
        is_q = is_question(user_msg_text)
        # Use incoming_step (original step before advancement) to verify parameter provision
        if incoming_step in ["awaiting_origin_dest", "hotel_awaiting_city", "itinerary_awaiting_city"] and (result.origin or result.destination or result.hotel_city or (user_msg_text.strip() and not is_q)):
            is_providing_parameter = True
        elif incoming_step in ["awaiting_departure_date", "hotel_awaiting_check_in", "hotel_awaiting_check_out"] and (result.departure_date or result.check_in_date or result.check_out_date or (user_msg_text.strip() and not is_q)):
            is_providing_parameter = True
        elif incoming_step in ["awaiting_journey_type", "awaiting_return_date", "invalid_return_date"] and (result.journey_type or result.return_date or (user_msg_text.strip() and not is_q)):
            is_providing_parameter = True
            step = get_next_flight_step(flight_params, invalid_date, invalid_return_date)
        elif incoming_step in ["awaiting_passenger_count"] and (result.adults_count or result.children_count or result.infants_count or (user_msg_text.strip() and not is_q)):
            is_providing_parameter = True
        elif incoming_step == "itinerary_awaiting_days":
            if re.search(r"\b\d+\b", user_msg_text) or (user_msg_text.strip() and not is_q):
                is_providing_parameter = True
        elif incoming_step == "awaiting_passenger_details" and (result.passenger_name or result.passenger_email or result.passenger_contact or result.passenger_passport or (user_msg_text.strip() and not is_q)):
            is_providing_parameter = True
        elif incoming_step in ["hotel_awaiting_guest_name", "hotel_awaiting_guest_email", "hotel_awaiting_guest_phone", "hotel_awaiting_special_requests", "hotel_awaiting_arrival_time"] and user_msg_text.strip() and not is_q:
            is_providing_parameter = True

        if _is_pure_greeting and is_active_flow:
            # FIX F-002: Pure greetings mid-flow get a warm reply via interruption_question
            interruption_question = user_msg_text
        elif is_confirmation or is_providing_parameter:
            interruption_question = None
        else:
            interruption_question = user_msg_text

    elif (result.intent == "book_hotel" or user_msg_text.strip().lower() == "book a hotel") and not is_gathering_details and step != "hotel_ready_to_search":
        # FIX H-001: Use pre-extraction snapshots to check for REAL prior flights
        city_already_known = bool(hotel_params.get("city"))
        has_prior_flight = bool(_original_flight_destination or _original_flight_has_airline)
        if has_prior_flight and not city_already_known:
            # Only show city confirmation when we have a REAL prior flight and don't yet know city
            step = "hotel_confirm_city"
        elif has_prior_flight and city_already_known:
            # City was provided in message — skip confirm, go straight to dates
            hotel_arrival_date = flight_params.get("return_date") or _original_departure_date
            if hotel_arrival_date:
                step = "hotel_confirm_dates"
            else:
                step = "hotel_awaiting_check_in"
        else:
            # No prior flight — skip directly to check-in since city is now known
            step = "hotel_awaiting_check_in" if city_already_known else "hotel_awaiting_city"

    elif (result.intent == "book_flight" or user_msg_text.strip().lower() in ["book a flight", "book flight", "flight", "fly"]) and not is_gathering_details:
        # Starting a fresh flight booking:
        # If flight was already confirmed or previous session had leftover flight params, reset them if no new cities provided in message
        is_fresh_flight_req = user_msg_text.strip().lower() in ["book a flight", "book flight", "flight", "fly"] or state.get("ticket") is not None
        if is_fresh_flight_req and not result.origin and not result.destination:
            flight_params.clear()
            selected_flight.clear()
            passengers_details.clear()
            passenger_count.clear()
            current_passenger_index = 0
        step = get_next_flight_step(flight_params, invalid_date)
        
    return {
        "current_step": step,
        "latest_intent": result.intent,
        "flight_params": flight_params,
        "passenger_details": passenger_details,
        "selected_flight": selected_flight,
        "passenger_count": passenger_count,
        "passengers_details": passengers_details,
        "current_passenger_index": current_passenger_index,
        "hotel_params": hotel_params,
        "selected_hotel": selected_hotel,
        "pending_clarification": pending_clarification,
        "interruption_question": interruption_question,
        "clarification_repeats": state.get("clarification_repeats") or {},
        "options_to_show": options_to_show,
        "hotel_ticket": state.get("hotel_ticket"),
        "temp_new_hotel": state.get("temp_new_hotel")
    }
