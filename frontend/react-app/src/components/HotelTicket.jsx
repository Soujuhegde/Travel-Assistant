import React from 'react';

const HotelTicket = ({ ticket }) => {
  if (!ticket) return null;

  const pricePerNight = ticket.price_per_night || "₹2,250";
  
  // Compute nights from actual dates if available, fallback to ticket.nights
  let nights = ticket.nights || 1;
  if (ticket.check_in_date && ticket.check_out_date) {
    try {
      const d1 = new Date(ticket.check_in_date);
      const d2 = new Date(ticket.check_out_date);
      const diff = Math.round((d2 - d1) / (1000 * 60 * 60 * 24));
      if (diff > 0) nights = diff;
    } catch (_) {}
  }
  
  // Recompute total price on frontend from price_per_night × nights × rooms
  let rooms = 1;
  try { rooms = parseInt((ticket.rooms || "1").replace(/[^\d]/g, "")) || 1; } catch (_) {}
  let totalPrice = ticket.total_price;
  try {
    const cleanPriceStr = pricePerNight.replace(/[^\d.]/g, "");
    const pRaw = parseFloat(cleanPriceStr);
    if (pRaw > 0 && nights > 0) {
      totalPrice = `₹${(pRaw * nights * rooms).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
  } catch (_) {}
  if (!totalPrice) totalPrice = pricePerNight;

  const occupancy = `${ticket.guests || "01 Adult"}, ${ticket.rooms || "01 Room"}`;

  return (
    <div className="w-full max-w-xl mx-auto my-4 bg-white border border-slate-200 rounded-3xl p-5 shadow-lg relative font-sans flex flex-col gap-4">
      {/* Green Checkmark Circle on left edge */}
      <div className="absolute -left-5 top-1/2 -translate-y-1/2 w-10 h-10 bg-emerald-500 rounded-full flex items-center justify-center border-4 border-white shadow-md z-10">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="w-5 h-5 text-white">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>

      <div className="pl-4">
        {/* Room & Price Summary Header */}
        <h3 className="font-bold text-slate-800 text-lg mb-4">Room & Price Summary</h3>

        <div className="flex gap-4 items-start mb-4">
          {/* Room Image */}
          <div className="w-24 h-24 rounded-xl overflow-hidden flex-shrink-0 bg-slate-100 border border-slate-100">
            <img 
              src={ticket.image || "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=200&q=80"} 
              alt={ticket.room_type} 
              className="w-full h-full object-cover"
            />
          </div>

          {/* Room Details */}
          <div className="flex-1 min-w-0">
            <h4 className="font-bold text-slate-800 text-lg truncate">{ticket.room_type || "Executive Rooms"}</h4>
            
            {/* Address */}
            <p className="text-xs text-slate-400 mt-1 mb-2 flex items-start gap-1 font-medium leading-tight">
              <span className="flex-shrink-0 text-slate-400">📍</span>
              <span className="truncate">{ticket.hotel_name}, {ticket.city}, India</span>
            </p>

            {/* Amenities */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-slate-500 font-medium text-xs">
              <span className="flex items-center gap-1">📰 Newspaper</span>
              <span className="flex items-center gap-1">🍺 Refrigerator</span>
              <span className="text-[#3b82f6] font-bold hover:underline cursor-pointer">More Amenities</span>
            </div>
          </div>
        </div>

        {/* Shaded Occupancy Table */}
        <div className="bg-[#f0f6ff] rounded-xl p-3 grid grid-cols-2 gap-3 text-left mb-4">
          <div>
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Check In Date/Time</p>
            <p className="font-bold text-slate-800 text-sm mt-0.5">{ticket.check_in_date || "12 PM"}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Check Out Date/Time</p>
            <p className="font-bold text-slate-800 text-sm mt-0.5">{ticket.check_out_date || "11 AM"}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Occupancy</p>
            <p className="font-bold text-slate-800 text-sm mt-0.5 truncate">{occupancy}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Guest Name</p>
            <p className="font-bold text-slate-800 text-sm mt-0.5 truncate">{ticket.guest_name || "Guest"}</p>
          </div>
        </div>

        {/* Pricing Info */}
        <div className="flex justify-between items-center py-3 px-4 bg-slate-50/50 rounded-2xl border border-slate-100 mb-4">
          <div className="text-left">
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Price per night</p>
            <p className="text-lg font-black text-slate-800 mt-0.5">{pricePerNight}</p>
          </div>
          
          <div className="h-8 w-px bg-slate-200"></div>

          <div className="text-right">
            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Total ({nights} Night{nights > 1 ? 's' : ''})</p>
            <p className="text-xl font-black text-[#1e88e5] mt-0.5">{totalPrice}</p>
          </div>
        </div>

        {ticket.add_on && (
          <div className="mb-3 px-3.5 py-2 bg-amber-50 border border-amber-200/80 rounded-xl flex items-center gap-2 text-xs font-bold text-amber-900 animate-fade-in-up">
            <span>✨</span>
            <span>{ticket.add_on}</span>
          </div>
        )}

        {/* Booked Button */}
        <div className="flex justify-end mt-2">
          <button 
            disabled 
            className="bg-[#1e88e5] text-white font-bold py-2.5 px-10 rounded-xl text-sm opacity-100 shadow transition-opacity cursor-default w-32 text-center"
          >
            Booked
          </button>
        </div>
      </div>
    </div>
  );
};

export default HotelTicket;
