from app.schemas.chat import TaskRequest, TaskResponse
import os
import re
import httpx
import time
from typing import TypedDict, List, Dict, Any, Optional
from app.utils.cache import get_cached_response, set_cached_response
from langgraph.graph import StateGraph, START, END

# ── Sub-agent State ────────────────────────────────────────────────────────────

class HotelAgentState(TypedDict):
    task_id: str
    session_id: str
    parameters: Dict[str, Any]
    metadata: Dict[str, Any]
    status: str
    results: List[Dict[str, Any]]
    clarification_needed: Optional[str]
    error: Optional[str]
    serpapi_request_info: Optional[Dict[str, Any]]
    serpapi_response_data: Optional[Dict[str, Any]]

# ── Node 1: Input Validation ──────────────────────────────────────────────────

def validate_node(state: HotelAgentState) -> Dict[str, Any]:
    params = state.get("parameters") or {}
    if not params.get("city") or not params.get("check_in_date") or not params.get("check_out_date"):
        return {
            "status": "needs_clarification",
            "clarification_needed": "I need the city, check-in date, and check-out date to search for hotels."
        }
    return {"status": "success"}

# ── Node 2: Search / Retrieval ────────────────────────────────────────────────

def search_node(state: HotelAgentState) -> Dict[str, Any]:
    params = state.get("parameters") or {}

    api_key = os.getenv("SERPAPI_API_KEY")
    results = []
    serpapi_request_info = None
    serpapi_response_data = None

    if api_key:
        try:
            url = "https://serpapi.com/search.json"

            # Map common IATA codes to city names for better hotel search
            city = params.get("city", "")
            if len(city) == 3 and city.isupper():
                iata_map = {
                    "BOM": "Mumbai", "DEL": "Delhi", "BLR": "Bangalore", "SIN": "Singapore",
                    "PNQ": "Pune", "GOI": "Goa", "GOX": "Goa", "COK": "Kochi", "HYD": "Hyderabad",
                    "MAA": "Chennai", "CCU": "Kolkata", "AMD": "Ahmedabad", "JAI": "Jaipur"
                }
                city = iata_map.get(city, city)

            req_params = {
                "engine": "google_hotels",
                "q": f"hotels in {city}",
                "check_in_date": params.get("check_in_date"),
                "check_out_date": params.get("check_out_date"),
                "currency": "INR",
                "hl": "en",
                "api_key": api_key
            }

            # Map budget if specified
            budget = params.get("budget", "")
            if budget and budget != "I'll decide later":
                prices = re.findall(r"[\d,]+", budget)
                if len(prices) == 2:
                    min_p = int(prices[0].replace(",", ""))
                    max_p = int(prices[1].replace(",", ""))
                    req_params["min_price"] = min_p
                    req_params["max_price"] = max_p
                elif len(prices) == 1 and "+" in budget:
                    min_p = int(prices[0].replace(",", ""))
                    req_params["min_price"] = min_p

            serpapi_request_info = {
                "url": url,
                "params": {k: v for k, v in req_params.items() if k != "api_key"}
            }

            cached_data = get_cached_response("google_hotels", req_params)
            if cached_data:
                data = cached_data
                print(f"Retrieving hotel search results from cache for {city}")
            else:
                response = httpx.get(url, params=req_params, timeout=15.0)
                response.raise_for_status()
                data = response.json()
                set_cached_response("google_hotels", req_params, data)

            serpapi_response_data = data
            properties = data.get("properties", [])[:20]
            for p in properties:
                lowest_rate = p.get("rate_per_night", {}).get("lowest", "")
                if not lowest_rate:
                    lowest_rate = p.get("total_rate", {}).get("lowest", "")

                p_images = []
                for img in p.get("images", []):
                    img_url = img.get("url") or img.get("thumbnail")
                    if img_url:
                        p_images.append(img_url)

                if len(p_images) < 2:
                    p_images = [
                        "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=600&q=80",
                        "https://images.unsplash.com/photo-1582719508461-905c673771fd?auto=format&fit=crop&w=600&q=80"
                    ]

                star_rating = p.get("rating", 4.0)
                guest_rating = str(p.get("rating", "4.5"))

                distance = p.get("distance", "Convenient location")
                if not distance and p.get("address"):
                    distance = p.get("address")

                amenities = p.get("amenities", p.get("highlights", ["Free WiFi", "AC", "Room Service"]))
                if not amenities:
                    amenities = ["Free WiFi", "AC", "Room Service"]

                card = {
                    "name": p.get("name", "Luxury Hotel"),
                    "star_rating": int(float(star_rating)) if star_rating else 4,
                    "price_per_night": lowest_rate or "₹4,500",
                    "distance": distance,
                    "amenities": amenities[:4],
                    "guest_rating": guest_rating,
                    "images": p_images[:3],
                    "booking_url": p.get("link") or "https://booking.com"
                }
                results.append(card)

        except Exception as e:
            print(f"SerpAPI Google Hotels Error: {e}")

    # Fallback to mock data if SerpAPI fails or returns nothing
    if not results:
        from app.utils.mock_data import mock_search_hotels
        fallback = mock_search_hotels(params)
        if fallback.get("status") == "success":
            results = fallback.get("results", [])

    return {
        "results": results,
        "serpapi_request_info": serpapi_request_info,
        "serpapi_response_data": serpapi_response_data
    }

# ── Node 3: Response Formatting ───────────────────────────────────────────────

def format_node(state: HotelAgentState) -> Dict[str, Any]:
    # All formatting is handled by the flow layers above; this node is the
    # terminal pass-through required by the LangGraph sub-agent spec.
    return {}

# ── Conditional Router ─────────────────────────────────────────────────────────

def route_hotel_agent(state: HotelAgentState):
    if state.get("status") == "needs_clarification":
        return "format_node"
    return "search_node"

# ── Build & Compile Hotel Agent Sub-Graph ─────────────────────────────────────

_builder = StateGraph(HotelAgentState)
_builder.add_node("validate_node", validate_node)
_builder.add_node("search_node", search_node)
_builder.add_node("format_node", format_node)

_builder.add_edge(START, "validate_node")
_builder.add_conditional_edges("validate_node", route_hotel_agent, {
    "format_node": "format_node",
    "search_node": "search_node"
})
_builder.add_edge("search_node", "format_node")
_builder.add_edge("format_node", END)

hotel_agent_graph = _builder.compile()

# ── Public A2A Entry-point ─────────────────────────────────────────────────────

def call_hotel_agent(request: TaskRequest) -> TaskResponse:
    initial_state: HotelAgentState = {
        "task_id": request.task_id,
        "session_id": request.session_id,
        "parameters": request.parameters,
        "metadata": request.metadata,
        "status": "success",
        "results": [],
        "clarification_needed": None,
        "error": None,
        "serpapi_request_info": None,
        "serpapi_response_data": None
    }
    output = hotel_agent_graph.invoke(initial_state)

    api_key = os.getenv("SERPAPI_API_KEY")
    metadata = {
        "agent_id": "hotel_agent",
        "timestamp": time.time(),
        "source": "serpapi" if api_key and output["results"] else "mock"
    }
    if output["serpapi_request_info"]:
        metadata["serpapi_request"] = output["serpapi_request_info"]
    if output["serpapi_response_data"]:
        metadata["serpapi_response"] = output["serpapi_response_data"]

    return TaskResponse(
        task_id=output["task_id"],
        status=output.get("status", "success"),
        results=output["results"],
        clarification_needed=output["clarification_needed"],
        error=output["error"],
        metadata=metadata
    )

