const mongoose = require('mongoose');

const PredictionSchema = new mongoose.Schema(
  {
    user: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
    symbol: { type: String, required: true },
    predictedPrice: { type: Number },
    targetDate: { type: Date },
    confidence: { type: Number },
    model: { type: String },
  },
  { timestamps: true }
);

module.exports = mongoose.model('Prediction', PredictionSchema);
