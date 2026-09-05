import React, { useState } from 'react';
import { ShieldCheck, Lock, CreditCard, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

const PaymentCheckoutCard = ({ paymentDetails, onPay }) => {
  const [isProcessing, setIsProcessing] = useState(false);

  if (!paymentDetails) return null;

  const handlePayClick = async () => {
    setIsProcessing(true);
    try {
      if (onPay) {
        await onPay(paymentDetails);
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const formattedAmount = paymentDetails.amount_rupees 
    ? Number(paymentDetails.amount_rupees).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : (paymentDetails.amount ? (paymentDetails.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00');

  return (
    <div className="w-full max-w-lg my-3 bg-white border border-slate-200/80 rounded-2xl shadow-lg overflow-hidden transition-all duration-300 hover:shadow-xl">
      {/* Top Header */}
      <div className="bg-gradient-to-r from-[#002f6c] to-[#004e92] text-white p-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-white/10 rounded-xl backdrop-blur-sm">
            <Lock className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h4 className="font-bold text-base leading-tight">Secure Payment Checkout</h4>
            <p className="text-xs text-blue-200/80 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 inline" /> Razorpay Verified Gateway
            </p>
          </div>
        </div>
        <div className="text-right">
          <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded-full">
            Gated Order
          </span>
        </div>
      </div>

      {/* Details Section */}
      <div className="p-5 space-y-4">
        <div className="flex justify-between items-start pb-3 border-b border-slate-100">
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Item Details</p>
            <p className="text-base font-bold text-slate-800 mt-0.5">{paymentDetails.item_name || 'Travel Booking'}</p>
            {paymentDetails.passenger_count && (
              <p className="text-xs text-slate-500 mt-0.5">
                {paymentDetails.passenger_count} Passenger{paymentDetails.passenger_count > 1 ? 's' : ''}
              </p>
            )}
          </div>
          <div className="text-right">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Order ID</p>
            <p className="text-xs font-mono font-bold text-slate-600 mt-0.5">
              {paymentDetails.order_id ? paymentDetails.order_id.substring(0, 14) + '...' : 'Generated'}
            </p>
          </div>
        </div>

        {/* Amount Summary */}
        <div className="bg-slate-50 rounded-xl p-4 flex items-center justify-between border border-slate-100">
          <div className="flex items-center gap-2">
            <CreditCard className="w-5 h-5 text-slate-500" />
            <span className="text-sm font-semibold text-slate-600">Total Payable Amount</span>
          </div>
          <div className="text-right">
            <span className="text-2xl font-extrabold text-[#004e92]">₹{formattedAmount}</span>
            <span className="text-xs text-slate-500 block font-medium">INR (All taxes incl.)</span>
          </div>
        </div>

        {/* Pay Button */}
        <button
          onClick={handlePayClick}
          disabled={isProcessing}
          className="w-full py-3.5 px-6 rounded-xl bg-gradient-to-r from-[#004e92] to-[#000428] hover:from-[#003d73] hover:to-[#000320] text-white font-bold text-base shadow-md hover:shadow-lg transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed group active:scale-[0.99]"
        >
          {isProcessing ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>Opening Razorpay Gateway...</span>
            </>
          ) : (
            <>
              <Lock className="w-4 h-4 text-emerald-400 transition-transform group-hover:scale-110" />
              <span>Pay ₹{formattedAmount} with Razorpay</span>
            </>
          )}
        </button>

        {/* Trust Badges */}
        <div className="flex items-center justify-center gap-4 text-[11px] text-slate-400 pt-1">
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Instant Ticket Confirmation
          </span>
          <span>•</span>
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> 256-bit SSL Security
          </span>
        </div>
      </div>
    </div>
  );
};

export default PaymentCheckoutCard;
