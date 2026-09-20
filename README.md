# ✈️ Sara — AI Travel & Booking Assistant

Sara is an AI-powered travel assistant that helps users **search flights and hotels, plan personalized itineraries, and complete booking workflows through natural language**.

The system combines **LLM-based intent parsing, LangGraph agent workflows, live travel search APIs, payment verification, email confirmations, and a React frontend** into an end-to-end travel booking application.


## 📌 What Sara Can Do

### Travel Search

* Search live flight options using **Google Flights via SerpAPI**
* Search hotels using **Google Hotels via SerpAPI**
* Filter and compare available options
* Handle natural-language requests such as:

  * "Find the cheapest flight"
  * "Show hotels in Goa"
  * "Show the IndiGo flight"
  * "Suggest hotels for next weekend"

### Booking Workflows

* Stateful flight and hotel booking flows
* Collect and validate required booking information
* Handle changes to existing booking selections
* Maintain conversation state throughout the booking process
* Generate booking summaries before confirmation

### AI Travel Planning

* Generate personalized day-by-day itineraries
* Include activities, transportation, meals, packing suggestions, and emergency guidance
* Understand natural-language travel requests and relative dates

### Booking & Confirmation

* Razorpay-based payment workflow
* Payment signature/webhook verification
* Generate digital flight tickets and hotel vouchers
* Send booking confirmations through **Brevo SMTP**
* Download generated tickets locally

### Reliability & Guardrails

* Validate travel dates and email addresses
* Resolve relative dates such as "tomorrow", "3 nights", and "next week"
* Handle interruptions during active booking flows
* Prevent unrelated queries from taking over the travel workflow
* Use Pydantic schemas for structured data validation
* Fall back to local mock data when external search services are unavailable
* Cache SerpAPI responses to reduce duplicate requests and API quota usage


# 🏗️ Architecture

Sara follows a **multi-agent architecture** with a conversational orchestrator coordinating specialized travel agents.

```text
                         ┌──────────────────────┐
                         │     React Frontend   │
                         │  Vite + Tailwind CSS │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    FastAPI Gateway   │
                         │      Port 8000       │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │  Orchestrator Agent  │
                         │      LangGraph       │
                         │                      │
                         │ • Intent parsing     │
                         │ • State management   │
                         │ • Routing            │
                         │ • Interruptions      │
                         └───────┬───────┬──────┘
                                 │       │
                    A2A TaskRequest     A2A TaskRequest
                                 │       │
                    ┌────────────┘       └────────────┐
                    ▼                                  ▼
          ┌──────────────────┐              ┌──────────────────┐
          │   Flight Agent   │              │    Hotel Agent   │
          │    LangGraph     │              │    LangGraph     │
          └────────┬─────────┘              └────────┬─────────┘
                   │                                  │
                   ▼                                  ▼
          ┌──────────────────┐              ┌──────────────────┐
          │  Google Flights  │              │   Google Hotels  │
          │     SerpAPI      │              │      SerpAPI     │
          └──────────────────┘              └──────────────────┘

                    Additional Services
                  ┌────────────┬────────────┐
                  ▼            ▼            ▼
              Payment       Email        Database
              Razorpay      Brevo        Persistence
```

# 🤖 Multi-Agent Workflow

The system separates conversational orchestration from domain-specific travel operations.

### 1. Orchestrator Agent

The orchestrator is the main conversational entry point.

It handles:

* Natural-language understanding
* Intent extraction
* Conversation state
* Booking step management
* User interruptions
* Routing requests to specialized agents
* Returning structured results to the frontend

The orchestrator uses **LangGraph StateGraph** workflows to maintain state across multiple turns.

### 2. Flight Agent

The Flight Agent handles flight-specific operations:

```text
User Request
     ↓
Validate Input
     ↓
Search Flights
     ↓
Filter / Format Results
     ↓
Return Structured Response
```

It retrieves flight information through SerpAPI and can fall back to local data when necessary.

### 3. Hotel Agent

The Hotel Agent follows a similar workflow:

```text
User Request
     ↓
Validate Input
     ↓
Search Hotels
     ↓
Filter / Format Results
     ↓
Return Structured Response
```

### 4. Agent-to-Agent Communication

The orchestrator communicates with specialized agents using structured **A2A TaskRequest / TaskResponse** messages.

This keeps the domain agents independent from the conversational interface.

# 🧠 Natural Language Understanding

Sara uses LLM-based parsing to convert conversational requests into structured information.

For example:

```text
"Book me a flight from Bangalore to Dubai
tomorrow for two people"
```

can be interpreted into structured information such as:

```text
origin      → Bangalore
destination → Dubai
date        → resolved departure date
passengers  → 2
intent      → flight booking
```

The parsed information is validated before entering the appropriate LangGraph workflow.

# 🔄 Stateful Conversations

Booking workflows require information to be collected across multiple messages.

Sara maintains separate state models for:

* `FlightState`
* `HotelState`
* `CommonState`
* `ConversationState`

This allows the application to maintain information such as:

* Origin and destination
* Travel dates
* Passenger information
* Selected flight
* Hotel city
* Check-in/check-out dates
* Selected hotel
* Current booking step
* Conversation history
* Active interruptions

This prevents the system from treating every message as an independent request.

# ⚡ SerpAPI Caching

Live travel search APIs can generate repeated requests during a conversation.

Sara includes a local caching layer that:

* Normalizes search parameters
* Removes session-specific parameters
* Hashes equivalent queries
* Stores responses locally
* Uses a configurable TTL
* Reuses cached responses when possible

Default cache location:

```text
.cache/serpapi/
```

Default TTL:

```text
1 hour
```

# 💳 Payment & Booking

Sara includes a payment workflow using Razorpay.

```text
Select Travel Option
        ↓
Review Booking
        ↓
Create Payment Order
        ↓
Complete Payment
        ↓
Verify Payment Signature / Webhook
        ↓
Confirm Booking
        ↓
Generate Ticket / Voucher
        ↓
Send Confirmation Email
```

The backend performs payment verification before completing the booking workflow.

# 📧 Email Confirmations

After successful booking confirmation, Sara uses **Brevo SMTP** to send transactional confirmation emails.

The confirmation can include:

* Booking information
* Passenger/guest details
* Flight or hotel details
* Confirmation information
* Generated ticket/voucher

# 🎫 Digital Tickets & Vouchers

The application generates digital travel documents after booking.

### Flight

Includes information such as:

* Passenger details
* PNR
* Seat
* Gate
* Flight information
* Barcode

### Hotel

Includes:

* Guest details
* Hotel information
* Check-in/check-out dates
* Booking information

Generated documents can be downloaded locally from the frontend.

# 🛡️ Guardrails & Validation

### Date Validation

Rejects invalid or past travel dates.

It also understands relative inputs such as:

```text
tomorrow
next week
3 nights
one week
```

### Schema Validation

Pydantic models validate structured requests and responses before they move through the application.

### Booking State Protection

The application maintains the current booking state and redirects users back to the active workflow after interruptions.

### Out-of-Scope Protection

Non-travel requests are prevented from taking over the travel assistant workflow.

### External API Fallback

If live travel APIs fail or time out, the application can use local mock data so the workflow remains testable.

# 🛠️ Technology Stack

| Layer                  | Technologies                          |
| ---------------------- | ------------------------------------- |
| Frontend               | React, Vite, Tailwind CSS             |
| Backend                | Python, FastAPI                       |
| Agent Orchestration    | LangGraph                             |
| LLM / NLU              | Groq, Llama models                    |
| Travel Search          | SerpAPI Google Flights, Google Hotels |
| Validation             | Pydantic                              |
| Database / Persistence | SQLite / application persistence      |
| Agent Communication    | A2A TaskRequest / TaskResponse        |
| Payments               | Razorpay                              |
| Email                  | Brevo SMTP                            |
| HTTP Client            | Axios                                 |
| Testing                | Pytest                                |
| Caching                | Local SerpAPI disk cache              |

# 📂 Project Structure

```text
travel-chatbot/
│
├── frontend/
│   └── react-app/
│       ├── src/
│       │   ├── components/
│       ├── App.jsx
│       ├── main.jsx
│       └── index.css
│       ├── tailwind.config.js
│       └── package.json
│
├── src/
│   └── app/
│       ├── agents/
│       │   ├── flight_agent.py
│       │   └── hotel_agent.py
│       │
│       ├── api/
│       │   └── routes.py
│       │
│       ├── db/
│       │   ├── checkpointer.py
│       │   └── database.py
│       │
│       ├── orchestrator/
│       │   ├── graph.py
│       │   ├── nlu_parser.py
│       │   ├── flight_flow.py
│       │   ├── hotel_flow.py
│       │   └── itinerary_flow.py
│       │
│       ├── schemas/
│       │   ├── chat.py
│       │   └── state.py
│       │
│       ├── services/
│       │   ├── audit_service.py
│       │   ├── campaign_service.py
│       │   ├── email_service.py
│       │   └── payment_service.py
│       │
│       ├── utils/
│       │   ├── cache.py
│       │   └── mock_data.py
│       │
│       └── main.py
│
├── .env.example
├── requirements.txt
└── README.md
```

# ⚙️ Quick Setup

## Prerequisites

Make sure you have:

* Python 3.10+
* Node.js 18+
* npm
* Git

You will also need API keys for:

* Groq
* SerpAPI
* 
## 1. Clone the Repository

```bash
git clone https://github.com/Soujuhegde/Travel-Assistant.git

cd Travel-Assistant
```

## 2. Backend Setup

Create a virtual environment:

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### macOS / Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 3. Configure Environment Variables

Create your environment file:

```bash
cp .env.example .env
```

On Windows, you can also create `.env` manually by copying `.env.example`.

Add your API credentials:

```env
GROQ_API_KEY=your_groq_api_key
SERPAPI_API_KEY=your_serpapi_api_key
```

## 4. Start the Backend

From the project root:

```bash
python src/app/main.py
```

The FastAPI backend will run at:

```text
http://localhost:8000
```

## 5. Start the Frontend

Open another terminal:

```bash
cd frontend/react-app
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

The frontend will normally be available at:

```text
http://localhost:5173
```

Open the displayed URL in your browser.

# 👤 Author

**Soujanya S P**

AI Engineer | Generative AI | Agentic AI

* GitHub: https://github.com/Soujuhegde
* LinkedIn: https://www.linkedin.com/in/soujanyasp02
