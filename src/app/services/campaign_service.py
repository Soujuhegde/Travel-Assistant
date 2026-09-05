import asyncio
from typing import Dict, Any, List
from app.services.audit_service import audit_service
from app.services.email_service import email_service

class CampaignService:
    def __init__(self):
        pass

    async def check_and_recover_abandoned_sessions(self, sessions_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Detects sessions stalled at the payment step without completion,
        and triggers a bounded recovery email via Brevo.
        """
        recovered = []
        payment_steps = [
            "awaiting_payment", "flight_awaiting_payment", "flight_summary",
            "hotel_summary", "hotel_awaiting_payment"
        ]

        for session_id, state in sessions_dict.items():
            current_step = state.get("current_step")
            is_confirmed = current_step in ["booking_confirmed", "hotel_booking_confirmed"]
            already_sent = state.get("abandonment_email_sent", False)
            
            if current_step in payment_steps and not is_confirmed and not already_sent:
                # Find customer email and name
                pax_list = state.get("passengers_details") or []
                if not pax_list and state.get("passenger_details"):
                    pax_list = [state.get("passenger_details")]
                
                selected_hotel = state.get("selected_hotel") or {}
                customer_email = None
                customer_name = "Traveler"
                
                if pax_list and pax_list[0].get("email"):
                    customer_email = pax_list[0].get("email")
                    customer_name = pax_list[0].get("name", "Traveler")
                elif selected_hotel.get("guest_email"):
                    customer_email = selected_hotel.get("guest_email")
                    customer_name = selected_hotel.get("guest_name", "Traveler")

                if customer_email:
                    # Log abandonment detection
                    audit_service.log_event(
                        event_type="ABANDONMENT_DETECTED",
                        session_id=session_id,
                        actor="campaign_orchestrator",
                        payload={
                            "current_step": current_step,
                            "customer_email": customer_email,
                            "customer_name": customer_name
                        },
                        status="pending"
                    )

                    # Send recovery email
                    booking_info = "your flight" if not current_step.startswith("hotel_") else "your hotel reservation"
                    subject = f"Complete your booking for {booking_info} with Sara AI"
                    html_content = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                        <h2 style="color: #2563eb;">Hey {customer_name}, your trip is waiting!</h2>
                        <p>We noticed you started reserving {booking_info} but didn't get a chance to complete the payment.</p>
                        <p>Your seats and dates are temporarily reserved. You can easily complete your booking anytime.</p>
                        <div style="margin: 25px 0;">
                            <a href="http://localhost:5173/?session_id={session_id}" style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                                Complete Booking Now &rarr;
                            </a>
                        </div>
                        <p style="color: #666; font-size: 13px;">If you have any questions or need to change dates, simply reply to Sara in the chat!</p>
                    </div>
                    """
                    
                    try:
                        asyncio.create_task(email_service.send_email(customer_email, subject, html_content))
                        state["abandonment_email_sent"] = True
                        
                        audit_service.log_event(
                            event_type="ABANDONMENT_EMAIL_SENT",
                            session_id=session_id,
                            actor="campaign_orchestrator",
                            payload={
                                "customer_email": customer_email,
                                "subject": subject
                            },
                            status="success"
                        )
                        recovered.append({
                            "session_id": session_id,
                            "customer_email": customer_email,
                            "status": "email_triggered"
                        })
                    except Exception as e:
                        print(f"Error sending abandonment email to {customer_email}: {e}")

        return recovered

campaign_service = CampaignService()
