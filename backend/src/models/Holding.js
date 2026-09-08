const mongoose = require('mongoose');

const HoldingSchema = new mongoose.Schema(
  {
    portfolio: { type: mongoose.Schema.Types.ObjectId, ref: 'Portfolio', required: true },
    symbol: { type: String, required: true },
    quantity: { type: Number, required: true, default: 0 },
    avgPrice: { type: Number, required: false },
  },
  { timestamps: true }
);

module.exports = mongoose.model('Holding', HoldingSchema);
