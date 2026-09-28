import os
import re
from typing import TypedDict, Annotated, Literal, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.orchestrator.nlu_parser import parse_intent, llm
from app.orchestrator.flight_flow import flight_node, get_flight_contextual_reminder, handle_flight_clarification
from app.orchestrator.hotel_flow import hotel_node, get_hotel_contextual_reminder, handle_hotel_clarification
from app.orchestrator.itinerary_flow import get_itinerary_contextual_reminder, handle_itinerary_clarification
from app.utils.cleaner import clean_travel_response

from app.schemas.state import ConversationState, FlightState, HotelState, CommonState

def route_next(state: ConversationState):
    step = state.get("current_step")
    if step == "ready_to_search":
        return "flight_node"
    if step == "hotel_ready_to_search":
        return "hotel_node"
    return "ask_clarification"

def get_contextual_booking_reminder(step, state):
    if not step:
        return None
    # Check flight steps
    if step in ["awaiting_origin_dest", "awaiting_departure_date", "invalid_departure_date", "awaiting_journey_type", "awaiting_return_date", "invalid_return_date", "flight_selecting", "awaiting_passenger_count", "verify_passenger_count", "awaiting_passenger_details", "awaiting_payment", "flight_awaiting_payment"]:
        return get_flight_contextual_reminder(step, state)
    # Check hotel steps
    elif step.startswith("hotel_") or step == "hotel_summary":
        return get_hotel_contextual_reminder(step, state)
    # Check itinerary steps
    elif step.startswith("itinerary_"):
        return get_itinerary_contextual_reminder(step, state)
    return None

def ask_clarification(state: ConversationState):
    step = state.get("current_step")
    latest_intent = state.get("latest_intent")
    
    flight_params = state.get("flight_params") or {}
    hotel_params = state.get("hotel_params") or {}
    selected_hotel = state.get("selected_hotel") or {}
    selected_flight = state.get("selected_flight") or {}
    
    msg = "How can I help you?"
    replies = []
    options = []
    
    # Conversational QA interruption handling
    interruption_question = state.get("interruption_question")
    interruption_answer = ""
    identified_index = None
    if interruption_question and llm:
        options_to_show = state.get("options_to_show") or []
        options_context = ""
        if options_to_show:
            options_context = "\nOptions currently visible to the user on their screen:\n"
            for idx, opt in enumerate(options_to_show):
                if opt.get("type") == "flight" or "pricing" in opt:
                    pricing_str = ", ".join(f"{p['class']}: {p['price']}" for p in opt.get("pricing", []))
                    options_context += f"- Flight Option {idx}: Airline {opt.get('airline_name')} flight {opt.get('flight_numbers')}, base price {opt.get('price')} ({pricing_str})\n"
                else:
                    options_context += f"- Hotel Option {idx}: Hotel {opt.get('name')}, rating {opt.get('star_rating')}, price per night {opt.get('price_per_night')}, amenities {', '.join(opt.get('amenities', []))}\n"

        qa_prompt = f"""You are a friendly travel assistant chatbot helping the user complete a booking.

The user sent this message while in the middle of a booking: "{interruption_question}"

Classify the message into ONE of these 3 categories and respond accordingly:

CATEGORY 1 — GREETING or CASUAL (hello, hi, hey, thanks, how are you, good morning, ok, sure, etc.):
   Respond warmly and naturally, then gently redirect to the booking.
   Example for "hello": "Hello! 😊 Is there anything I can help you with, or shall we continue with your booking?"
   Example for "thanks": "You're welcome! Shall we continue with your booking? or You are Welcome , Please let me know if u need any help " 
   Keep it short, friendly, and conversational.

CATEGORY 2 — TRAVEL-RELATED QUESTION (airports, airlines, visa, luggage, destination tips, hotel amenities, weather for a trip, "what to eat in [city]", etc.):
   Answer directly and concisely in under 2 sentences.

CATEGORY 3 — COMPLETELY OFF-TOPIC (generic food recipes like "what is biryani", coding, math, science, personal advice, anything unrelated to travel):
   Respond exactly with: "I'm sorry, but I can only assist with travel-related queries such as flight bookings, hotel reservations, and itinerary planning. Please ask a travel-related question."

You must respond with a JSON object inside a ```json ``` block with these keys:
- "answer": your warm conversational response (Category 1, 2, or 3)
- "identified_option_index": if (and only if) the user is comparing or referring to one of the visible options above (e.g. "is the Indigo flight cheaper?" or "which is the expensive one?"), set this to the 0-based index of that option. Otherwise, set it to null.

Ensure you follow the strict formatting and rules. Do not hallucinate fields.
"""
        try:
            msgs = [SystemMessage(content=qa_prompt)] + state["messages"][-2:]
            response = llm.invoke(msgs)
            content = response.content.strip()
            
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                import json
                data = json.loads(match.group(0))
            else:
                import json
                data = json.loads(content)
                
            raw_answer = data.get("answer", "").strip()
            interruption_answer = clean_travel_response(raw_answer) + "\n\n" if raw_answer else ""
            identified_index = data.get("identified_option_index")
            if identified_index is not None:
                try:
                    identified_index = int(identified_index)
                except (ValueError, TypeError):
                    identified_index = None
        except Exception as e:
            print(f"Error generating/parsing interruption JSON: {e}")
            try:
                msgs = [SystemMessage(content=qa_prompt.split("You must respond with a JSON")[0])] + state["messages"][-2:]
                response = llm.invoke(msgs)
                interruption_answer = clean_travel_response(response.content.strip()) + "\n\n"
            except Exception as ex:
                print(f"Default LLM call also failed: {ex}. Using local rule-based travel QA fallback.")
                city = hotel_params.get("city") or flight_params.get("destination") or ""
                interruption_answer = fallback_travel_qa(interruption_question, city) + "\n\n"
            identified_index = None

    # Guard repeats: check if we have already repeated the prompt for this step
    clarification_repeats = state.get("clarification_repeats") or {}

    _DECLINE_MARKER = "I'm sorry, I can only assist"

    def filter_options_for_query(options: list, query: str) -> list:
        if not options or not query:
            return options
        q = query.lower()
        
        # 1. Index checks
        if "first" in q or "option 1" in q or "1st" in q:
            return [options[0]] if len(options) >= 1 else options
        if "second" in q or "option 2" in q or "2nd" in q:
            return [options[1]] if len(options) >= 2 else options
        if "third" in q or "option 3" in q or "3rd" in q:
            return [options[2]] if len(options) >= 3 else options
            
        # 2. Price sorting checks
        if "cheapest" in q or "lowest" in q or "affordable" in q or "budget" in q:
            def get_price(opt):
                p_str = opt.get("price") or opt.get("price_per_night") or "999999"
                p_str_no_cents = p_str.split(".")[0]
                digits = "".join(filter(str.isdigit, p_str_no_cents))
                return int(digits) if digits else 999999
            return [min(options, key=get_price)]
            
        # 3. Brand name checks (e.g. airline or hotel name matching)
        matched = []
        for opt in options:
            name = opt.get("airline_name", opt.get("airline", opt.get("name", "")))
            if name and name.lower() in q:
                matched.append(opt)
        if matched:
            return matched
            
        return options

    def get_msg_content(msg):
        if hasattr(msg, "content"):
            return msg.content
        if isinstance(msg, dict):
            return msg.get("content", "")
        return str(msg)

    def make_response(res_dict):
        if interruption_answer:
            answer_text = interruption_answer.strip()
            
            # Message 1 (main response) is the answer to greeting/question/decline
            res_dict["final_response"] = answer_text
            
            # Message 2 (followup message) is a contextual reminder of the booking step
            reminder = get_contextual_booking_reminder(step, state)
            if reminder:
                res_dict["followup_message"] = reminder
                res_dict["followup_quick_replies"] = res_dict.get("quick_replies", [])
                res_dict["quick_replies"] = []
            else:
                res_dict["followup_message"] = None
                res_dict["followup_quick_replies"] = []
            
            # Special case: identified option in flight/hotel selection
            if identified_index is not None and step in ["flight_selecting", "hotel_selecting"] and not answer_text.startswith(_DECLINE_MARKER):
                options_to_show = state.get("options_to_show") or []
                if 0 <= identified_index < len(options_to_show):
                    single_option = options_to_show[identified_index]
                    type_str = "flight" if (single_option.get("type") == "flight" or "pricing" in single_option) else "hotel"
                    res_dict["followup_message"] = f"Would you like to proceed with this {type_str} or do you want to select another one?"
                    res_dict["options_to_show"] = [single_option]
                    res_dict["followup_quick_replies"] = ["Proceed with this option", "Select another one"]
            elif step in ["flight_selecting", "hotel_selecting"]:
                orig_opts = res_dict.get("options_to_show") or state.get("options_to_show") or []
                res_dict["options_to_show"] = filter_options_for_query(orig_opts, get_msg_content(state["messages"][-1]))
                
        res_dict["interruption_question"] = None
        res_dict["clarification_repeats"] = clarification_repeats
        return res_dict

    # If the user goes off-topic or says something conversational/harsh, handle it dynamically
    if step == "general_qa":
        if llm:
            qa_prompt = f"""You are Sara, a specialized AI luxury travel consultant and trip planner.
You assist travelers with any question related to travel, destinations, itineraries, sightseeing, culture, local foods, hotels, flights, weather, packing, budgeting, transport, and visas.

Guidelines:
1. Scope: Answer all questions about travel, destinations, itineraries, attractions, trip planning, durations, costs, packing, and bookings warmly, helpfully, and clearly.
2. Itinerary & Advice: If the user asks about an itinerary, places to visit, things to do, or trip suggestions, provide a clear, helpful, and well-structured answer with natural bullet points and emojis.
3. Clean Output: Strictly DO NOT wrap your response in code blocks (no ``` or ```markdown). DO NOT output markdown tables or HTML tags. Output pure, clean text/markdown only.
4. Out-of-Scope: Only decline questions that are completely unrelated to travel or destinations (e.g. software programming code, mathematics homework, general physics, personal non-travel advice). If and only if the question is completely unrelated to travel, respond exactly with: "I'm sorry, but I can only assist with travel-related queries such as flight bookings, hotel reservations, and itinerary planning. Please ask a travel-related question."
"""
            msgs = [SystemMessage(content=qa_prompt)] + [m if hasattr(m, 'content') else HumanMessage(content=get_msg_content(m)) for m in state["messages"][-2:]]
            try:
                response = llm.invoke(msgs)
                msg = clean_travel_response(response.content)
            except Exception as e:
                print(f"Error calling general_qa LLM: {e}. Falling back to local travel QA.")
                city = hotel_params.get("city") or flight_params.get("destination") or ""
                msg = fallback_travel_qa(get_msg_content(state["messages"][-1]), city)
        else:
            city = hotel_params.get("city") or flight_params.get("destination") or ""
            msg = fallback_travel_qa(get_msg_content(state["messages"][-1]), city)
        
        replies = ["Book a Flight", "Book a Hotel", "Plan an Itinerary"]
        res_data = {"final_response": msg, "quick_replies": replies, "options_to_show": []}
    elif step in ["awaiting_origin_dest", "invalid_departure_date", "awaiting_departure_date", "awaiting_journey_type", "awaiting_return_date", "invalid_return_date", "flight_selecting", "awaiting_passenger_count", "verify_passenger_count", "awaiting_passenger_details", "awaiting_payment", "flight_awaiting_payment", "booking_confirmed"]:
        res_data = handle_flight_clarification(step, state)
    elif step and (step.startswith("hotel_") or step in ["hotel_booking_confirmed", "hotel_summary"]):
        res_data = handle_hotel_clarification(step, state)
    elif step and (step.startswith("itinerary_") or step == "plan_itinerary"):
        res_data = handle_itinerary_clarification(step, state)
    else:
        res_data = {"final_response": msg, "quick_replies": replies, "options_to_show": options}

    return make_response(res_data)

# Build Graph
builder = StateGraph(ConversationState)

builder.add_node("parse_intent", parse_intent)
builder.add_node("ask_clarification", ask_clarification)
builder.add_node("flight_node", flight_node)
builder.add_node("hotel_node", hotel_node)

builder.add_edge(START, "parse_intent")
builder.add_conditional_edges("parse_intent", route_next)
builder.add_edge("ask_clarification", END)
builder.add_edge("flight_node", END)
builder.add_edge("hotel_node", END)

graph = builder.compile()

def fallback_travel_qa(query: str, city: str) -> str:
    import re
    q = query.lower()
    city_clean = city.upper() if city else ""
    
    # Resolve common city codes
    city_map = {
        "DEL": "Delhi", "BOM": "Mumbai", "GOI": "Goa", "BLR": "Bangalore",
        "CDG": "Paris", "LHR": "London", "DXB": "Dubai", "SIN": "Singapore",
        "JAI": "Jaipur", "HYD": "Hyderabad", "MAA": "Chennai", "CCU": "Kolkata",
        "COK": "Kochi", "AMD": "Ahmedabad", "PNQ": "Pune", "JFK": "New York"
    }
    city_display = city_map.get(city_clean, city) if city_clean else ""
    for code, name in city_map.items():
        if name.lower() in q:
            city_display = name
            break
            
    # Standard Greetings with exact word boundaries
    if any(re.search(rf"\b{w}\b", q) for w in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]):
        return "Hello! 😊 I'm Sara, your AI travel companion. I can help with flight bookings, hotel reservations, custom day-by-day itineraries, and destination tips. How can I assist you today?"
    if any(re.search(rf"\b{w}\b", q) for w in ["thanks", "thank you", "awesome", "perfect", "ok", "okay", "sure"]):
        return "You're very welcome! Let me know if you need itinerary plans, flight options, hotel bookings, or local travel tips."
    if "how are you" in q or "how's it going" in q:
        return "I'm doing great, thank you for asking! Ready to help you plan your next memorable journey. Where would you like to travel?"

    # 1. Itinerary Planning / Customization / Duration Questions
    if any(re.search(rf"\b{w}\b", q) for w in ["itinerary", "itineary", "travel plan", "trip plan", "day-by-day", "how many days", "days enough", "customize", "schedule"]):
        dest = city_display if city_display else "your destination"
        if "goa" in q or dest.lower() == "goa":
            return "For **Goa**, a 3 to 5-day trip is ideal! You can spend Days 1-2 exploring North Goa beaches and forts (Aguada, Baga), Day 3 exploring Old Goa heritage churches and Fontainhas Latin Quarter, and Days 4-5 relaxing in South Goa (Palolem, Dudhsagar Falls). You can ask me 'Plan a 3-day itinerary for Goa' anytime!"
        elif "mumbai" in q or dest.lower() == "mumbai":
            return "For **Mumbai**, 3 days gives you a great mix: Day 1 for South Mumbai heritage (Gateway of India, Marine Drive, Colaba), Day 2 for arts & Bollywood (Kala Ghoda, Bandra Bandstand), and Day 3 for Kanheri Caves or Elephanta Island. Click 'Plan an Itinerary' to build a custom schedule!"
        elif "delhi" in q or dest.lower() == "delhi":
            return "For **Delhi**, 3 to 4 days is recommended: Old Delhi monuments & street food (Red Fort, Chandni Chowk), New Delhi landmarks (India Gate, Qutub Minar, Humayun's Tomb), and cultural hubs (Akshardham, Lotus Temple). Click 'Plan an Itinerary' to create a custom day-by-day plan!"
        elif "jaipur" in q or dest.lower() == "jaipur":
            return "For **Jaipur**, 2 to 3 days is perfect to explore Amer Fort, Hawa Mahal, City Palace, Jantar Mantar, and shop for vibrant handicrafts in the Johari Bazaar."
        else:
            return f"I can generate a tailored day-by-day itinerary for **{dest}** complete with morning, afternoon, and evening activities, restaurant picks, and budget estimates! Simply type 'Plan a 3-day itinerary for {dest}' or click 'Plan an Itinerary'."

    # 2. Attractions / Must visit places
    if any(re.search(rf"\b{w}\b", q) for w in ["place", "places", "visit", "attraction", "attractions", "things to do", "sightsee", "sightseeing", "explore", "beach", "beaches", "monument", "monuments"]):
        if "del" in q or "delhi" in q or (city_display and city_display.lower() == "delhi"):
            return "Must-visit places in **Delhi** include the UNESCO World Heritage sites Red Fort and Qutub Minar, India Gate, Humayun's Tomb, Lotus Temple, and the vibrant markets of Chandni Chowk."
        elif "bom" in q or "mumbai" in q or (city_display and city_display.lower() == "mumbai"):
            return "Key attractions in **Mumbai** include Gateway of India, Marine Drive (Queen's Necklace), Chhatrapati Shivaji Maharaj Terminus, Elephanta Caves, Bandra Bandstand, and Sanjay Gandhi National Park."
        elif "goa" in q or (city_display and city_display.lower() == "goa"):
            return "Top attractions in **Goa** include Baga & Calangute Beaches, historic Fort Aguada, Basilica of Bom Jesus, colorful Fontainhas Latin Quarter, Dudhsagar Waterfalls, and serene Palolem Beach."
        elif "blr" in q or "bangalore" in q or (city_display and city_display.lower() == "bangalore"):
            return "In **Bangalore**, visit the historic Bangalore Palace, Lalbagh Botanical Garden & Glass House, Cubbon Park, Tipu Sultan's Summer Palace, and the vibrant cafes of Indiranagar and Church Street."
        elif "jai" in q or "jaipur" in q or (city_display and city_display.lower() == "jaipur"):
            return "In **Jaipur**, highlights include Amer Fort, Hawa Mahal (Palace of Winds), City Palace, Jal Mahal, Nahargarh Fort sunset view, and colorful bazaars."
        elif "par" in q or "cdg" in q or "paris" in q or (city_display and city_display.lower() == "paris"):
            return "In **Paris**, top highlights are the Eiffel Tower, Louvre Museum, Notre-Dame Cathedral, Arc de Triomphe, Montmartre & Sacré-Cœur, and a scenic Seine River cruise."
        elif "lon" in q or "lhr" in q or "london" in q or (city_display and city_display.lower() == "london"):
            return "When in **London**, must-see attractions include Tower of London & Tower Bridge, British Museum, London Eye, Buckingham Palace, Big Ben, and Westminster Abbey."
        elif "dxb" in q or "dubai" in q or (city_display and city_display.lower() == "dubai"):
            return "In **Dubai**, visit the Burj Khalifa observation deck, Dubai Mall & Fountain show, Palm Jumeirah, desert safari dune bashing, and the historic Al Fahidi district."
        else:
            dest = city_display if city_display else "your destination"
            return f"Top things to do in **{dest}** include exploring central historic landmarks, visiting renowned cultural museums, strolling through local artisan bazaars, and enjoying scenic sunset viewpoints."

    # 3. Food & Dining
    if any(re.search(rf"\b{w}\b", q) for w in ["eat", "food", "dish", "dishes", "cuisine", "restaurant", "restaurants", "culinary", "delicacy", "breakfast", "lunch", "dinner"]):
        if "del" in q or "delhi" in q or (city_display and city_display.lower() == "delhi"):
            return "Delhi's culinary highlights include famous street food like Chole Bhature, Golgappas, Butter Chicken at Moti Mahal / Gulati, and kebabs in Old Delhi's Karim's."
        elif "bom" in q or "mumbai" in q or (city_display and city_display.lower() == "mumbai"):
            return "Famous foods in Mumbai include Vada Pav, Pav Bhaji at Cannon / Sardar, Bhel Puri at Chowpatty, coastal seafood like Bombay Duck and Surmai fry, and Irani cafe bun maska chai."
        elif "goa" in q or (city_display and city_display.lower() == "goa"):
            return "In Goa, must-try dishes include traditional Goan Fish Curry Thali, Pork Vindaloo / Sorpotel, Butter Garlic Prawns at beach shacks, and layered Bebinca dessert."
        elif "blr" in q or "bangalore" in q or (city_display and city_display.lower() == "bangalore"):
            return "In Bangalore, savor crispy Benne Masala Dosa at CTR / Vidyarthi Bhavan, steaming Idli Vada with Filter Coffee at Brahmin's Coffee Bar, and craft brews at microbreweries."
        else:
            dest = city_display if city_display else "your destination"
            return f"For **{dest}**, we recommend trying the signature regional delicacies, visiting highly-rated heritage restaurants, and exploring bustling evening food streets."

    # 4. Weather & Best Time to Visit
    if any(re.search(rf"\b{w}\b", q) for w in ["weather", "temperature", "rain", "snow", "monsoon", "climate", "season", "best time to visit", "best month", "when to go"]):
        if "goa" in q or (city_display and city_display.lower() == "goa"):
            return "Goa has a tropical climate. The **best time to visit is mid-November to February** for pleasant sunny beach weather (20°C–32°C). June to September brings lush green monsoons and peaceful stays."
        elif "del" in q or "delhi" in q or (city_display and city_display.lower() == "delhi"):
            return "Delhi experiences hot summers (April–June, up to 45°C) and crisp winters (December–January, 5°C–20°C). The **best time to visit is October to March** for pleasant sightseeing."
        elif "bom" in q or "mumbai" in q or (city_display and city_display.lower() == "mumbai"):
            return "Mumbai is warm and coastal year-round. The **best time to visit is October to March** with comfortable evenings. Heavy monsoons occur from June to September."
        elif "blr" in q or "bangalore" in q or (city_display and city_display.lower() == "bangalore"):
            return "Bangalore enjoys pleasant, moderate weather year-round (18°C–30°C). September to March offers especially crisp and comfortable weather for outdoor exploring."
        else:
            dest = city_display if city_display else "your destination"
            return f"The best time to visit **{dest}** is typically during the cooler dry months (October through March), which offer ideal temperatures for sightseeing and outdoor tours."

    # 5. Packing & What to Wear
    if any(re.search(rf"\b{w}\b", q) for w in ["pack", "packing", "what to wear", "clothes", "dress code"]):
        return "Essential packing tips:\n- Lightweight, breathable cotton clothes and comfortable walking shoes.\n- Sunscreen (SPF 30+), UV sunglasses, and a hat.\n- Power bank, charging adapters, and personal medications.\n- Modest attire (covering shoulders and knees) when visiting temples and spiritual heritage sites."

    # 6. Budget & Estimated Costs
    if any(re.search(rf"\b{w}\b", q) for w in ["budget", "cost", "how much", "price", "expensive", "cheap", "estimate"]):
        return "Typical trip budgets per person (excluding flights & hotels):\n- **Budget:** ₹1,500 – ₹2,500/day (local transit, street food, standard entry fees)\n- **Mid-Range / Comfort:** ₹3,500 – ₹5,500/day (cabs, top restaurants, guided activities)\n- **Luxury:** ₹8,000+/day (private chauffeur, fine dining, private tours)"

    # 7. Visa / Passport
    if any(re.search(rf"\b{w}\b", q) for w in ["visa", "passport", "entry permit"]):
        return "Visa requirements depend on your nationality and destination. Most international trips require a passport valid for at least 6 months from travel date and a valid tourist visa or eVisa."

    # 8. Luggage / Baggage allowance
    if any(re.search(rf"\b{w}\b", q) for w in ["luggage", "baggage", "bag", "carry on", "cabin"]):
        return "Standard flight baggage allowances:\n- **Domestic flights:** Usually 15 kg checked baggage + 7 kg cabin bag per passenger.\n- **International flights:** Typically 20–30 kg checked baggage + 7–10 kg cabin bag."

    # 9. Off-topic Decline (Only strictly non-travel queries)
    travel_keywords = [
        "flight", "hotel", "itinerary", "itineary", "stay", "travel", "ticket", "book", "reserve", "destination",
        "place", "visit", "eat", "food", "weather", "temperature", "visa", "passport", "luggage", "baggage",
        "airline", "airport", "budget", "room", "guest", "trip", "tour", "attraction", "things to do", "pack",
        "packing", "city", "goa", "delhi", "mumbai", "bangalore", "paris", "london", "dubai", "jaipur"
    ]
    if not any(re.search(rf"\b{w}\b", q) for w in travel_keywords) and not any(re.search(rf"\b{w}\b", q) for w in ["hi", "hello", "thanks"]):
        return "I'm sorry, but I can only assist with travel-related queries such as flight bookings, hotel reservations, and itinerary planning. Please ask a travel-related question."

    # Generic Travel Helper Response
    return f"I can help with flight options, hotel bookings, custom itineraries, and local destination tips for {city_display if city_display else 'your destination'}. Please let me know how you'd like to proceed!"
