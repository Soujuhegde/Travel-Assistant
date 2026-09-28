from datetime import datetime
from typing import Dict, Any
from langchain_core.messages import SystemMessage
from app.orchestrator.nlu_parser import llm
from app.config import settings
from app.utils.cleaner import clean_travel_response

def get_itinerary_contextual_reminder(step: str, state: Dict[str, Any]) -> str | None:
    hotel_params = state.get("hotel_params") or {}
    flight_params = state.get("flight_params") or {}

    if step == "itinerary_awaiting_city":
        return "Which city or destination would you like me to plan the itinerary for?"
    elif step == "itinerary_awaiting_start_date":
        city = hotel_params.get("city") or flight_params.get("destination") or "your destination"
        return f"When are you planning to start your trip to {city}?"
    elif step == "itinerary_awaiting_days":
        return "For how many days would you like me to plan the itinerary?"
    return None

def handle_itinerary_clarification(step: str, state: Dict[str, Any]) -> Dict[str, Any]:
    msg = ""
    replies = []
    options = []
    
    hotel_params = state.get("hotel_params") or {}
    flight_params = state.get("flight_params") or {}
    selected_flight = state.get("selected_flight") or {}
    selected_hotel = state.get("selected_hotel") or {}

    if step == "itinerary_awaiting_city":
        clarification = state.get("pending_clarification")
        prefix = f"{clarification}\n\n" if clarification else ""
        msg = f"{prefix}Hi! I'm Sara, your AI travel companion. I'd love to plan a custom itinerary for you! Which city or destination are you planning to visit?"
        
    elif step == "itinerary_awaiting_start_date":
        city = hotel_params.get("city", "your destination")
        clarification = state.get("pending_clarification")
        prefix = f"{clarification}\n\n" if clarification else ""
        msg = f"{prefix}Great choice! 🌍 When are you planning to start your trip to **{city}**? (e.g. 2025-08-15 or 'next Monday')"
        replies = ["Today", "Tomorrow"]
        
    elif step == "itinerary_awaiting_days":
        days = 0
        check_in = hotel_params.get("check_in_date") or flight_params.get("departure_date")
        check_out = hotel_params.get("check_out_date")
        if check_in and check_out:
            try:
                d1 = datetime.strptime(check_in, "%Y-%m-%d")
                d2 = datetime.strptime(check_out, "%Y-%m-%d")
                days = (d2 - d1).days
            except:
                pass
                
        clarification = state.get("pending_clarification")
        prefix = f"{clarification}\n\n" if clarification else ""
        city = hotel_params.get("city") or flight_params.get("destination", "your destination")
        msg = f"{prefix}Perfect! 🗓️ How many days would you like me to plan the itinerary for **{city}**?"
        
        replies = ["3 Days", "5 Days", "7 Days"]
        if days > 0 and str(days) not in ["3", "5", "7"]:
            replies.append(f"{days} Days")
            
    elif step == "plan_itinerary":
        city = hotel_params.get("city") or flight_params.get("destination") or "your destination"
        itinerary_days = hotel_params.get("itinerary_days", 3)
        check_in = hotel_params.get("check_in_date") or flight_params.get("departure_date") or "today"
        hotel_name = selected_hotel.get("name", "")
        airline_name = selected_flight.get("airline_name", "")
        guests = hotel_params.get("guests", "1 Adult")

        itinerary_prompt = f"""You are a world-class luxury travel planner with deep expertise in {city}. 
Create an EXTREMELY DETAILED, immersive, and practical day-by-day travel itinerary.

Trip Details:
- 🌍 Destination: {city}
- 📅 Duration: {itinerary_days} days (starting {check_in})
- 🏨 Accommodation: {hotel_name if hotel_name else "To be decided"}
- ✈️ Flight: {airline_name if airline_name else "To be arranged"}
- 👥 Travellers: {guests}

STRICT OUTPUT FORMAT — Follow this clean markdown structure for EVERY SINGLE DAY:

### 🌟 Day [N]: [Catchy Theme Title]
**📅 Date:** [Starting date + N-1 days]

**🌅 Morning (8:00 AM – 12:00 PM)**
- 🍳 **Breakfast:** [Restaurant name] — [Must-try dish] (Approx. ₹[Cost])
- 🏛️ **Sightseeing:** [Specific attraction/monument] — [What to explore, highlights, insider tip, duration]
- 🗺️ **Excursion:** [Specific spot/activity] — [Key details and entry info]
- 🚗 **Transport:** [Transport mode, approx cost, travel time]

**☀️ Afternoon (12:00 PM – 6:00 PM)**
- 🍽️ **Lunch:** [Restaurant name] — [Signature dish and price range]
- 🎭 **Experience:** [Cultural activity, museum, or landmark] — [What makes it special]
- 🛍️ **Shopping & Leisure:** [Market or street name] — [What to buy and local specialties]
- 🚗 **Transport:** [Transport to evening spot]

**🌙 Evening (6:00 PM – 10:00 PM)**
- 🌆 **Sunset & Views:** [Best viewpoint or promenade]
- 🍷 **Dinner:** [Restaurant name] — [Cuisine type, atmosphere, recommended dishes]
- 🎵 **Nightlife & Leisure:** [Night market, cafe, live music, or cultural show]

**💡 Local Tips:**
- [Practical insider tip 1 — dress code, timing, or local etiquette]
- [Practical insider tip 2 — photography spots, hidden gems]

**💰 Estimated Daily Budget:** ₹[X,XXX] – ₹[X,XXX] per person (excluding hotel)

---

### 🎒 Packing Tips
- [Item 1]
- [Item 2]
- [Item 3]

### 📋 Essential Info
- **Emergency Numbers:** 112 (All-in-one Emergency Helpline)
- **Currency:** Indian Rupee (INR ₹)
- **Best Apps:** Google Maps, Uber / Ola, Zomato

CRITICAL FORMATTING RULES:
1. Generate ALL {itinerary_days} days with full detail.
2. Name REAL, specific places and restaurants in {city}.
3. DO NOT wrap the output in code blocks (no ``` or ```markdown). Output pure, readable text only.
4. DO NOT use markdown tables (no |---|---|). Use clean bullet points instead.
5. DO NOT use HTML tags (no <ul>, <li>, <br>, <table>).
6. DO NOT use bracket placeholders like '[Activity 1]'. Use natural travel text.
7. Include rich emojis for readability."""

        try:
            from langchain_groq import ChatGroq
            # Use the configured model with explicit API key
            itinerary_llm = ChatGroq(model=settings.LLM_MODEL, temperature=0.4, max_tokens=4096, api_key=settings.GROQ_API_KEY)
            response = itinerary_llm.invoke([SystemMessage(content=itinerary_prompt)])
            msg = clean_travel_response(response.content)
        except Exception as e:
            print(f"Itinerary LLM call failed: {e}. Falling back to default LLM.")
            try:
                if llm:
                    response = llm.invoke([SystemMessage(content=itinerary_prompt)])
                    msg = clean_travel_response(response.content)
                else:
                    raise ValueError("Default LLM is not configured")
            except Exception as ex:
                print(f"Default LLM call also failed: {ex}. Using local rule-based itinerary fallback generator.")
                msg = generate_fallback_itinerary(city, itinerary_days, check_in, hotel_name, airline_name, guests)
                
        replies = ["Book a Flight", "Book a Hotel", "Plan an Itinerary"]

    return {"final_response": msg, "quick_replies": replies, "options_to_show": options}

def generate_fallback_itinerary(city: str, itinerary_days: int, check_in: str, hotel_name: str, airline_name: str, guests: str) -> str:
    from datetime import datetime, timedelta
    
    # Try to parse start date
    try:
        start_dt = datetime.strptime(check_in, "%Y-%m-%d")
    except:
        start_dt = datetime.now()
        
    lines = []
    lines.append(f"# 🗺️ Custom Itinerary for {city.upper()}")
    lines.append("")
    lines.append("Here is your curated travel plan:")
    lines.append("")
    lines.append(f"**Trip Details:**")
    lines.append(f"- 🌍 **Destination:** {city}")
    lines.append(f"- 📅 **Duration:** {itinerary_days} days")
    lines.append(f"- 🏨 **Accommodation:** {hotel_name if hotel_name else 'To be decided'}")
    lines.append(f"- ✈️ **Flight:** {airline_name if airline_name else 'To be arranged'}")
    lines.append(f"- 👥 **Travellers:** {guests}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Curated, engaging activities mapping for popular cities
    activities_by_city = {
        "GOA": [
            ("North Goa Beach Culture & Coastal Forts", "Breakfast at Infantaria Café (Calangute, ₹300)", "Visit historic Fort Aguada and lighthouse overlooking the Arabian Sea", "Relax at Candolim and Baga beach shacks with water sports", "Scooter / Taxi rental (₹500/day)"),
            ("Old Goa Heritage & Latin Quarter Romance", "Breakfast at Viva Panjim (Fontainhas, ₹350)", "Explore Basilica of Bom Jesus and Se Cathedral in Old Goa", "Heritage walking tour through the colorful Portuguese quarter of Fontainhas", "Cab ride to Panjim (₹400, 30 mins)"),
            ("South Goa Serenity & Scenic Waterfalls", "Breakfast at Dropadi Restaurant (Palolem, ₹400)", "Day trip to the magnificent Dudhsagar Falls", "Sunset beach relaxation at Palolem Beach and butterfly island boat ride", "Private taxi hire (₹2,000 full day)"),
        ],
        "GOI": [
            ("North Goa Beach Culture & Coastal Forts", "Breakfast at Infantaria Café (Calangute, ₹300)", "Visit historic Fort Aguada and lighthouse overlooking the Arabian Sea", "Relax at Candolim and Baga beach shacks with water sports", "Scooter / Taxi rental (₹500/day)"),
            ("Old Goa Heritage & Latin Quarter Romance", "Breakfast at Viva Panjim (Fontainhas, ₹350)", "Explore Basilica of Bom Jesus and Se Cathedral in Old Goa", "Heritage walking tour through the colorful Portuguese quarter of Fontainhas", "Cab ride to Panjim (₹400, 30 mins)"),
            ("South Goa Serenity & Scenic Waterfalls", "Breakfast at Dropadi Restaurant (Palolem, ₹400)", "Day trip to the magnificent Dudhsagar Falls", "Sunset beach relaxation at Palolem Beach and butterfly island boat ride", "Private taxi hire (₹2,000 full day)"),
        ],
        "DEL": [
            ("Historical Splendors of Old Delhi", "Breakfast at Karim's (Mutton Korma & Roti, ₹350)", "Visit Red Fort (UNESCO heritage site) and Jama Masjid", "Walk through Chandni Chowk spice markets and Dariba Kalan", "Cycle rickshaw ride (₹100, 15 mins)"),
            ("New Delhi Landmarks & Lutyens Zone", "South Indian Breakfast at Saravana Bhavan (₹200)", "Explore India Gate, National War Memorial, and Rashtrapati Bhavan", "Visit Qutub Minar complex and Mehrauli Archaeological Park", "Delhi Metro ride to Rajiv Chowk (₹40, 20 mins)"),
            ("Cultural Temples & Spiritual Walk", "Breakfast at Wenger's (Connaught Place, ₹300)", "Visit Lotus Temple and serene gardens", "Explore Akshardham Temple complex and musical fountain show", "Auto-rickshaw ride (₹120, 25 mins)"),
        ],
        "BOM": [
            ("Gateway to Mumbai Heritage Walk", "Breakfast at Café Mondegar (Keema Ghotala, ₹400)", "Visit Gateway of India and the iconic Taj Mahal Palace hotel", "Walk around Colaba Causeway and Kala Ghoda Art District", "Taxi ride (₹80, 10 mins)"),
            ("Coastal Drives & Sunset Promenades", "Breakfast at Yazdani Bakery (Bun Maska & Chai, ₹150)", "Visit Marine Drive and walk along the Queen's Necklace", "Explore Haji Ali Dargah and Bandra Bandstand", "Local train / cab ride (₹150, 25 mins)"),
            ("Artistic Passages & Ancient Caves", "Breakfast at Theobroma (Colaba, ₹250)", "Ferry excursion to Elephanta Caves (UNESCO World Heritage Site)", "Visit Jehangir Art Gallery and National Gallery of Modern Art", "Ferry ride (₹200 return)"),
        ],
        "BLR": [
            ("Garden City & Royal Heritage", "Breakfast at CTR / Shri Sagar (Benne Masala Dosa, ₹180)", "Explore Bangalore Palace and Tipu Sultan's Summer Palace", "Stroll through Lalbagh Botanical Garden and Glass House", "Namma Metro ride (₹35, 15 mins)"),
            ("Tech Hub, Art & Cultural Hubs", "Breakfast at Vidyarthi Bhavan (Gandhi Bazaar, ₹150)", "Visit National Gallery of Modern Art and Cubbon Park", "Explore Church Street bookstores and vibrant cafes", "Auto-rickshaw ride (₹90, 20 mins)"),
            ("Spiritual Tranquility & Scenic Outskirts", "Breakfast at Brahmin's Coffee Bar (Idli Vada & Filter Coffee, ₹120)", "Visit ISKCON Temple and Bull Temple in Basavanagudi", "Shopping at Commercial Street and UB City mall", "Cab ride (₹250, 30 mins)"),
        ]
    }
    
    # default activities if city is not in map
    default_activities = [
        ("Discovering Local Treasures & Historic Center", "Breakfast at a top-rated local café (Signature breakfast, ₹250)", "Visit the main historic cathedral, castle, or central square", "Stroll through the botanical garden and scenic municipal park", "Walking tour & public transit (₹50)"),
        ("Scenic Panoramas & Cultural Museums", "Breakfast at an artisan bakery (Pastry & coffee, ₹200)", "Visit the national art museum and historical exhibition center", "Enjoy panoramic sunset views from the highest city viewpoint", "Public tram / bus (₹40, 15 mins)"),
        ("Spiritual Landmarks & Artisan Markets", "Breakfast at a traditional food market (Local specialty, ₹180)", "Explore ancient temples, architectural monuments, and historic alleys", "Browse the bustling cultural handicraft and souvenir bazaar", "Taxi / Ride-share (₹150, 20 mins)")
    ]
    
    city_key = city.upper()
    city_acts = activities_by_city.get(city_key, default_activities)
    
    for i in range(itinerary_days):
        day_num = i + 1
        day_date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        theme, b_fast, act1, act2, trans = city_acts[i % len(city_acts)]
        
        lines.append(f"### 🌟 Day {day_num}: {theme}")
        lines.append(f"**📅 Date:** {day_date}")
        lines.append("")
        lines.append(f"**🌅 Morning (8:00 AM – 12:00 PM)**")
        lines.append(f"- 🍳 **Breakfast:** {b_fast}")
        lines.append(f"- 🏛️ **Sightseeing:** {act1}")
        lines.append(f"- 🗺️ **Exploration:** {act2}")
        lines.append(f"- 🚗 **Transport:** {trans}")
        lines.append("")
        lines.append(f"**☀️ Afternoon (12:00 PM – 6:00 PM)**")
        lines.append(f"- 🍽️ **Lunch:** Local Specialty Restaurant (Chef's Special, ₹350)")
        lines.append(f"- 🎭 **Experience:** Cultural monument tour & photo walk")
        lines.append(f"- 🛍️ **Shopping & Leisure:** Buying souvenirs & local handicrafts at the central market")
        lines.append(f"- 🚗 **Transport:** Ride to the evening promenade (₹80)")
        lines.append("")
        lines.append(f"**🌙 Evening (6:00 PM – 10:00 PM)**")
        lines.append(f"- 🌆 **Sunset & Views:** Golden hour viewpoint and scenic sunset walk")
        lines.append(f"- 🍷 **Dinner:** Fine Dining Bistro (Signature multi-course meal, ₹1,200)")
        lines.append(f"- 🎵 **Nightlife & Leisure:** Stroll through night market or enjoy live acoustic music")
        lines.append("")
        lines.append(f"**💡 Local Tips:**")
        lines.append(f"- Dress comfortably with lightweight footwear for walking tours.")
        lines.append(f"- Keep small local currency notes handy for markets and transport.")
        lines.append("")
        lines.append(f"**💰 Estimated Daily Budget:** ₹2,500 – ₹4,000 per person")
        lines.append("")
        lines.append("---")
        lines.append("")
        
    lines.append("### 🎒 Packing Tips")
    lines.append("- Comfortable walking sneakers, breathable cotton clothing, sunglasses, and sunscreen.")
    lines.append("- Power bank, universal adapter, and personal medication kit.")
    lines.append("- Modest attire covering shoulders and knees for heritage/spiritual sites.")
    lines.append("")
    lines.append("### 📋 Essential Info")
    lines.append("- **Emergency Numbers:** 112 (All-in-one Emergency Helpline).")
    lines.append("- **Currency:** Indian Rupee (INR ₹). UPI/Cards accepted at most stores; cash handy for local stalls.")
    lines.append("- **Best Apps:** Google Maps for transit, Uber / Ola / GoaMiles for cabs, Zomato for food reviews.")
    
    return "\n".join(lines)


