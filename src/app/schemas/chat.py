from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any

class TaskRequest(BaseModel):
    task_id: str
    task_type: Literal["flight_search", "hotel_search"]
    session_id: str
    parameters: dict
    metadata: dict = Field(default_factory=dict) # {requested_by, timestamp}

class TaskResponse(BaseModel):
    task_id: str
    status: Literal["success", "partial", "failed", "needs_clarification"]
    results: List[dict] = Field(default_factory=list)
    clarification_needed: Optional[str] = None
    error: Optional[str] = None
    metadata: dict = Field(default_factory=dict) # {agent_id, timestamp}

class ChatRequest(BaseModel):
    message: str
    session_id: str

class PaymentDetails(BaseModel):
    order_id: str
    amount: int  # in paise
    amount_rupees: float
    currency: str = "INR"
    key_id: str
    item_name: str
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None

class UpsellDetails(BaseModel):
    offer_id: str
    title: str
    description: str
    price_rupees: float
    order_id: Optional[str] = None
    key_id: Optional[str] = None
    category: str  # "insurance", "transfer", "hotel_upgrade"

class ChatResponse(BaseModel):
    message: str
    options: List[dict] = Field(default_factory=list)
    clarification_needed: bool = False
    quick_replies: List[str] = Field(default_factory=list)
    ticket: Optional[dict] = None
    followup_message: Optional[str] = None
    followup_quick_replies: List[str] = Field(default_factory=list)
    current_flow: Optional[str] = None
    payment_details: Optional[PaymentDetails] = None
    upsell_details: Optional[UpsellDetails] = None

class PaymentOrderRequest(BaseModel):
    session_id: str
    booking_type: Optional[str] = "flight"

class PaymentVerifyRequest(BaseModel):
    session_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    is_upsell: bool = False
    upsell_type: Optional[str] = None

class PaymentFailureRequest(BaseModel):
    session_id: str
    order_id: str
    error_description: str
    error_code: Optional[str] = None

class MCPExecuteRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    agent_id: Optional[str] = "mcp_buyer_agent"
