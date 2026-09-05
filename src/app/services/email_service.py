import httpx
from app.config import settings

class EmailService:
    def __init__(self):
        self.api_key = settings.BREVO_API_KEY
        self.url = "https://api.brevo.com/v3/smtp/email"

    async def send_booking_confirmation(self, email_to: str, booking_details: dict):
        is_hotel = "hotel_name" in booking_details
        subject = f"🏨 Booking Confirmation: {booking_details.get('hotel_name')}" if is_hotel else f"✈️ Boarding Pass: {booking_details.get('airline', 'Flight')} ({booking_details.get('pnr', 'PNR')})"

        html_content = self.generate_hotel_html(booking_details) if is_hotel else self.generate_flight_html(booking_details)

        if not self.api_key:
            print("\n" + "="*80)
            print(f"[MOCK EMAIL SERVICE] Triggers booking email dispatch!")
            print(f"To: {email_to}")
            print(f"Subject: {subject}")
            print(f"Details: {booking_details.get('hotel_name', booking_details.get('airline'))} booking successful.")
            print("="*80 + "\n")
            return True

        headers = {
            "accept": "application/json",
            "api-key": self.api_key,
            "content-type": "application/json"
        }

        payload = {
            "sender": {"name": "Sara Travel Agent", "email": settings.BREVO_SENDER_EMAIL},
            "to": [{"email": email_to}],
            "subject": subject,
            "htmlContent": html_content
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                print("\n" + "="*80)
                print(f"[BREVO EMAIL SERVICE] Email sent successfully to: {email_to}")
                print(f"Message ID: {response.json().get('messageId')}")
                print("="*80 + "\n")
                return True
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    print("\n" + "!"*80)
                    print("[BREVO SERVICE ERROR] 401 Unauthorized.")
                    print("Your BREVO_API_KEY in the .env file is invalid or inactive.")
                    print("Please check your Brevo credentials at https://brevo.com")
                    print("!"*80 + "\n")
                else:
                    print(f"Error sending email (HTTP status error): {e}")
                return False
            except Exception as e:
                print(f"Error sending email: {e}")
                return False

    def generate_flight_html(self, ticket: dict) -> str:
        airline = ticket.get('airline', 'Air India')
        pnr = ticket.get('pnr', 'AI-894271')
        origin = ticket.get('origin', 'BOM')
        origin_full = ticket.get('origin_full', 'Mumbai')
        destination = ticket.get('destination', 'DEL')
        destination_full = ticket.get('destination_full', 'Delhi')
        flight_class = ticket.get('flight_class', 'Economy')
        flight_num = ticket.get('flight_numbers', 'AI 2432')
        flight_date = ticket.get('date', 'N/A')
        gate = ticket.get('gate', 'G12')
        seat = ticket.get('seat', '14A')
        dep_time = ticket.get('departure_time', '09:30 AM')
        arr_time = ticket.get('arrival_time', '11:50 AM')
        add_on = ticket.get('add_on')

        passengers_rows = ""
        for p in ticket.get("passengers", []):
            name = p.get('name', 'Primary Traveler')
            email = p.get('email', 'N/A')
            passengers_rows += f"""
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 14px 16px; font-weight: 700; color: #0f172a; font-size: 14px;">
                    👤 {name}
                </td>
                <td style="padding: 14px 16px; color: #64748b; font-size: 13px;">
                    {email}
                </td>
                <td style="padding: 14px 16px; text-align: right;">
                    <span style="background-color: #ecfdf5; color: #059669; font-size: 11px; font-weight: 800; padding: 4px 10px; border-radius: 9999px; text-transform: uppercase;">Confirmed</span>
                </td>
            </tr>
            """

        logo_img = f'<img src="{ticket.get("airline_logo")}" alt="{airline}" style="height: 32px; max-width: 120px; object-fit: contain; vertical-align: middle; margin-right: 12px;" />' if ticket.get("airline_logo") else ""
        addon_badge = f'<div style="background: #fef3c7; color: #92400e; padding: 10px 16px; border-radius: 10px; font-weight: 700; font-size: 13px; margin-bottom: 20px; border: 1px solid #fde68a;">✨ <b>Active Perk:</b> {add_on}</div>' if add_on else ""

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Boarding Pass - {pnr}</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; padding: 30px 10px; margin: 0; line-height: 1.5;">
            <div style="max-width: 620px; margin: 0 auto; background-color: #ffffff; border-radius: 24px; overflow: hidden; box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0;">
                
                <!-- Premium Header Banner -->
                <div style="background: linear-gradient(135deg, #0b192c 0%, #1e3e62 100%); color: #ffffff; padding: 28px 32px; position: relative;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="vertical-align: middle;">
                                <div style="display: inline-flex; align-items: center;">
                                    {logo_img}
                                    <span style="font-size: 20px; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; color: #ffffff;">{airline}</span>
                                </div>
                                <div style="margin-top: 6px;">
                                    <span style="background: rgba(255,255,255,0.15); color: #93c5fd; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">Official Boarding Pass</span>
                                </div>
                            </td>
                            <td style="text-align: right; vertical-align: middle;">
                                <span style="font-size: 11px; text-transform: uppercase; color: #f59e0b; font-weight: 800; letter-spacing: 1.5px; display: block; margin-bottom: 2px;">Booking Ref (PNR)</span>
                                <span style="font-size: 24px; font-weight: 900; letter-spacing: 2px; color: #ffffff; font-family: monospace;">{pnr}</span>
                            </td>
                        </tr>
                    </table>
                </div>

                <!-- Main Ticket Body -->
                <div style="padding: 32px 32px 24px 32px;">
                    {addon_badge}

                    <!-- Flight Route Card -->
                    <div style="background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%); border-radius: 20px; padding: 24px; border: 1px solid #e2e8f0; margin-bottom: 28px;">
                        <table style="width: 100%; text-align: center; border-collapse: collapse;">
                            <tr>
                                <td style="width: 38%; text-align: left; vertical-align: middle;">
                                    <span style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 800; letter-spacing: 1px; display: block;">Departure</span>
                                    <span style="font-size: 38px; font-weight: 900; color: #0f172a; line-height: 1.1; margin: 4px 0; display: block;">{origin}</span>
                                    <span style="font-size: 13px; color: #475569; font-weight: 600; display: block;">{origin_full}</span>
                                    <span style="font-size: 14px; color: #2563eb; font-weight: 800; margin-top: 4px; display: block;">🕒 {dep_time}</span>
                                </td>
                                <td style="width: 24%; vertical-align: middle; text-align: center;">
                                    <div style="font-size: 24px; color: #2563eb; transform: rotate(0deg); margin-bottom: 4px;">✈️</div>
                                    <div style="background-color: #e0e7ff; color: #3730a3; padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 800; display: inline-block; text-transform: uppercase;">
                                        {flight_class}
                                    </div>
                                    <div style="border-top: 2px dashed #cbd5e1; margin-top: 10px; width: 100%;"></div>
                                </td>
                                <td style="width: 38%; text-align: right; vertical-align: middle;">
                                    <span style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 800; letter-spacing: 1px; display: block;">Arrival</span>
                                    <span style="font-size: 38px; font-weight: 900; color: #0f172a; line-height: 1.1; margin: 4px 0; display: block;">{destination}</span>
                                    <span style="font-size: 13px; color: #475569; font-weight: 600; display: block;">{destination_full}</span>
                                    <span style="font-size: 14px; color: #2563eb; font-weight: 800; margin-top: 4px; display: block;">🕒 {arr_time}</span>
                                </td>
                            </tr>
                        </table>
                    </div>

                    <!-- Flight Specs Grid -->
                    <table style="width: 100%; border-collapse: separate; border-spacing: 8px; margin-bottom: 28px;">
                        <tr>
                            <td style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; padding: 14px 10px; text-align: center; width: 25%;">
                                <span style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 800; display: block; margin-bottom: 4px; letter-spacing: 0.5px;">Flight</span>
                                <span style="font-size: 15px; font-weight: 900; color: #0f172a;">{flight_num}</span>
                            </td>
                            <td style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; padding: 14px 10px; text-align: center; width: 25%;">
                                <span style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 800; display: block; margin-bottom: 4px; letter-spacing: 0.5px;">Date</span>
                                <span style="font-size: 14px; font-weight: 900; color: #0f172a;">{flight_date}</span>
                            </td>
                            <td style="background-color: #fff7ed; border: 1px solid #fed7aa; border-radius: 14px; padding: 14px 10px; text-align: center; width: 25%;">
                                <span style="font-size: 10px; text-transform: uppercase; color: #c2410c; font-weight: 800; display: block; margin-bottom: 4px; letter-spacing: 0.5px;">Gate</span>
                                <span style="font-size: 16px; font-weight: 900; color: #ea580c;">{gate}</span>
                            </td>
                            <td style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 14px; padding: 14px 10px; text-align: center; width: 25%;">
                                <span style="font-size: 10px; text-transform: uppercase; color: #1d4ed8; font-weight: 800; display: block; margin-bottom: 4px; letter-spacing: 0.5px;">Seat</span>
                                <span style="font-size: 16px; font-weight: 900; color: #2563eb;">{seat}</span>
                            </td>
                        </tr>
                    </table>

                    <!-- Passenger Details -->
                    <div style="margin-bottom: 28px;">
                        <h4 style="margin: 0 0 12px 0; color: #0f172a; font-size: 15px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center;">
                            👥 Passenger Information
                        </h4>
                        <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;">
                            <thead style="background-color: #f8fafc;">
                                <tr style="border-bottom: 1px solid #e2e8f0;">
                                    <th style="padding: 10px 16px; text-align: left; font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 800;">Passenger</th>
                                    <th style="padding: 10px 16px; text-align: left; font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 800;">Contact Email</th>
                                    <th style="padding: 10px 16px; text-align: right; font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 800;">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {passengers_rows}
                            </tbody>
                        </table>
                    </div>

                    <!-- Baggage & Terminal Policy Box -->
                    <div style="background-color: #faf5ff; border: 1px solid #f3e8ff; border-radius: 14px; padding: 14px 18px; margin-bottom: 28px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="width: 50%; font-size: 12px; color: #6b21a8; font-weight: 600;">
                                    🧳 <b>Cabin Baggage:</b> 7 kg per guest
                                </td>
                                <td style="width: 50%; font-size: 12px; color: #6b21a8; font-weight: 600; text-align: right;">
                                    🧳 <b>Check-in Baggage:</b> 15 kg included
                                </td>
                            </tr>
                        </table>
                    </div>

                    <!-- Simulated Barcode Footer -->
                    <div style="text-align: center; padding: 20px 0 10px 0; border-top: 1px dashed #cbd5e1;">
                        <div style="letter-spacing: 4px; font-size: 18px; color: #334155; font-family: monospace; font-weight: 900; margin-bottom: 6px;">
                            ||||| | || |||| | |||||| || | |||| |||| ||||| |||
                        </div>
                        <span style="font-size: 11px; color: #94a3b8; font-family: monospace;">E-TICKET REF: {pnr}-ELECTRONIC-VOUCHER</span>
                    </div>
                </div>

                <!-- Footer -->
                <div style="background-color: #f8fafc; text-align: center; padding: 18px 24px; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                    Need assistance with your itinerary? Reply directly to this email or chat with <b>Sara AI Travel Agent</b>.
                </div>
            </div>
        </body>
        </html>
        """

    def generate_hotel_html(self, ticket: dict) -> str:
        hotel_name = ticket.get('hotel_name', 'Luxury Hotel Stay')
        city = ticket.get('city', 'Goa')
        check_in = ticket.get('check_in_date', 'N/A')
        check_out = ticket.get('check_out_date', 'N/A')
        guest_name = ticket.get('guest_name', 'Valued Guest')
        guest_email = ticket.get('guest_email', 'N/A')
        guest_phone = ticket.get('guest_phone', 'N/A')
        room_type = ticket.get('room_type', 'Deluxe Premium Room')
        rooms = ticket.get('rooms', '1')
        nights = ticket.get('nights', '1')
        guests = ticket.get('guests', '1')
        total_price = ticket.get('total_price', '₹4,500.00')
        add_on = ticket.get('add_on')
        booking_ref = f"HTL-{hash(hotel_name + check_in) % 899999 + 100000}"

        img_html = f'<div style="width: 100%; height: 220px; overflow: hidden; background: #1e293b;"><img src="{ticket.get("image")}" alt="{hotel_name}" style="width: 100%; height: 100%; object-fit: cover;" /></div>' if ticket.get("image") else ""
        addon_badge = f'<div style="background: #ecfdf5; color: #065f46; padding: 10px 16px; border-radius: 10px; font-weight: 700; font-size: 13px; margin-bottom: 20px; border: 1px solid #a7f3d0;">🚗 <b>VIP Extra:</b> {add_on}</div>' if add_on else ""

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Hotel Reservation Voucher - {booking_ref}</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 30px 10px; margin: 0; line-height: 1.5;">
            <div style="max-width: 620px; margin: 0 auto; background-color: #ffffff; border-radius: 24px; overflow: hidden; box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0;">
                
                {img_html}

                <!-- Luxury Header -->
                <div style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); color: #ffffff; padding: 26px 32px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td>
                                <span style="background: #f59e0b; color: #78350f; padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 900; text-transform: uppercase; letter-spacing: 1px; display: inline-block; margin-bottom: 8px;">★ Confirmed Hotel Voucher</span>
                                <h2 style="margin: 0 0 6px 0; color: #ffffff; font-size: 24px; font-weight: 900; line-height: 1.2;">{hotel_name}</h2>
                                <p style="margin: 0; color: #c7d2fe; font-size: 14px; font-weight: 600;">📍 {city}</p>
                            </td>
                            <td style="text-align: right; vertical-align: top;">
                                <span style="font-size: 11px; text-transform: uppercase; color: #f59e0b; font-weight: 800; letter-spacing: 1px; display: block; margin-bottom: 2px;">Voucher No.</span>
                                <span style="font-size: 20px; font-weight: 900; color: #ffffff; font-family: monospace;">{booking_ref}</span>
                            </td>
                        </tr>
                    </table>
                </div>

                <!-- Voucher Body -->
                <div style="padding: 32px 32px 24px 32px;">
                    {addon_badge}

                    <!-- Check-in & Check-out Calendar Cards -->
                    <table style="width: 100%; border-collapse: separate; border-spacing: 12px; margin: -12px -12px 20px -12px;">
                        <tr>
                            <td style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px; padding: 18px 20px;">
                                <span style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 800; letter-spacing: 1px; display: block; margin-bottom: 4px;">Check-In Date</span>
                                <span style="font-size: 18px; font-weight: 900; color: #0f172a; display: block;">{check_in}</span>
                                <span style="font-size: 12px; color: #059669; font-weight: 700; display: block; margin-top: 4px;">🕒 From 14:00 PM</span>
                            </td>
                            <td style="width: 50%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px; padding: 18px 20px;">
                                <span style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 800; letter-spacing: 1px; display: block; margin-bottom: 4px;">Check-Out Date</span>
                                <span style="font-size: 18px; font-weight: 900; color: #0f172a; display: block;">{check_out}</span>
                                <span style="font-size: 12px; color: #dc2626; font-weight: 700; display: block; margin-top: 4px;">🕒 Until 11:00 AM</span>
                            </td>
                        </tr>
                    </table>

                    <!-- Stay Breakdown Table -->
                    <div style="border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden; margin-bottom: 24px;">
                        <div style="background-color: #f8fafc; padding: 12px 18px; border-bottom: 1px solid #e2e8f0; font-size: 12px; font-weight: 800; text-transform: uppercase; color: #475569; letter-spacing: 0.5px;">
                            🏨 Reservation Summary
                        </div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                            <tr style="border-bottom: 1px solid #f1f5f9;">
                                <td style="padding: 12px 18px; color: #64748b; font-weight: 600;">Primary Guest</td>
                                <td style="padding: 12px 18px; font-weight: 800; color: #0f172a; text-align: right;">{guest_name}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #f1f5f9;">
                                <td style="padding: 12px 18px; color: #64748b; font-weight: 600;">Room Selection</td>
                                <td style="padding: 12px 18px; font-weight: 800; color: #0f172a; text-align: right;">{room_type}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #f1f5f9;">
                                <td style="padding: 12px 18px; color: #64748b; font-weight: 600;">Duration & Rooms</td>
                                <td style="padding: 12px 18px; font-weight: 800; color: #0f172a; text-align: right;">{rooms} Room(s) • {nights} Night(s)</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #f1f5f9;">
                                <td style="padding: 12px 18px; color: #64748b; font-weight: 600;">Occupancy</td>
                                <td style="padding: 12px 18px; font-weight: 800; color: #0f172a; text-align: right;">{guests} Guest(s)</td>
                            </tr>
                            <tr style="background-color: #f8fafc;">
                                <td style="padding: 14px 18px; color: #0f172a; font-weight: 800; font-size: 15px;">Total Amount Paid</td>
                                <td style="padding: 14px 18px; font-weight: 900; color: #059669; text-align: right; font-size: 18px;">{total_price}</td>
                            </tr>
                        </table>
                    </div>

                    <!-- Amenities Included -->
                    <div style="background-color: #eff6ff; border: 1px solid #dbeafe; border-radius: 14px; padding: 14px 18px; margin-bottom: 24px;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #1e40af; font-weight: 800; display: block; margin-bottom: 6px;">✨ Complimentary Amenities:</span>
                        <div style="font-size: 13px; color: #1e3a8a; font-weight: 600;">
                            📶 High-Speed Wi-Fi • 🍳 Daily Breakfast Buffet • 🏊 Pool & Gym Access • 🛎️ 24/7 Front Desk
                        </div>
                    </div>

                    <!-- Front Desk Instructions -->
                    <div style="text-align: center; padding-top: 10px; border-top: 1px dashed #cbd5e1;">
                        <p style="font-size: 13px; color: #64748b; margin: 0 0 16px 0;">
                            Please present a valid photo ID and this digital voucher upon arrival at the hotel reception.
                        </p>
                    </div>
                </div>

                <!-- Footer -->
                <div style="background-color: #f8fafc; text-align: center; padding: 18px 24px; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                    Have questions regarding check-in? Reply directly to this email or chat with <b>Sara AI Travel Agent</b>.
                </div>
            </div>
        </body>
        </html>
        """

email_service = EmailService()

