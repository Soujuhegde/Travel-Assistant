import React from 'react';
import { Download } from 'lucide-react';
import html2canvas from 'html2canvas';

// Helper to extract 3-letter IATA code
const getIataCode = (city, fullAirport) => {
  if (city && city.length === 3) return city.toUpperCase();
  if (fullAirport) {
    const match = fullAirport.match(/\(([A-Z]{3})\)/);
    if (match) return match[1];
  }
  return (city || 'N/A').substring(0, 3).toUpperCase();
};

// Single boarding pass for one passenger
const SingleBoardingPass = ({ ticket, passengerName, passengerIndex, seat }) => {
  const ticketRef = React.useRef(null);
  const displayDate = ticket.date.toUpperCase();

  const handleDownload = async () => {
    if (!ticketRef.current) return;
    try {
      const btn = ticketRef.current.querySelector('.download-btn');
      if (btn) btn.style.display = 'none';

      const canvas = await html2canvas(ticketRef.current, {
        useCORS: true,
        allowTaint: true,
        backgroundColor: '#4a81e3',
        scale: 2,
      });

      if (btn) btn.style.display = 'flex';

      const dataUrl = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.download = `boarding_pass_${ticket.pnr || 'ticket'}_pax${passengerIndex + 1}.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error('Error generating image:', err);
    }
  };

  return (
    <div ref={ticketRef} className="w-full max-w-4xl mx-auto my-4 flex flex-col md:flex-row font-sans rounded-2xl overflow-hidden shadow-2xl bg-[#4a81e3] p-2 relative">
      
      {/* Download Icon Button */}
      <button 
        onClick={handleDownload} 
        className="download-btn absolute top-5 right-5 bg-white/10 hover:bg-white/20 text-white p-2.5 rounded-full transition-colors z-20 flex items-center justify-center shadow-md border border-white/10"
        title={`Download Boarding Pass - ${passengerName}`}
      >
        <Download className="w-5 h-5 text-white" />
      </button>

      {/* Left Section (White Card) */}
      <div className="flex-1 bg-white rounded-xl p-6 md:p-8 relative flex flex-col">

        {/* Top Header */}
        <div className="flex justify-between items-start mb-6">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-[#4a81e3] text-white rounded-full flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="currentColor" className="w-8 h-8 transform -rotate-45">
                <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-bold text-[#204996] leading-tight uppercase tracking-wide">
                {ticket.airline}
              </h2>
              <p className="text-xs font-semibold text-[#4a81e3] tracking-widest">AIRLINES</p>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="px-4 py-1 bg-[#4a81e3] text-white text-xs font-bold uppercase tracking-wider rounded">
              {ticket.flight_class}
            </span>
            {(ticket.journey_type === "Round Trip" || ticket.return_date) && (
              <span className="px-3 py-1 bg-emerald-600 text-white text-[11px] font-black uppercase tracking-wider rounded text-center shadow-sm">
                ROUND TRIP 🔁
              </span>
            )}
            <span className="px-4 py-1 bg-[#4a81e3] text-white text-xs font-bold uppercase tracking-wider rounded text-center">
              GROUP {ticket.group}
            </span>
          </div>
        </div>

        <div className="border-b-2 border-gray-100 mb-8 w-full"></div>

        {/* Middle Route Section */}
        <div className="flex justify-between items-center mb-10 px-4">
          <div className="text-left">
            <p className="text-sm text-gray-400 uppercase tracking-widest font-semibold mb-1">From</p>
            <p className="text-5xl font-bold text-[#204996] mb-1">{ticket.origin}</p>
            <p className="text-sm font-semibold text-gray-500 uppercase">{ticket.origin_full || 'Origin'}</p>
          </div>

          <div className="flex-1 px-6 flex items-center justify-center relative">
            <div className="w-full h-[2px] bg-gray-300 border-dashed border-t-2 border-gray-300 absolute"></div>
            <div className="z-10 text-[#4a81e3] transform rotate-90 bg-white px-2">
              <svg viewBox="0 0 24 24" fill="currentColor" className="w-8 h-8">
                <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
              </svg>
            </div>
          </div>

          <div className="text-right">
            <p className="text-sm text-gray-400 uppercase tracking-widest font-semibold mb-1">To</p>
            <p className="text-5xl font-bold text-[#204996] mb-1">{ticket.destination}</p>
            <p className="text-sm font-semibold text-gray-500 uppercase">{ticket.destination_full || 'Destination'}</p>
          </div>
        </div>

        {/* Bottom Details Box */}
        <div className="bg-[#f2f6fc] rounded-xl p-5 flex justify-between items-center mt-auto">
          <div className="grid grid-cols-4 gap-y-4 gap-x-8 w-full">
            <div className="col-span-2">
              <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold mb-1">Passenger</p>
              <p className="font-bold text-gray-800 text-sm whitespace-nowrap">{passengerName}</p>
            </div>
            <div className={ticket.return_date ? "col-span-1" : "col-span-2"}>
              <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold mb-1">Outbound</p>
              <p className="font-bold text-gray-800 text-sm">{displayDate}</p>
            </div>
            {ticket.return_date && (
              <div className="col-span-1">
                <p className="text-[10px] text-emerald-600 uppercase tracking-widest font-bold mb-1">Return</p>
                <p className="font-bold text-[#204996] text-sm">{ticket.return_date}</p>
              </div>
            )}
            <div>
              <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold mb-1">Gate</p>
              <p className="font-bold text-gray-800 text-sm">{ticket.gate}</p>
            </div>
            <div>
              <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold mb-1">Flight</p>
              <p className="font-bold text-gray-800 text-sm">{ticket.flight_numbers}</p>
            </div>
            <div>
              <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold mb-1">Boarding Time</p>
              <p className="font-bold text-gray-800 text-sm">{ticket.departure_time}</p>
            </div>
            <div>
              <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold mb-1">Seat</p>
              <p className="font-bold text-gray-800 text-sm">{seat}</p>
            </div>
          </div>

          <div className="ml-4 flex-shrink-0">
            <div className="w-20 h-20 bg-white p-1 rounded grid grid-cols-4 grid-rows-4 gap-0.5">
              {[...Array(16)].map((_, i) => (
                <div key={i} className={`bg-gray-800 ${Math.random() > 0.3 ? 'opacity-100' : 'opacity-0'}`}></div>
              ))}
            </div>
          </div>
        </div>

        {ticket.add_on && (
          <div className="mt-3 px-3 py-1.5 bg-amber-50 border border-amber-200/80 rounded-lg flex items-center gap-2 text-xs font-bold text-amber-900 animate-fade-in-up">
            <span>✨</span>
            <span>{ticket.add_on}</span>
          </div>
        )}
      </div>

      {/* Dashed Separator */}
      <div className="hidden md:flex flex-col items-center justify-center w-6 relative">
        <div className="absolute top-0 bottom-0 w-[2px] border-l-[3px] border-dashed border-white/40"></div>
      </div>

      {/* Right Section (Blue area) */}
      <div className="w-full md:w-80 p-5 md:p-6 text-white flex flex-col relative rounded-r-2xl border-t md:border-t-0 md:border-l-0 border-white/20 border-dashed mt-4 md:mt-0">
        <h3 className="text-xl font-bold tracking-widest uppercase mb-6 text-center mt-8">Boarding Pass</h3>

        {/* Small White Route Box */}
        <div className="bg-white text-[#204996] rounded-xl p-3 flex justify-between items-center mb-8 w-full shadow-inner">
          <div className="text-center flex-1">
            <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold">From</p>
            <p className="text-2xl font-bold">{getIataCode(ticket.origin, ticket.origin_full)}</p>
          </div>
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 transform rotate-90 text-[#4a81e3] mx-2 flex-shrink-0">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
          </svg>
          <div className="text-center flex-1">
            <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold">To</p>
            <p className="text-2xl font-bold">{getIataCode(ticket.destination, ticket.destination_full)}</p>
          </div>
        </div>

        {/* Text Details */}
        <div className="grid grid-cols-2 gap-y-5 gap-x-2 text-sm w-full">
          <div className="col-span-2">
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-0.5">Passenger Name</p>
            <p className="font-semibold truncate">{passengerName}</p>
          </div>
          
          <div>
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-0.5">Gate</p>
            <p className="font-semibold">{ticket.gate}</p>
          </div>
          <div className="text-right">
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-0.5">Flight</p>
            <p className="font-semibold">{ticket.flight_numbers}</p>
          </div>

          <div>
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-0.5">Date</p>
            <p className="font-semibold">{displayDate}</p>
          </div>
          <div className="text-right">
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-0.5">Boarding Time</p>
            <p className="font-semibold">{ticket.departure_time}</p>
          </div>

          <div>
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-0.5">Departed</p>
            <p className="font-semibold">{ticket.departure_time}</p>
          </div>
          <div className="text-right">
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-0.5">Arrived</p>
            <p className="font-semibold">{ticket.arrival_time}</p>
          </div>
        </div>

        {/* Bottom Boxes */}
        <div className="flex gap-4 mt-auto pt-6">
          <div className="flex-1 border border-white/40 rounded-lg p-2 text-center bg-white/10">
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-1">Group</p>
            <p className="text-xl font-bold">{ticket.group}</p>
          </div>
          <div className="flex-1 border border-white/40 rounded-lg p-2 text-center bg-white/10">
            <p className="text-[9px] text-white/60 uppercase tracking-widest mb-1">Seat</p>
            <p className="text-xl font-bold">{seat}</p>
          </div>
        </div>
      </div>

    </div>
  );
};

// Generate unique seats for all passengers
const generateSeats = (count) => {
  const rows = Array.from({ length: 30 }, (_, i) => i + 1);
  const cols = ['A', 'B', 'C', 'D', 'E', 'F'];
  const used = new Set();
  const seats = [];
  while (seats.length < count) {
    const row = rows[Math.floor(Math.random() * rows.length)];
    const col = cols[Math.floor(Math.random() * cols.length)];
    const seat = `${row}${col}`;
    if (!used.has(seat)) {
      used.add(seat);
      seats.push(seat);
    }
  }
  return seats;
};

const FlightTicket = ({ ticket }) => {
  if (!ticket) return null;

  const passengers = ticket.passengers && ticket.passengers.length > 0
    ? ticket.passengers
    : [{ name: 'PASSENGER' }];

  // Stable unique seats per PNR
  const seats = React.useMemo(
    () => generateSeats(passengers.length),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ticket.pnr, passengers.length]
  );

  return (
    <div className="flex flex-col gap-2">
      {passengers.map((pax, idx) => (
        <SingleBoardingPass
          key={idx}
          ticket={ticket}
          passengerName={(pax.name || 'PASSENGER').toUpperCase()}
          passengerIndex={idx}
          seat={seats[idx]}
        />
      ))}
    </div>
  );
};

export default FlightTicket;
