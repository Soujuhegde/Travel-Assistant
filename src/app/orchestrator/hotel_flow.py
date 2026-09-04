import time
import random
import string
from datetime import datetime
from typing import Dict, Any, List
from app.schemas.chat import TaskRequest
from app.agents.hotel_agent import call_hotel_agent

def get_hotel_contextual_reminder(step: str, state: Dict[str, Any]) -> str | None:
    flight_params = state.get("flight_params") or {}
    selected_hotel = state.get("selected_hotel") or {}
    # FIX H-002: Expanded city_map for all major airports
    _CITY_MAP = {
        "BOM": "Mumbai", "DEL": "Delhi", "BLR": "Bangalore", "SIN": "Singapore",
        "PNQ": "Pune", "GOI": "Goa", "HYD": "Hyderabad", "MAA": "Chennai",
        "CCU": "Kolkata", "AMD": "Ahmedabad", "COK": "Kochi", "JAI": "Jaipur",
        "IXE": "Mangalore", "TRV": "Thiruvananthapuram", "NAG": "Nagpur",
        "BBI": "Bhubaneswar", "VTZ": "Visakhapatnam", "GAU": "Guwahati",
        "LHR": "London", "CDG": "Paris", "DXB": "Dubai", "JFK": "New York",
        "LAX": "Los Angeles", "SYD": "Sydney", "NRT": "Tokyo",
        "FRA": "Frankfurt", "AMS": "Amsterdam", "ICN": "Seoul",
        "BKK": "Bangkok", "KUL": "Kuala Lumpur", "HKG": "Hong Kong",
        "DOH": "Doha", "AUH": "Abu Dhabi"
    }

    if step == "hotel_confirm_city":
        dest = flight_params.get("destination", "your destination")
        dest_name = _CITY_MAP.get(dest.upper(), dest)
        return f"Shall we search for hotels in {dest_name}?"
    elif step == "hotel_confirm_dates":
        check_in = flight_params.get("departure_date", "flight date")
        return f"Would you like to check in to the hotel on the same day as your flight ({check_in})?"
    elif step == "hotel_awaiting_city":
        return "Which city would you like to book a hotel in?"
    elif step == "hotel_awaiting_check_in":
        return "When will you be checking in to the hotel? (Format: YYYY-MM-DD)"
    elif step == "hotel_awaiting_check_out":
        return "When is your check-out date from the hotel? (Format: YYYY-MM-DD)"
    elif step == "hotel_awaiting_guests":
        return "How many guests will be staying at the hotel?"
    elif step == "hotel_awaiting_rooms":
        return "How many rooms would you like to reserve?"
    elif step == "hotel_awaiting_room_type":
        return "What type of room would you prefer for your stay?"
    elif step == "hotel_awaiting_budget":
        return "What is your preferred budget range per night for the hotel?"
    elif step == "hotel_awaiting_custom_budget":
        return "Please enter your preferred budget range per night (e.g. ₹3,000–₹6,000)."
    elif step == "hotel_awaiting_area":
        return "Where in the city would you prefer to stay (e.g. near airport, city centre)?"
    elif step == "hotel_awaiting_category":
        return "What class or type of hotel are you looking for?"
    elif step == "hotel_awaiting_guest_name":
        return "Could you please provide the guest's full name for the booking?"
    elif step == "hotel_awaiting_guest_email":
        return "Could you please provide the guest's email address for confirmation?"
    elif step == "hotel_awaiting_guest_phone":
        return "Could you please provide the guest's contact number for the reservation?"
    elif step == "hotel_awaiting_special_requests":
        return "Do you have any special requests for the stay, or should we skip this?"
    elif step == "hotel_awaiting_arrival_time":
        return "What is your estimated arrival time at the hotel, or would you like to skip this?"
    elif step in ["hotel_awaiting_payment", "hotel_summary"]:
        return f"Please click the 'Proceed to Booking' button above to complete your stay at {selected_hotel.get('name')}, or say 'Payment Done' once finished."
    return None

def handle_hotel_clarification(step: str, state: Dict[str, Any]) -> Dict[str, Any]:
    msg = ""
    replies = []
    options = []
    ticket = None

    flight_params = state.get("flight_params") or {}
    hotel_params = state.get("hotel_params") or {}
    selected_hotel = state.get("selected_hotel") or {}

    # FIX H-002: Expanded city_map reused here
    _CITY_MAP = {
        "BOM": "Mumbai", "DEL": "Delhi", "BLR": "Bangalore", "SIN": "Singapore",
        "PNQ": "Pune", "GOI": "Goa", "HYD": "Hyderabad", "MAA": "Chennai",
        "CCU": "Kolkata", "AMD": "Ahmedabad", "COK": "Kochi", "JAI": "Jaipur",
        "IXE": "Mangalore", "TRV": "Thiruvananthapuram", "NAG": "Nagpur",
        "BBI": "Bhubaneswar", "VTZ": "Visakhapatnam", "GAU": "Guwahati",
        "LHR": "London", "CDG": "Paris", "DXB": "Dubai", "JFK": "New York",
        "LAX": "Los Angeles", "SYD": "Sydney", "NRT": "Tokyo",
        "FRA": "Frankfurt", "AMS": "Amsterdam", "ICN": "Seoul",
        "BKK": "Bangkok", "KUL": "Kuala Lumpur", "HKG": "Hong Kong",
        "DOH": "Doha", "AUH": "Abu Dhabi"
    }

    if step == "hotel_confirm_city":
        dest = flight_params.get("destination", "Pune")
        dest_name = _CITY_MAP.get(dest.upper(), dest)
        msg = f"I see you've booked a flight to {dest_name}. Are you planning to book a hotel in {dest_name}?"
        replies = ["✅ Yes", "❌ No, different city"]
    elif step == "hotel_confirm_dates":
        # For round-trip flights, arrival is the return date; for one-way, use departure_date
        check_in = flight_params.get("return_date") or flight_params.get("departure_date", datetime.now().strftime("%Y-%m-%d"))
        msg = f"Your flight arrival is on {check_in}. Would you like to check in on the same day ({check_in})?"
        replies = ["✅ Yes", "✏️ Edit Dates"]
    elif step == "hotel_awaiting_city":
        msg = "Hi! I'm Sara, your AI travel companion. I'll help you find the perfect hotel. Which city would you like to stay in?"
    elif step == "hotel_awaiting_check_in":
        clarification = state.get("pending_clarification")
        prefix = f"{clarification}\n\n" if clarification else ""
        msg = f"{prefix}When will you be checking in? (Format: YYYY-MM-DD)"
        replies = ["Today", "Tomorrow"]
    elif step == "hotel_awaiting_check_out":
        clarification = state.get("pending_clarification")
        prefix = f"{clarification}\n\n" if clarification else ""
        msg = f"{prefix}And when is your check-out date? (Format: YYYY-MM-DD)"
        # Generate dynamic quick replies relative to check-in date (not today)
        c_in_str = hotel_params.get("check_in_date")
        try:
            from datetime import timedelta
            c_in_dt = datetime.strptime(c_in_str, "%Y-%m-%d")
            d1 = (c_in_dt + timedelta(days=1)).strftime("%Y-%m-%d")
            d2 = (c_in_dt + timedelta(days=2)).strftime("%Y-%m-%d")
            d3 = (c_in_dt + timedelta(days=3)).strftime("%Y-%m-%d")
            replies = [d1, d2, d3]
        except:
            replies = ["Tomorrow", "In 2 days", "In 3 days"]
    elif step == "hotel_awaiting_guests":
        msg = "How many guests will be staying?"
        replies = ["👤 1 Adult", "👥 2 Adults", "👨👩👧 Family", "➕ Custom"]
    elif step == "hotel_awaiting_rooms":
        msg = "How many rooms would you like to book?"
        replies = ["1 Room", "2 Rooms", "Custom"]
    elif step == "hotel_awaiting_room_type":
        msg = "What type of room would you prefer for your stay?"
        replies = ["Standard Room", "Deluxe Room", "Luxury Room / Suite", "No Preference"]
    elif step == "hotel_awaiting_budget":
        msg = "What's your preferred budget per night?"
        replies = ["₹2,000–₹5,000", "₹5,000–₹8,000", "₹8,000–₹12,000", "₹12,000+", "✏️ Custom Budget", "I'll decide later"]
    elif step == "hotel_awaiting_custom_budget":
        msg = "Please enter your preferred budget per night (e.g. ₹3,000–₹6,000 or ₹4,500+):"
    elif step == "hotel_awaiting_area":
        msg = "Where would you like to stay?"
        replies = ["Near Airport", "Near City Centre", "Near Business District", "Near Tourist Attractions", "No Preference"]
    elif step == "hotel_awaiting_category":
        msg = "What type of hotel are you looking for?"
        replies = ["⭐ 3-Star", "⭐⭐⭐⭐ 4-Star", "⭐⭐⭐⭐⭐ 5-Star", "Boutique Hotel", "No Preference"]
    elif step == "hotel_awaiting_guest_name":
        clarification = state.get("pending_clarification")
        prefix = f"{clarification}\n\n" if clarification else ""
        msg = f"{prefix}Please enter the Guest's Full Name (as per government ID/passport):"
    elif step == "hotel_awaiting_guest_email":
        clarification = state.get("pending_clarification")
        prefix = f"{clarification}\n\n" if clarification else ""
        msg = f"{prefix}Please enter the Guest's Email Address:"
    elif step == "hotel_awaiting_guest_phone":
        clarification = state.get("pending_clarification")
        prefix = f"{clarification}\n\n" if clarification else ""
        msg = f"{prefix}Please enter the Guest's Mobile Number (with country code, e.g. +919876543210):"
    elif step == "hotel_awaiting_special_requests":
        msg = "Do you have any Special Requests? (Optional)"
        replies = ["Skip", "No special request"]
    elif step == "hotel_awaiting_arrival_time":
        msg = "What is your Estimated Arrival Time? (Optional)"
        replies = ["Skip", "No preference"]
    elif step == "hotel_selecting":
        options_to_show = state.get("options_to_show") or []
        options = options_to_show
        if len(options_to_show) == 1:
            msg = "Here is the hotel I found for you. Would you like to proceed with this booking, or see all other options?"
            replies = ["Proceed with this option", "See other options"]
        else:
            msg = "Here are some great hotels for your stay. Click to choose your preferred one."
    elif step == "hotel_summary":
        price_str = selected_hotel.get("price", selected_hotel.get("price_per_night", "₹3,200"))
        try:
            d1 = datetime.strptime(hotel_params.get("check_in_date"), "%Y-%m-%d")
            d2 = datetime.strptime(hotel_params.get("check_out_date"), "%Y-%m-%d")
            nights = (d2 - d1).days
            if nights <= 0: nights = 1
        except:
            nights = 1

        rooms_str = hotel_params.get("rooms", "1")
        try:
            rooms_clean = int("".join(filter(str.isdigit, rooms_str)))
            if rooms_clean <= 0: rooms_clean = 1
        except:
            rooms_clean = 1

        try:
            price_str_no_cents = price_str.split(".")[0]
            p_clean = int("".join(filter(str.isdigit, price_str_no_cents)))
            total_p = p_clean * nights * rooms_clean
            total_price = f"₹{total_p:,}.00"
        except:
            total_price = f"{price_str} x {nights} night(s)"
            
        msg = f"📋 Booking Summary\n\n🏨 Hotel: {selected_hotel.get('name')}\n🌆 City: {hotel_params.get('city', 'Mumbai')}\n🛋️ Room Type: {hotel_params.get('room_type', 'Standard Room')}\n📅 Check-in: {hotel_params.get('check_in_date')}\n📅 Check-out: {hotel_params.get('check_out_date')}\n👥 Guests: {hotel_params.get('guests', '1 Adult')}\n🛏️ Rooms: {hotel_params.get('rooms', '1')}\n💰 Total Price: {total_price}\n👤 Guest Name: {selected_hotel.get('guest_name')}"
        replies = ["Payment Done"]
        options = [{"type": "action_button", "label": "Proceed to Booking", "url": selected_hotel.get("booking_link") or selected_hotel.get("booking_url") or "https://booking.com"}]
        
    elif step == "hotel_awaiting_payment":
        link = selected_hotel.get("booking_link") or selected_hotel.get("booking_url") or "https://booking.com"
        msg = f"Perfect! Let's proceed with booking your stay at {selected_hotel.get('name')}."
        replies = ["Payment Done"]
        options = [{"type": "action_button", "label": "Proceed to Booking", "url": link}]
        
    elif step == "hotel_confirm_change":
        old_hotel = state.get("hotel_ticket", {}).get("hotel_name", "your booked hotel")
        new_hotel = state.get("temp_new_hotel", {}).get("name", "the new hotel")
        msg = f"You already have a confirmed booking at **{old_hotel}**. Would you like to cancel it and book **{new_hotel}** instead?"
        replies = ["Yes, cancel and book new", "No, keep existing"]
        
    elif step == "hotel_booking_confirmed":
        pnr = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        price_str = selected_hotel.get("price", selected_hotel.get("price_per_night", "₹2,250"))
        try:
            price_str_no_cents = price_str.split(".")[0]
            p_clean = int("".join(filter(str.isdigit, price_str_no_cents)))
            try:
                d1 = datetime.strptime(hotel_params.get("check_in_date"), "%Y-%m-%d")
                d2 = datetime.strptime(hotel_params.get("check_out_date"), "%Y-%m-%d")
                nights = (d2 - d1).days
                if nights <= 0: nights = 1
            except:
                nights = 1
                
            rooms_str = hotel_params.get("rooms", "1")
            try:
                rooms_clean = int("".join(filter(str.isdigit, rooms_str)))
                if rooms_clean <= 0: rooms_clean = 1
            except:
                rooms_clean = 1
                
            total_p = p_clean * nights * rooms_clean
            total_price = f"₹{total_p:,}.00"
        except:
            nights = 1
            total_price = price_str
            
        formatted_price = price_str
        if not formatted_price.startswith("₹") and not formatted_price.startswith("$"):
            formatted_price = f"₹{formatted_price}"
        if not formatted_price.endswith(".00") and "." not in formatted_price:
            formatted_price = f"{formatted_price}.00"
            
        room_type = hotel_params.get("room_type")
        if not room_type:
            if selected_hotel.get("star_rating", 3) >= 5:
                room_type = "Executive Room"
            else:
                room_type = "Standard Room"
            
        ticket = {
            "hotel_name": selected_hotel.get("name", "The Hotel Prime"),
            "room_type": room_type,
            "city": hotel_params.get("city", "Mumbai"),
            "check_in_date": hotel_params.get("check_in_date", "12 PM"),
            "check_out_date": hotel_params.get("check_out_date", "11 AM"),
            "guests": hotel_params.get("guests", "01 Adult"),
            "rooms": hotel_params.get("rooms", "01 Room"),
            "price_per_night": formatted_price,
            "total_price": total_price,
            "nights": nights,
            "guest_name": selected_hotel.get("guest_name", "Guest"),
            "image": selected_hotel.get("images", [""])[0] if selected_hotel.get("images") else "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=200&q=80"
        }
        msg = f"🎉 Payment Successful! Booking Confirmed. 🎉\n\nYour stay at {selected_hotel.get('name')} is confirmed with reservation number {pnr}."
        replies = ["Book a Flight", "Plan an Itinerary"]

    return {"final_response": msg, "quick_replies": replies, "options_to_show": options, "ticket": ticket}

def hotel_node(state: Dict[str, Any]) -> Dict[str, Any]:
    request = TaskRequest(
        task_id=f"hotel_{int(time.time())}",
        task_type="hotel_search",
        session_id=state.get("session_id", "default"),
        parameters=state.get("hotel_params", {})
    )
    response = call_hotel_agent(request)
    
    options = []
    if response.status == "success":
        for r in response.results:
            r["type"] = "hotel"
            options.append(r)
            
    final_text = "Here are some great hotels for your stay. Click to choose your preferred one." if options else "Sorry, we could not find any hotels for those dates."
    
    serpapi_calls = state.get("serpapi_calls") or []
    if response.metadata.get("serpapi_request"):
        serpapi_calls.append({
            "engine": "google_hotels",
            "request": response.metadata.get("serpapi_request"),
            "response": response.metadata.get("serpapi_response")
        })
        
    return {
        "final_response": final_text, 
        "options_to_show": options[:3], 
        "quick_replies": [], 
        "hotel_result": response.model_dump(), 
        "current_step": "hotel_selecting",
        "serpapi_calls": serpapi_calls
    }
