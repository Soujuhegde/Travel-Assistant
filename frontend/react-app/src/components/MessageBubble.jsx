import React from 'react';
import { Plane, Hotel, CheckCircle, ChevronRight } from 'lucide-react';
import FlightTicket from './FlightTicket';
import HotelCard from './HotelCard';
import HotelTicket from './HotelTicket';
import PaymentCheckoutCard from './PaymentCheckoutCard';
import UpsellOfferCard from './UpsellOfferCard';

const formatDuration = (dur) => {
  if (!dur) return "";
  const durStr = String(dur).trim();
  if (durStr.includes('h') || durStr.includes('d')) {
    return durStr;
  }
  const minutes = parseInt(durStr.replace(/[^\d]/g, ""), 10);
  if (isNaN(minutes)) {
    return durStr;
  }
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0 && m > 0) {
    return `${h}h ${m}m`;
  } else if (h > 0) {
    return `${h}h`;
  } else {
    return `${m}m`;
  }
};

const FlightCard = ({ option }) => {
  const isRoundTrip = option.journey_type === "Round Trip" || Boolean(option.return_date);

  return (
    <div className="bg-white border border-slate-100 rounded-3xl p-5 my-2 shadow-sm mb-4">
      <div className="flex justify-between items-start mb-4 gap-2">
        <div className="font-bold text-slate-800 text-lg flex items-center gap-3">
          {option.airline_logo && <img src={option.airline_logo} alt={option.airline_name} className="w-6 h-6 object-contain" />}
          <span>{option.airline_name} - {option.flight_numbers}</span>
        </div>
        {isRoundTrip && (
          <span className="px-2.5 py-1 bg-indigo-50 text-indigo-700 border border-indigo-200/80 rounded-full text-xs font-extrabold whitespace-nowrap flex-shrink-0">
            🔁 Round Trip
          </span>
        )}
      </div>
      
      <div className="flex justify-between text-sm text-slate-500 font-medium mb-1">
        <span>Outbound: {option.departure_date}</span>
        {isRoundTrip && option.return_date ? (
          <span className="text-indigo-600 font-bold">Return: {option.return_date}</span>
        ) : (
          <span>{option.arrival_date}</span>
        )}
      </div>
      
      <div className="flex justify-between items-center mb-1">
        <div className="text-3xl font-bold text-[#004e92]">{option.departure_time}</div>
        <div className="flex-1 flex flex-col items-center mx-4">
          <div className="flex items-center w-full text-slate-400 font-medium text-xs">
            <div className="flex-1 border-t border-dashed border-slate-400"></div>
            <span className="bg-[#f0f4f8] px-2 py-1 rounded-md mx-2 text-slate-700">{formatDuration(option.duration)}</span>
            <div className="flex-1 border-t border-dashed border-slate-400"></div>
          </div>
        </div>
        <div className="text-3xl font-bold text-[#004e92]">{option.arrival_time}</div>
      </div>
      
      <div className="flex justify-between text-sm font-semibold text-slate-800 mb-6">
        <div className="w-24 leading-tight">{option.origin_airport}</div>
        <div className="text-slate-600 font-bold">{option.stops}</div>
        <div className="w-24 text-right leading-tight">{option.destination_airport}</div>
      </div>
      
      <div className="space-y-3">
        {option.pricing?.map((p, idx) => (
          <div 
            key={idx} 
            onClick={() => option.onOptionSelect && option.onOptionSelect(option, p.class, p.price)}
            className="flex justify-between items-center bg-orange-50 p-4 rounded-xl cursor-pointer hover:bg-orange-100 transition-colors"
          >
            <span className="font-bold text-slate-900 text-base">{p.class}</span>
            <span className="font-bold text-brand flex items-center gap-1 text-base">
              From {p.price} <ChevronRight className="w-4 h-4" />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const renderMessageText = (text, isUser) => {
  if (!text) return null;
  const textColorClass = isUser ? 'text-white' : 'text-slate-700';
  const headingColorClass = isUser ? 'text-white border-white/10' : 'text-slate-800 border-slate-100';
  const boldBgClass = isUser ? 'bg-white/10 text-white' : 'bg-indigo-50/50 text-slate-800';
  const bulletColorClass = isUser ? 'text-white/80' : 'text-indigo-500';

  // Sanitize any code block markers or html tags that might slip through
  let cleanText = text
    .replace(/^```[a-zA-Z]*\n?/gm, '')
    .replace(/```$/gm, '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<li>/gi, '- ')
    .replace(/<\/?[a-zA-Z][^>]*>/g, '');

  const lines = cleanText.split('\n');

  return lines.map((line, index) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('### ')) {
      return (
        <h3 key={index} className={`font-bold ${headingColorClass} text-[20px] md:text-[21px] mt-4 mb-2 flex items-center gap-1.5 border-b pb-1`}>
          {renderLineContent(trimmed.slice(4), isUser, boldBgClass)}
        </h3>
      );
    }
    if (trimmed.startsWith('## ')) {
      return (
        <h2 key={index} className={`font-black ${headingColorClass} text-[22px] md:text-[23px] mt-5 mb-3 flex items-center gap-1.5`}>
          {renderLineContent(trimmed.slice(3), isUser, boldBgClass)}
        </h2>
      );
    }
    if (trimmed.startsWith('# ')) {
      return (
        <h1 key={index} className={`font-black ${headingColorClass} text-[24px] md:text-[25px] mt-5 mb-4`}>
          {renderLineContent(trimmed.slice(2), isUser, boldBgClass)}
        </h1>
      );
    }

    if (trimmed.startsWith('* ') || trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
      const content = trimmed.replace(/^[*•-]\s*/, '');
      return (
        <div key={index} className={`flex items-start gap-2 ml-4 my-1.5 ${textColorClass} leading-relaxed`}>
          <span className={`font-bold select-none ${bulletColorClass}`}>•</span>
          <p className="flex-1 text-[19px] md:text-[20px]">{renderLineContent(content, isUser, boldBgClass)}</p>
        </div>
      );
    }

    if (trimmed === '') {
      return <div key={index} className="h-2" />;
    }

    return (
      <p key={index} className={`leading-relaxed my-1 text-[19px] md:text-[20px] ${textColorClass}`}>
        {renderLineContent(line, isUser, boldBgClass)}
      </p>
    );
  });
};

const renderLineContent = (str, isUser, boldBgClass) => {
  const boldRegex = /\*\*([^*]+)\*\*/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = boldRegex.exec(str)) !== null) {
    if (match.index > lastIndex) {
      parts.push(renderTextWithLinksOnly(str.substring(lastIndex, match.index), isUser));
    }
    parts.push(
      <strong key={match.index} className={`font-extrabold ${boldBgClass} px-1 rounded`}>
        {match[1]}
      </strong>
    );
    lastIndex = boldRegex.lastIndex;
  }

  if (lastIndex < str.length) {
    parts.push(renderTextWithLinksOnly(str.substring(lastIndex), isUser));
  }

  return parts.length > 0 ? parts : str;
};

const renderTextWithLinksOnly = (text, isUser) => {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const parts = text.split(urlRegex);
  return parts.map((part, index) => {
    if (part.match(urlRegex)) {
      return (
        <a
          key={index}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
          className={`${isUser ? 'text-white hover:text-white/80' : 'text-indigo-600 hover:text-indigo-800'} font-bold underline transition-colors break-all`}
        >
          {part}
        </a>
      );
    }
    return part;
  });
};

const parseItinerary = (text) => {
  if (!text) return null;
  // Flexible match for Day 1 header (e.g. ### 🌟 Day 1, ### Day 1:, ## Day 1, **Day 1**)
  const hasDay1 = /(?:###|##|\*\*)\s*(?:[🌟📍✨🗺️🗓️📅\w\s]*\s*)?Day\s*1\b/i.test(text);
  if (!hasDay1) {
    return null;
  }
  
  // Clean code blocks or wrappers
  let cleanText = text
    .replace(/^```[a-zA-Z]*\n?/gm, '')
    .replace(/```$/gm, '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<li>/gi, '- ')
    .replace(/<\/?[a-zA-Z][^>]*>/g, '');

  const lines = cleanText.split('\n');
  const days = [];
  const footers = {};
  let currentDay = null;
  let currentFooterSection = null;
  let intro = '';
  
  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed === '---') continue;
    
    // Check if this is a Footer Section Header (e.g., Packing Tips, Essential Info, Local Tips, etc.)
    const footerMatch = trimmed.match(/^(?:###|##|\*\*|- \*\*)\s*(?:[🎒📋💡🏨✈️🛡️\w\s]*\s*)?(Packing Tips|Essential Info|Travel Tips|Local Tips|Hotel Details|Flight Details|Safety Tips|Emergency Numbers|Travel Guide|Best Apps|Guide)\b/i);
                           
    if (footerMatch) {
      currentFooterSection = footerMatch[1].trim();
      footers[currentFooterSection] = [];
      currentDay = null;
      continue;
    } else if (currentFooterSection) {
      // Check if another day started (should not happen after footers, but for safety)
      const isDayHeader = /^(?:###|##|\*\*)\s*(?:[🌟📍✨🗺️🗓️📅\s]*\s*)?Day\s*\d+\b/i.test(trimmed);
      if (!isDayHeader) {
        if (trimmed.startsWith('* ') || trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
          footers[currentFooterSection].push(trimmed.replace(/^[*•-]\s*/, ''));
        } else {
          footers[currentFooterSection].push(trimmed);
        }
        continue;
      }
    }
    
    // Check if this is a Day Header (e.g., "### 🌟 Day 1: Coastal Explorations", "## Day 2", "### Day 3 - Forts")
    const dayHeaderMatch = trimmed.match(/^(?:###|##|\*\*)\s*(?:[🌟📍✨🗺️🗓️📅\s]*\s*)?Day\s*(\d+)[:\-–\s]*(.*)$/i);
    if (dayHeaderMatch) {
      const dayNum = dayHeaderMatch[1];
      const dayTheme = dayHeaderMatch[2].replace(/\*\*/g, '').trim();
      const title = dayTheme ? `Day ${dayNum}: ${dayTheme}` : `Day ${dayNum}`;
      currentDay = {
        title: title,
        activities: [],
        summary: ''
      };
      days.push(currentDay);
      currentFooterSection = null;
    } else if (currentDay) {
      if (trimmed.startsWith('* ') || trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
        currentDay.activities.push(trimmed.replace(/^[*•-]\s*/, ''));
      } else if (!trimmed.startsWith('#') && !trimmed.startsWith('**Trip Details') && !trimmed.includes('Duration:')) {
        if (currentDay.activities.length === 0) {
          currentDay.summary = trimmed;
        } else {
          currentDay.activities.push(trimmed);
        }
      }
    } else {
      if (!trimmed.startsWith('#')) {
        intro += trimmed + '\n';
      }
    }
  }
  
  return { intro, days, footers };
};

const ItineraryTimeline = ({ text, isUser }) => {
  const parsed = parseItinerary(text);
  const [activeDay, setActiveDay] = React.useState(0);

  if (!parsed || parsed.days.length === 0) {
    return null;
  }

  // Extract clean destination / title
  let cleanTitle = 'Travel Itinerary';
  const destMatch = text.match(/Destination:\s*\*?([A-Za-z\s]+)\*?/i) || text.match(/Itinerary for\s*\*?([A-Za-z\s]+)\*?/i);
  if (destMatch) {
    cleanTitle = `${destMatch[1].trim()} Itinerary`;
  } else if (parsed.intro) {
    const rawFirst = parsed.intro.replace(/\*\*/g, '').replace(/Trip Details:/g, '').trim().split('\n')[0];
    if (rawFirst) cleanTitle = rawFirst;
  }
  const currentDayData = parsed.days[activeDay];

  return (
    <div className="w-full bg-white border border-slate-100 rounded-3xl overflow-hidden my-3 shadow-md max-w-full p-6 flex flex-col gap-6">
      {/* Title Header */}
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center text-2xl shadow-sm">
          🗺️
        </div>
        <div>
          <div className="text-[15px] uppercase tracking-widest text-slate-400 font-extrabold mb-0.5">Your Itinerary</div>
          <h3 className="text-3xl md:text-4xl font-black text-slate-800 leading-tight">
            {cleanTitle || 'Travel Itinerary'}
          </h3>
        </div>
      </div>

      {/* Horizontal Tabs for Days */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
        {parsed.days.map((day, idx) => {
          const isActive = activeDay === idx;
          return (
            <button
              key={idx}
              onClick={() => setActiveDay(idx)}
              className={`px-7 py-3 rounded-full text-lg font-bold transition-all flex-shrink-0 ${
                isActive 
                  ? 'bg-[#060636] text-white shadow-md shadow-indigo-900/10' 
                  : 'bg-slate-50 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
              }`}
            >
              Day {idx + 1}
            </button>
          );
        })}
      </div>

      {/* Selected Day Content */}
      {currentDayData && (
        <div className="flex flex-col gap-6 bg-slate-50/40 border border-slate-100/50 rounded-2xl p-6 transition-all duration-200">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h4 className="font-extrabold text-slate-800 text-[23px] md:text-[24px]">
              {currentDayData.title}
            </h4>
          </div>

          {currentDayData.summary && (
            <p className="text-[21px] md:text-[22px] text-slate-600 leading-relaxed italic border-l-2 border-slate-200 pl-3">
              {currentDayData.summary.replace(/\*\*/g, '')}
            </p>
          )}

          {/* Timeline of Activities */}
          <div className="relative border-l border-slate-200 ml-3 pl-6 flex flex-col gap-6 py-2">
            {currentDayData.activities.map((act, aIdx) => {
              const cleanAct = act.replace(/\*\*/g, '');
              if (!cleanAct.trim()) return null;

              return (
                <div key={aIdx} className="relative flex flex-col items-start gap-1 group">
                  <div className="absolute -left-[31.5px] top-2.5 w-[10px] h-[10px] rounded-full bg-slate-300 border-2 border-white shadow-sm transition-transform duration-200 group-hover:scale-125"></div>
                  
                  <p className="text-[21px] md:text-[22px] text-slate-600 leading-relaxed">
                    {renderTextWithLinksOnly(cleanAct, isUser)}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer Utility Cards */}
      {parsed.footers && Object.keys(parsed.footers).length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
          {Object.entries(parsed.footers).map(([section, items], sIdx) => {
            if (items.length === 0) return null;
            
            let bgClass = "bg-slate-50 border-slate-100";
            let titleClass = "text-slate-800";
            let icon = "💡";
            
            if (section.toLowerCase().includes("tip")) {
              bgClass = "bg-amber-50/40 border-amber-100/50";
              titleClass = "text-amber-800";
              icon = "💡";
            } else if (section.toLowerCase().includes("hotel")) {
              bgClass = "bg-sky-50/40 border-sky-100/50";
              titleClass = "text-sky-800";
              icon = "🏨";
            } else if (section.toLowerCase().includes("flight")) {
              bgClass = "bg-indigo-50/40 border-indigo-100/50";
              titleClass = "text-indigo-800";
              icon = "✈️";
            } else if (section.toLowerCase().includes("safe")) {
              bgClass = "bg-red-50/40 border-red-100/50";
              titleClass = "text-red-800";
              icon = "🛡️";
            }
            
            return (
              <div key={sIdx} className={`p-5 rounded-2xl border ${bgClass} flex flex-col gap-3 shadow-sm`}>
                <h5 className={`font-black text-[20px] md:text-[21px] ${titleClass} flex items-center gap-1.5`}>
                  <span>{icon}</span> {section}
                </h5>
                <ul className="flex flex-col gap-2">
                  {items.map((item, iIdx) => {
                    const cleanItem = item.replace(/\*\*/g, '');
                    return (
                      <li key={iIdx} className="text-slate-600 text-[19px] md:text-[20px] leading-relaxed flex items-start gap-2">
                        <span className="select-none text-slate-400">•</span>
                        <span className="flex-1">
                          {renderTextWithLinksOnly(cleanItem, isUser)}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const MessageBubble = ({ message, onQuickReply, onOptionSelect, onPay, onDirectPay, onUpsellPay, onUpsellDecline }) => {
  const isUser = message.sender === 'user';
  const hasItinerary = !isUser && parseItinerary(message.text);

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} mb-6`}>
      {/* Bot Avatar */}
      {!isUser && (
        <div className="w-12 h-12 rounded-full overflow-hidden mr-3 flex-shrink-0 mt-1 shadow-sm border border-slate-200">
          <img src="/sara bot.png" alt="AI Agent" className="w-full h-full object-cover" />
        </div>
      )}
      
      <div className={`w-full max-w-[95%] lg:max-w-[85%] ${isUser ? 'order-2 flex flex-col items-end' : 'order-1 flex flex-col items-start'}`}>
        {hasItinerary ? (
          <ItineraryTimeline text={message.text} isUser={isUser} />
        ) : (
          <div 
            className={`p-5 shadow-sm text-[19px] md:text-[20px] w-fit ${
              isUser 
                ? 'bg-brand text-white rounded-3xl rounded-tr-sm' 
                : 'bg-white text-slate-700 rounded-3xl rounded-tl-sm border border-slate-100'
            }`}
          >
            <div className="whitespace-pre-wrap leading-relaxed">
              {renderMessageText(message.text, isUser)}
            </div>
          </div>
        )}
        
        {/* Flight Cards and Action Buttons */}
        {message.options && message.options.length > 0 && (
          <div className="mt-4 grid grid-cols-1 gap-4 w-full">
            {message.options.map((opt, i) => {
              if (opt.type === 'action_button') {
                return (
                  <div key={i} className="flex">
                    <a 
                      href={opt.url || 'https://flights.google.com'} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="inline-block w-fit text-center bg-brand text-white font-bold py-3 px-6 rounded-xl shadow hover:opacity-90 transition-opacity"
                    >
                      {opt.label}
                    </a>
                  </div>
                );
              }
              if (opt.type === 'hotel') {
                return <HotelCard key={i} hotel={{...opt, onOptionSelect}} />;
              }
              return <FlightCard key={i} option={{...opt, onOptionSelect}} />;
            })}
          </div>
        )}

        {/* Razorpay Payment Checkout Card */}
        {message.payment_details && (
          <div className="mt-4 w-full">
            <PaymentCheckoutCard 
              paymentDetails={message.payment_details} 
              onPay={onPay}
              onDirectPay={onDirectPay}
            />
          </div>
        )}

        {/* Flight Ticket */}
        {message.ticket && !message.ticket.hotel_name && (
          <div className="mt-4 w-full">
            <FlightTicket ticket={message.ticket} />
          </div>
        )}

        {/* Hotel Ticket */}
        {message.ticket && message.ticket.hotel_name && (
          <div className="mt-4 w-full">
            <HotelTicket ticket={message.ticket} />
          </div>
        )}

        {/* Post-Booking Upsell Card */}
        {message.upsell_details && (
          <div className="mt-4 w-full">
            <UpsellOfferCard 
              upsellDetails={message.upsell_details} 
              onAccept={onUpsellPay} 
              onDecline={onUpsellDecline} 
            />
          </div>
        )}

        {/* Quick Replies */}
        {!isUser && message.quick_replies && message.quick_replies.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-4 ml-1">
            {message.quick_replies.map((reply, i) => (
              <button 
                key={i} 
                onClick={() => onQuickReply && onQuickReply(reply)}
                className="px-6 py-3 bg-slate-50 border border-slate-200 text-slate-600 hover:bg-indigo-50/50 hover:border-indigo-200 hover:text-indigo-600 rounded-full text-[18px] md:text-[19px] font-semibold shadow-sm transform hover:-translate-y-0.5 active:translate-y-0 active:scale-95 transition-all duration-150"
              >
                {reply}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
