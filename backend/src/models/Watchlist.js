const mongoose = require('mongoose');

const WatchlistSchema = new mongoose.Schema(
  {
    user: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    symbols: [{ type: String }],
    name: { type: String },
  },
  { timestamps: true }
);

module.exports = mongoose.model('Watchlist', WatchlistSchema);
