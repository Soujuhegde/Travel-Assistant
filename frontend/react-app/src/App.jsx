import React, { useState } from 'react';
import ChatInterface from './components/ChatInterface';

function App() {
  const [currentFlow, setCurrentFlow] = useState(null);

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-[80%] max-w-[1600px] h-[90vh] glass rounded-3xl overflow-hidden flex flex-col">
        <header className="bg-brand text-white p-6 shadow-md z-10 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="text-2xl font-bold tracking-wide">TravelBot</h1>
              <p className="text-brand-light text-sm">Your intelligent travel companion</p>
            </div>
            {currentFlow && (
              <span className={`px-4 py-1.5 rounded-full text-xs font-black uppercase tracking-widest shadow-sm flex items-center gap-1.5 animate-fade-in ${
                currentFlow === "Flight Booking" ? "bg-blue-600/30 text-blue-200 border border-blue-500/20" :
                currentFlow === "Hotel Booking" ? "bg-amber-600/30 text-amber-200 border border-amber-500/20" :
                "bg-emerald-600/30 text-emerald-200 border border-emerald-500/20"
              }`}>
                {currentFlow === "Flight Booking" && "✈️ "}
                {currentFlow === "Hotel Booking" && "🏨 "}
                {currentFlow === "Itinerary Plan" && "🗺️ "}
                {currentFlow}
              </span>
            )}
          </div>
        </header>

        <main className="flex-1 overflow-hidden relative">
          <ChatInterface onFlowChange={setCurrentFlow} />
        </main>
      </div>
    </div>
  );
}

export default App;
