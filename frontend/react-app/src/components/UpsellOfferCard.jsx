import React, { useState } from 'react';
import { Sparkles, PlusCircle, X, ShieldCheck, Car, Check, Loader2, Zap } from 'lucide-react';

const cleanTitle = (rawTitle) => {
  if (!rawTitle) return '';
  // Remove leading emojis so we don't have duplicates alongside our custom icon
  return rawTitle.replace(/^[\s\p{Emoji}\u200d]+/gu, '').trim();
};

const UpsellOfferCard = ({ upsellDetails, onAccept, onDecline }) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  if (!upsellDetails || dismissed) return null;

  const handleAcceptClick = async () => {
    setIsProcessing(true);
    try {
      if (onAccept) {
        await onAccept(upsellDetails);
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDeclineClick = () => {
    setDismissed(true);
    if (onDecline) {
      onDecline(upsellDetails);
    }
  };

  const isInsurance = upsellDetails.category === 'insurance' || (upsellDetails.title && upsellDetails.title.toLowerCase().includes('insurance'));
  const isTransfer = upsellDetails.category === 'transfer' || (upsellDetails.title && upsellDetails.title.toLowerCase().includes('transfer'));

  const priceFormatted = upsellDetails.price_rupees
    ? Number(upsellDetails.price_rupees).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '0.00';

  const titleText = cleanTitle(upsellDetails.title) || (isInsurance ? 'Comprehensive Travel & Baggage Insurance' : 'VIP Airport Pick-up & Transfer');

  // Value props chips
  const perks = isInsurance
    ? ['Coverage up to ₹5 Lakhs', '24/7 Medical Support', 'Instant Policy ID']
    : ['Dedicated Chauffeur', 'Flight Delay Guarantee', 'Zero Waiting Time'];

  return (
    <div className="w-full max-w-lg my-4 bg-white border border-amber-200/90 rounded-3xl shadow-xl overflow-hidden animate-fade-in-up transition-all duration-300 hover:shadow-2xl hover:border-amber-300">
      
      {/* Top Banner Header */}
      <div className="bg-gradient-to-r from-amber-500 via-amber-600 to-orange-600 text-white px-5 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1 bg-white/20 rounded-lg backdrop-blur-md">
            <Sparkles className="w-4 h-4 text-amber-100 animate-pulse" />
          </div>
          <div>
            <span className="text-xs font-black uppercase tracking-wider block leading-none">
              Exclusive Post-Booking Offer
            </span>
            <span className="text-[10px] text-amber-100/90 font-medium">Special traveler rate applied</span>
          </div>
        </div>
        <button
          onClick={handleDeclineClick}
          className="text-white/80 hover:text-white p-1.5 rounded-full hover:bg-white/20 transition-all active:scale-95"
          title="Dismiss Offer"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Main Body */}
      <div className="p-5 space-y-4">
        <div className="flex items-start gap-3.5">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-100 to-orange-100 border border-amber-200/80 flex items-center justify-center text-amber-700 flex-shrink-0 shadow-sm mt-0.5">
            {isInsurance ? <ShieldCheck className="w-6 h-6 text-amber-600" /> : (isTransfer ? <Car className="w-6 h-6 text-amber-600" /> : <Sparkles className="w-6 h-6 text-amber-600" />)}
          </div>
          
          <div className="flex-1 min-w-0">
            <h4 className="font-extrabold text-slate-800 text-base leading-tight">
              {titleText}
            </h4>
            <p className="text-xs text-slate-500 leading-relaxed mt-1">
              {upsellDetails.description}
            </p>
          </div>
        </div>

        {/* Feature Benefit Chips */}
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {perks.map((perk, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200/60">
              <Check className="w-3 h-3 text-amber-600" />
              {perk}
            </span>
          ))}
        </div>

        {/* Pricing Summary Box */}
        <div className="bg-slate-50/90 border border-slate-100 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <span className="text-[11px] uppercase tracking-wider font-bold text-slate-400 block">Add-on Special Price</span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-xs text-slate-400 line-through">₹{(upsellDetails.price_rupees * 1.6).toFixed(0)}</span>
              <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">SAVE 40%</span>
            </div>
          </div>
          <div className="text-right">
            <span className="text-2xl font-black text-slate-900 leading-none">₹{priceFormatted}</span>
            <span className="text-[10px] text-slate-400 block font-medium mt-1">All taxes included</span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2.5 pt-1">
          <button
            onClick={handleAcceptClick}
            disabled={isProcessing}
            className="flex-1 py-3.5 px-5 rounded-2xl bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 hover:from-amber-600 hover:to-orange-600 text-white font-bold text-sm shadow-md hover:shadow-lg transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-60 group active:scale-[0.99]"
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Processing Razorpay Checkout...</span>
              </>
            ) : (
              <>
                <Zap className="w-4 h-4 text-amber-200 transition-transform group-hover:scale-110" />
                <span>Add to Booking for ₹{priceFormatted}</span>
              </>
            )}
          </button>
          
          <button
            onClick={handleDeclineClick}
            disabled={isProcessing}
            className="py-3.5 px-4 rounded-2xl bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold text-sm transition-colors active:scale-95"
          >
            No thanks
          </button>
        </div>
      </div>
    </div>
  );
};

export default UpsellOfferCard;
