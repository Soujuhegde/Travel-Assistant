import os
import re
from typing import TypedDict, Annotated, Literal, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.orchestrator.nlu_parser import parse_intent, llm
from app.orchestrator.flight_flow import flight_node, get_flight_contextual_reminder, handle_flight_clarification
from app.orchestrator.hotel_flow import hotel_node, get_hotel_contextual_reminder, handle_hotel_clarification
from app.orchestrator.itinerary_flow import get_itinerary_contextual_reminder, handle_itinerary_clarification

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
                
            interruption_answer = data.get("answer", "").strip() + "\n\n"
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
                interruption_answer = response.content.strip() + "\n\n"
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
            qa_prompt = f"""You are a specialized travel assistant chatbot designed to handle travel-related queries.
You should assist the user with any question related to travel, destinations, weather, sightseeing, culture, local food, hotels, flights, and itineraries.

Guidelines:
1. Destination Information: If the user asks about a city/place (e.g., "How is Mumbai?", "how is the weather in mumbai", "best time to visit", "what to eat"), this is fully in-scope.
2. Conciseness: Keep your response extremely brief, short, and focused. Limit your response strictly to a maximum of 2 sentences (or 2 lines). Do not write essays, bulleted lists, or excessive details.
3. Out-of-Scope: Only decline questions that are completely unrelated to travel or destinations (e.g., coding, math, general science, personal advice). If and only if the question is completely unrelated to travel, respond exactly with: "I'm sorry, but I can only assist with travel-related queries such as flight bookings, hotel reservations, and itinerary planning. Please ask a travel-related question."
"""
            msgs = [SystemMessage(content=qa_prompt)] + [m if hasattr(m, 'content') else HumanMessage(content=get_msg_content(m)) for m in state["messages"][-2:]]
            try:
                response = llm.invoke(msgs)
                msg = response.content
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
    city_display = city
    if city_clean == "DEL":
        city_display = "Delhi"
    elif city_clean == "BOM":
        city_display = "Mumbai"
    elif city_clean == "GOI":
        city_display = "Goa"
    elif city_clean == "BLR":
        city_display = "Bangalore"
    elif city_clean == "CDG":
        city_display = "Paris"
    elif city_clean == "LHR":
        city_display = "London"
        
    # Standard Greetings with exact word boundaries
    if any(re.search(rf"\b{w}\b", q) for w in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]):
        return f"Hello! 😊 I'm here to help you with your travel queries. Shall we continue with your booking?"
    if any(re.search(rf"\b{w}\b", q) for w in ["thanks", "thank you", "awesome", "perfect", "ok", "okay", "sure"]):
        return f"You're very welcome! Please let me know if you need any other travel tips or if we should proceed with your booking."
    if "how are you" in q or "how's it going" in q:
        return f"I'm doing great, thank you for asking! Let me know if you need any help with your trip."

    # 1. Attractions/Must visit places
    if any(re.search(rf"\b{w}\b", q) for w in ["place", "visit", "attraction", "things to do", "sightsee", "explore"]):
        if "del" in q or "delhi" in q or (city_display and city_display.lower() == "delhi"):
            return "Must-visit places in Delhi include the majestic Red Fort, Qutub Minar, India Gate, Lotus Temple, and the bustling streets of Chandni Chowk."
        elif "bom" in q or "mumbai" in q or (city_display and city_display.lower() == "mumbai"):
            return "In Mumbai, don't miss the Gateway of India, Marine Drive (Queen's Necklace), Chhatrapati Shivaji Terminus, and the lively Juhu Beach."
        elif "goa" in q or (city_display and city_display.lower() == "goa"):
            return "Key attractions in Goa include Baga Beach, Calangute Beach, Fort Aguada, Basilica of Bom Jesus, and Dudhsagar Falls."
        elif "blr" in q or "bangalore" in q or (city_display and city_display.lower() == "bangalore"):
            return "In Bangalore, visit the beautiful Bangalore Palace, Lalbagh Botanical Garden, Cubbon Park, and the Tipu Sultan's Summer Palace."
        elif "par" in q or "cdg" in q or "paris" in q or (city_display and city_display.lower() == "paris"):
            return "In Paris, the highlights are the iconic Eiffel Tower, Louvre Museum, Notre-Dame Cathedral, Arc de Triomphe, and a Seine River Cruise."
        elif "lon" in q or "lhr" in q or "london" in q or (city_display and city_display.lower() == "london"):
            return "When in London, check out the Tower of London, British Museum, London Eye, Buckingham Palace, and Big Ben."
        else:
            dest = city_display if city_display else "your destination"
            return f"Some of the best things to do in {dest} include exploring the central historic landmarks, visiting local museums, and walking through cultural food markets."

    # 2. Food & Dining
    if any(re.search(rf"\b{w}\b", q) for w in ["eat", "food", "dish", "cuisine", "restaurant", "culinary", "delicacy"]):
        if "del" in q or "delhi" in q or (city_display and city_display.lower() == "delhi"):
            return "Delhi is famous for its street food like Chole Bhature, Golgappas, Butter Chicken, and kebabs in Old Delhi."
        elif "bom" in q or "mumbai" in q or (city_display and city_display.lower() == "mumbai"):
            return "Famous foods in Mumbai include Vada Pav, Pav Bhaji, Bhel Puri, and coastal seafood specialties like Bombay Duck fry."
        elif "goa" in q or (city_display and city_display.lower() == "goa"):
            return "In Goa, try the traditional Goan Fish Curry, Pork Vindaloo, Bebinca (dessert), and fresh butter garlic prawns at beach shacks."
        else:
            dest = city_display if city_display else "your destination"
            return f"For {dest}, we recommend trying the signature local street foods, visiting top-rated traditional bistros, and sampling seasonal desserts."

    # 3. Weather
    if any(re.search(rf"\b{w}\b", q) for w in ["weather", "temperature", "rain", "snow", "climate", "season", "best time to visit"]):
        if "goa" in q or (city_display and city_display.lower() == "goa"):
            return "Goa has warm tropical weather year-round. The best time to visit is from November to February for pleasant weather and beach activities."
        elif "del" in q or "delhi" in q or (city_display and city_display.lower() == "delhi"):
            return "Delhi has extreme climates: hot summers (April-June) and chilly winters (December-January). October to March is the ideal tourist window."
        elif "bom" in q or "mumbai" in q or (city_display and city_display.lower() == "mumbai"):
            return "Mumbai is warm and humid year-round, with heavy monsoons from June to September. October to March is the best time to visit."
        else:
            dest = city_display if city_display else "your destination"
            return f"The weather in {dest} varies by season. It is generally recommended to visit during the mild shoulder seasons for sightseeing comfort."

    # 4. Visa / Passport
    if any(re.search(rf"\b{w}\b", q) for w in ["visa", "passport", "entry permit"]):
        return "Visa requirements vary by nationality. Most international destinations require a passport valid for at least 6 months and a tourist visa or eVisa."

    # 5. Luggage / Baggage allowance
    if any(re.search(rf"\b{w}\b", q) for w in ["luggage", "baggage", "bag", "carry on", "cabin"]):
        return "Standard domestic flights usually allow 15kg of checked baggage and 7kg of cabin luggage. International flights typically offer 20-30kg checked allowance."

    # 6. Off-topic Decline
    travel_keywords = [
        "flight", "hotel", "itinerary", "stay", "travel", "ticket", "book", "reserve", "destination",
        "place", "visit", "eat", "food", "weather", "temperature", "visa", "passport", "luggage", "baggage",
        "airline", "airport", "budget", "room", "guest", "trip", "tour", "attraction", "things to do"
    ]
    if not any(re.search(rf"\b{w}\b", q) for w in travel_keywords) and not any(re.search(rf"\b{w}\b", q) for w in ["hi", "hello", "thanks"]):
        return "I'm sorry, but I can only assist with travel-related queries such as flight bookings, hotel reservations, and itinerary planning. Please ask a travel-related question."

    # Generic Travel Helper Response
    return f"I can help with flight options, hotel bookings, itineraries, and local tips for {city_display if city_display else 'your destination'}. Please let me know how you'd like to proceed!"
