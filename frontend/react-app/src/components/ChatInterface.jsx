import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, MapPin, Menu } from 'lucide-react';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';

// Simple random string generator
const generateId = () => Math.random().toString(36).substring(2, 15);

const ChatInterface = ({ onFlowChange }) => {
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'bot',
      text: "Hi there! I'm Sara, your AI travel companion. I can help you find flights, book hotels, and plan custom itineraries. Where would you like to go today?",
    }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);
  const [sessionId, setSessionId] = useState(generateId());
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const isInitialState = !hasStarted && messages.length === 1;
  useEffect(() => {
    if (isInitialState && onFlowChange) {
      onFlowChange(null);
    }
  }, [isInitialState, onFlowChange]);

  const sendMessage = async (text) => {
    if (!text.trim()) return;
    setHasStarted(true);

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      text: text.trim()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);

    try {
      const response = await axios.post('http://localhost:8000/api/chat', {
        message: userMessage.text,
        session_id: sessionId
      });

      if (response.data.current_flow && onFlowChange) {
        onFlowChange(response.data.current_flow);
      }

      const botMessage = {
        id: Date.now() + 1,
        sender: 'bot',
        text: response.data.message,
        options: response.data.followup_message ? [] : response.data.options,  // no options on decline msg
        quick_replies: response.data.followup_message ? [] : response.data.quick_replies,
        ticket: response.data.ticket,
        payment_details: response.data.payment_details,
        upsell_details: response.data.upsell_details
      };

      setMessages(prev => [...prev, botMessage]);

      // If there's a followup (e.g. booking step reminder after a decline), render it as a second bubble
      if (response.data.followup_message) {
        setTimeout(() => {
          const followupMessage = {
            id: Date.now() + 2,
            sender: 'bot',
            text: response.data.followup_message,
            options: response.data.options,
            quick_replies: response.data.followup_quick_replies || response.data.quick_replies,
            ticket: null
          };
          setMessages(prev => [...prev, followupMessage]);
        }, 600);
      }

    } catch (error) {
      console.error("Error communicating with chat API:", error);
      const errorMessage = {
        id: Date.now() + 1,
        sender: 'bot',
        text: "I'm sorry, I'm having trouble connecting to my servers right now."
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleRazorpayCheckout = (paymentDetails) => {
    if (!window.Razorpay) {
      alert("Razorpay payment gateway SDK is loading. Please check your internet connection.");
      return;
    }

    const options = {
      key: paymentDetails.key_id,
      amount: paymentDetails.amount,
      currency: paymentDetails.currency || 'INR',
      name: 'Sara Travel Assistant',
      description: paymentDetails.item_name || 'Travel Booking Checkout',
      order_id: paymentDetails.order_id,
      prefill: {
        email: paymentDetails.customer_email || 'traveler@example.com',
        contact: paymentDetails.customer_phone || '9876543210'
      },
      notes: {
        session_id: sessionId,
        booking_type: paymentDetails.booking_type || 'travel'
      },
      theme: {
        color: '#004e92'
      },
      handler: async function (res) {
        setIsTyping(true);
        try {
          const verifyRes = await axios.post('http://localhost:8000/api/payment/verify', {
            session_id: sessionId,
            razorpay_order_id: res.razorpay_order_id,
            razorpay_payment_id: res.razorpay_payment_id,
            razorpay_signature: res.razorpay_signature,
            is_upsell: false
          });

          const botMessage = {
            id: Date.now() + 1,
            sender: 'bot',
            text: verifyRes.data.message || "🎉 Payment confirmed! Your booking is complete and your ticket has been emailed to you.",
            ticket: verifyRes.data.ticket,
            upsell_details: verifyRes.data.upsell_details,
            quick_replies: ["Book another flight", "Book a hotel", "Plan an itinerary"]
          };
          setMessages(prev => [...prev, botMessage]);
        } catch (err) {
          console.error("Payment verification failed:", err);
          setMessages(prev => [...prev, {
            id: Date.now() + 1,
            sender: 'bot',
            text: "⚠️ Payment verification encountered an issue. Please check your dashboard or contact support."
          }]);
        } finally {
          setIsTyping(false);
        }
      },
      modal: {
        ondismiss: async function () {
          try {
            await axios.post('http://localhost:8000/api/payment/failure', {
              session_id: sessionId,
              order_id: paymentDetails.order_id,
              error_code: 'MODAL_DISMISSED',
              error_description: 'User dismissed Razorpay checkout modal'
            });
          } catch (e) {}
        }
      }
    };

    const rzp = new window.Razorpay(options);
    rzp.on('payment.failed', async function (response) {
      try {
        await axios.post('http://localhost:8000/api/payment/failure', {
          session_id: sessionId,
          order_id: response.error?.metadata?.order_id || paymentDetails.order_id,
          error_code: response.error?.code || 'PAYMENT_FAILED',
          error_description: response.error?.description || 'Payment failed'
        });
      } catch (e) {}
    });
    rzp.open();
  };

  const handleDirectPaymentVerification = async (paymentDetails) => {
    setIsTyping(true);
    try {
      const verifyRes = await axios.post('http://localhost:8000/api/payment/verify', {
        session_id: sessionId,
        razorpay_order_id: paymentDetails.order_id,
        razorpay_payment_id: 'pay_test_' + Date.now(),
        razorpay_signature: 'mock_signature',
        is_upsell: false
      });

      const botMessage = {
        id: Date.now() + 1,
        sender: 'bot',
        text: verifyRes.data.message || "🎉 Payment confirmed! Your booking is complete and your ticket has been emailed to you.",
        ticket: verifyRes.data.ticket,
        upsell_details: verifyRes.data.upsell_details,
        quick_replies: ["Book another flight", "Book a hotel", "Plan an itinerary"]
      };
      setMessages(prev => [...prev, botMessage]);
    } catch (err) {
      console.error("Payment verification failed:", err);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        sender: 'bot',
        text: "⚠️ Payment verification encountered an issue. Please check your connection or contact support."
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleUpsellCheckout = (upsellDetails) => {
    if (!window.Razorpay) {
      alert("Razorpay payment gateway SDK is loading.");
      return;
    }

    const options = {
      key: upsellDetails.key_id,
      amount: Math.round((upsellDetails.price_rupees || 499) * 100),
      currency: 'INR',
      name: 'Sara Travel Add-on',
      description: upsellDetails.title,
      order_id: upsellDetails.order_id,
      theme: {
        color: '#d97706'
      },
      handler: async function (res) {
        setIsTyping(true);
        try {
          const verifyRes = await axios.post('http://localhost:8000/api/payment/verify', {
            session_id: sessionId,
            razorpay_order_id: res.razorpay_order_id,
            razorpay_payment_id: res.razorpay_payment_id,
            razorpay_signature: res.razorpay_signature,
            is_upsell: true,
            upsell_type: upsellDetails.category
          });

          // Update previous ticket to display add-on
          setMessages(prev => prev.map(m => {
            if (m.ticket) {
              return { ...m, ticket: verifyRes.data.ticket, upsell_details: null };
            }
            return m;
          }));

          const botMessage = {
            id: Date.now() + 1,
            sender: 'bot',
            text: `✨ Fantastic! ${upsellDetails.title} has been confirmed and attached to your booking.`,
            ticket: verifyRes.data.ticket,
            quick_replies: ["Book another flight", "Book a hotel", "Plan an itinerary"]
          };
          setMessages(prev => [...prev, botMessage]);
        } catch (err) {
          console.error("Upsell verification failed:", err);
        } finally {
          setIsTyping(false);
        }
      }
    };

    const rzp = new window.Razorpay(options);
    rzp.open();
  };

  const handleUpsellDecline = () => {
    setMessages(prev => prev.map(m => ({ ...m, upsell_details: null })));
  };

  const handleMenuOption = async (option) => {
    setIsMenuOpen(false);
    setHasStarted(true);
    if (onFlowChange) {
      onFlowChange(option);
    }
    let activeSessionId = sessionId;
    if (option === "Flight Booking" || option === "Itinerary Plan") {
      activeSessionId = generateId();
      setSessionId(activeSessionId);
    }
    
    setMessages([]);
    setIsTyping(true);
    
    let triggerMsg = "";
    if (option === "Flight Booking") triggerMsg = "Book a flight";
    else if (option === "Hotel Booking") triggerMsg = "Book a hotel";
    else triggerMsg = "Plan an itinerary";
    
    try {
      const response = await axios.post('http://localhost:8000/api/chat', {
        message: triggerMsg,
        session_id: activeSessionId
      });

      if (response.data.current_flow && onFlowChange) {
        onFlowChange(response.data.current_flow);
      }

      const botMessage = {
        id: Date.now(),
        sender: 'bot',
        text: response.data.message,
        options: response.data.options,
        quick_replies: response.data.quick_replies,
        ticket: response.data.ticket,
        payment_details: response.data.payment_details,
        upsell_details: response.data.upsell_details
      };

      setMessages([botMessage]);
    } catch (error) {
      console.error("Error communicating with chat API:", error);
      const errorMessage = {
        id: Date.now(),
        sender: 'bot',
        text: "I'm sorry, I'm having trouble connecting to my servers right now.",
        isError: true
      };
      setMessages([errorMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleSend = (e) => {
    e.preventDefault();
    sendMessage(input);
  };

  const samplePrompts = [
    "Flights to Goa this weekend",
    "Hotels near Marina Beach Chennai",
    "I want to go to Tokyo in June"
  ];



  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 18) return "Good afternoon";
    return "Good evening";
  };

  if (isInitialState) {
    return (
      <div className="flex flex-col h-full bg-slate-50/50 items-center justify-center p-6">
        <div className="w-full max-w-3xl flex flex-col items-center animate-fade-in-up">
          <h2 className="text-4xl font-serif text-gray-800 mb-8">{getGreeting()}, how can I help you?</h2>
          
          {isMenuOpen && (
            <div className="fixed inset-0 z-40" onClick={() => setIsMenuOpen(false)} />
          )}
          <form onSubmit={handleSend} className="relative flex items-center w-full mb-8 shadow-lg rounded-full z-50">
            <button
              type="button"
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="absolute left-4 p-2 text-slate-400 hover:text-slate-600 focus:outline-none z-20"
            >
              <Menu className="w-6 h-6 text-brand" />
            </button>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Where would you like to travel today?"
              className="w-full pl-14 pr-16 py-5 rounded-full border border-gray-200 focus:border-brand focus:ring-2 focus:ring-brand/20 outline-none text-gray-700 text-lg transition-all"
              disabled={isTyping}
            />
            <button
              type="submit"
              disabled={!input.trim() || isTyping}
              className="absolute right-3 p-3.5 bg-brand text-white rounded-full hover:bg-brand-dark disabled:opacity-50 disabled:hover:bg-brand transition-colors shadow-md"
            >
              <Send className="w-6 h-6" />
            </button>

            {isMenuOpen && (
              <div className="absolute bottom-20 left-4 bg-white border border-slate-200 rounded-2xl shadow-xl p-2 w-56 z-50 flex flex-col gap-1 text-left">
                <div className="text-[10px] text-slate-400 font-bold px-3 py-1.5 uppercase tracking-wider">Booking Options</div>
                <button
                  type="button"
                  onClick={() => handleMenuOption("Flight Booking")}
                  className="w-full text-left px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-brand rounded-xl transition-colors flex items-center gap-2"
                >
                  ✈️ Flight Booking
                </button>
                <button
                  type="button"
                  onClick={() => handleMenuOption("Hotel Booking")}
                  className="w-full text-left px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-brand rounded-xl transition-colors flex items-center gap-2"
                >
                  🏨 Hotel Booking
                </button>
                <button
                  type="button"
                  onClick={() => handleMenuOption("Itinerary Plan")}
                  className="w-full text-left px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-brand rounded-xl transition-colors flex items-center gap-2"
                >
                  🗺️ Itinerary Plan
                </button>
              </div>
            )}
          </form>

          <div className="flex flex-wrap justify-center gap-3 w-full">
            {samplePrompts.map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => setInput(prompt)}
                className="px-5 py-2.5 bg-white border border-gray-200 text-gray-600 rounded-full text-sm font-medium hover:bg-gray-50 transition-colors flex items-center gap-2 shadow-sm"
              >
                <MapPin className="w-4 h-4 text-brand" />
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-50/50">
      <div className="flex-1 overflow-y-auto p-6 scroll-smooth">
        {messages.map((msg, index) => (
          <MessageBubble 
            key={msg.id} 
            message={msg} 
            onQuickReply={sendMessage} 
            onOptionSelect={(option, flightClass, price) => {
              if (option.type === 'hotel') {
                sendMessage(`I would like to select hotel ${option.name} for ${price}`);
              } else {
                sendMessage(`I would like to select ${flightClass} class on ${option.airline_name} ${option.flight_numbers} for ${price}`);
              }
            }}
            onPay={handleRazorpayCheckout}
            onDirectPay={handleDirectPaymentVerification}
            onUpsellPay={handleUpsellCheckout}
            onUpsellDecline={handleUpsellDecline}
          />
        ))}
        {isTyping && (
          <div className="mb-6">
            <TypingIndicator />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 bg-white border-t border-slate-200">
        {isMenuOpen && (
          <div className="fixed inset-0 z-40" onClick={() => setIsMenuOpen(false)} />
        )}
        <form onSubmit={handleSend} className="relative flex items-center z-50">
          <button
            type="button"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="absolute left-3 p-1.5 text-slate-400 hover:text-slate-600 focus:outline-none z-20"
          >
            <Menu className="w-5 h-5 text-brand" />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your travel request here..."
            className="w-full pl-12 pr-14 py-4 rounded-full border border-slate-200 focus:border-brand focus:ring-2 focus:ring-brand/20 outline-none text-slate-700 shadow-sm transition-all"
            disabled={isTyping}
          />
          <button
            type="submit"
            disabled={!input.trim() || isTyping}
            className="absolute right-2 p-3 bg-brand text-white rounded-full hover:bg-brand-dark disabled:opacity-50 disabled:hover:bg-brand transition-colors shadow-md"
          >
            <Send className="w-5 h-5" />
          </button>

          {isMenuOpen && (
            <div className="absolute bottom-16 left-2 bg-white border border-slate-200 rounded-2xl shadow-xl p-2 w-56 z-50 flex flex-col gap-1 text-left">
              <div className="text-[10px] text-slate-400 font-bold px-3 py-1.5 uppercase tracking-wider">Booking Options</div>
              <button
                type="button"
                onClick={() => handleMenuOption("Flight Booking")}
                className="w-full text-left px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-brand rounded-xl transition-colors flex items-center gap-2"
              >
                ✈️ Flight Booking
              </button>
              <button
                type="button"
                onClick={() => handleMenuOption("Hotel Booking")}
                className="w-full text-left px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-brand rounded-xl transition-colors flex items-center gap-2"
              >
                🏨 Hotel Booking
              </button>
              <button
                type="button"
                onClick={() => handleMenuOption("Itinerary Plan")}
                className="w-full text-left px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-brand rounded-xl transition-colors flex items-center gap-2"
              >
                🗺️ Itinerary Plan
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
};

export default ChatInterface;
