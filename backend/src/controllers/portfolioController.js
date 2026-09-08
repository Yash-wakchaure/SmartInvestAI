const mongoose = require('mongoose');
const Portfolio = require('../models/Portfolio');
const Holding = require('../models/Holding');
const Transaction = require('../models/Transaction');

const isDbConnected = () => mongoose.connection.readyState === 1;

exports.createPortfolio = async (req, res) => {
  try {
    if (!isDbConnected()) return res.status(503).json({ success: false, message: 'Database not connected' });
    const { name, description } = req.body;
    const portfolio = new Portfolio({ user: req.user.id, name, description });
    await portfolio.save();
    return res.status(201).json({ success: true, portfolio });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

exports.getPortfolios = async (req, res) => {
  try {
    if (!isDbConnected()) return res.status(503).json({ success: false, message: 'Database not connected' });
    const portfolios = await Portfolio.find({ user: req.user.id });
    return res.json({ success: true, portfolios });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

// helper to compute portfolio summary
const computeSummary = (holdings) => {
  let invested = 0;
  let current = 0;
  const details = holdings.map((h) => {
    const qty = h.quantity || 0;
    const avg = h.avgPrice || 0;
    const cur = h.currentPrice || 0;
    const investedValue = avg * qty;
    const currentValue = cur * qty;
    const profitLoss = currentValue - investedValue;
    const roi = investedValue > 0 ? (profitLoss / investedValue) * 100 : null;
    invested += investedValue;
    current += currentValue;
    return Object.assign({}, h.toObject ? h.toObject() : h, {
      investedValue,
      currentValue,
      profitLoss,
      roi,
    });
  });
  const totalProfitLoss = current - invested;
  const totalRoi = invested > 0 ? (totalProfitLoss / invested) * 100 : null;
  return { invested, current, totalProfitLoss, totalRoi, details };
};

exports.getPortfolio = async (req, res) => {
  try {
    if (!isDbConnected()) return res.status(503).json({ success: false, message: 'Database not connected' });
    const { id } = req.params;
    const portfolio = await Portfolio.findOne({ _id: id, user: req.user.id });
    if (!portfolio) return res.status(404).json({ success: false, message: 'Portfolio not found' });

    const holdings = await Holding.find({ portfolio: portfolio._id });
    const transactions = await Transaction.find({ portfolio: portfolio._id }).sort({ executedAt: -1 });
    const summary = computeSummary(holdings);
    return res.json({ success: true, portfolio, holdings: summary.details, transactions, summary: { invested: summary.invested, current: summary.current, profitLoss: summary.totalProfitLoss, roi: summary.totalRoi } });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

// Add or update holding (upsert by symbol)
exports.addOrUpdateHolding = async (req, res) => {
  try {
    if (!isDbConnected()) return res.status(503).json({ success: false, message: 'Database not connected' });
    const { id } = req.params; // portfolio id
    const { symbol, quantity, averageBuyPrice, avgPrice, currentPrice } = req.body;
    const qty = Number(quantity || 0);
    const price = averageBuyPrice || avgPrice || 0;

    const portfolio = await Portfolio.findOne({ _id: id, user: req.user.id });
    if (!portfolio) return res.status(404).json({ success: false, message: 'Portfolio not found' });

    let holding = await Holding.findOne({ portfolio: id, symbol: symbol.toUpperCase() });
    if (holding) {
      // update weighted average and quantity
      const oldQty = holding.quantity || 0;
      const oldAvg = holding.avgPrice || 0;
      const newQty = oldQty + qty;
      const newAvg = newQty > 0 ? ((oldAvg * oldQty) + price * qty) / newQty : 0;
      holding.quantity = newQty;
      holding.avgPrice = newAvg;
      if (currentPrice !== undefined) holding.currentPrice = currentPrice;
      await holding.save();
    } else {
      holding = new Holding({ portfolio: id, symbol: symbol.toUpperCase(), quantity: qty, avgPrice: price, currentPrice });
      await holding.save();
    }

    return res.status(200).json({ success: true, holding });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

exports.updateHolding = async (req, res) => {
  try {
    if (!isDbConnected()) return res.status(503).json({ success: false, message: 'Database not connected' });
    const { id, holdingId } = req.params;
    const updates = req.body;
    const portfolio = await Portfolio.findOne({ _id: id, user: req.user.id });
    if (!portfolio) return res.status(404).json({ success: false, message: 'Portfolio not found' });
    const holding = await Holding.findOne({ _id: holdingId, portfolio: id });
    if (!holding) return res.status(404).json({ success: false, message: 'Holding not found' });
    Object.assign(holding, updates);
    await holding.save();
    return res.json({ success: true, holding });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

exports.removeHolding = async (req, res) => {
  try {
    if (!isDbConnected()) return res.status(503).json({ success: false, message: 'Database not connected' });
    const { id, holdingId } = req.params;
    const portfolio = await Portfolio.findOne({ _id: id, user: req.user.id });
    if (!portfolio) return res.status(404).json({ success: false, message: 'Portfolio not found' });
    const holding = await Holding.findOneAndDelete({ _id: holdingId, portfolio: id });
    if (!holding) return res.status(404).json({ success: false, message: 'Holding not found' });
    return res.json({ success: true, holding });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

// Record a transaction and update holdings accordingly
exports.recordTransaction = async (req, res) => {
  try {
    if (!isDbConnected()) return res.status(503).json({ success: false, message: 'Database not connected' });
    const { id } = req.params; // portfolio id
    const { symbol, type, quantity, price } = req.body;
    const qty = Number(quantity || 0);
    const unitPrice = Number(price || 0);
    if (!symbol || !type || qty <= 0 || unitPrice <= 0) return res.status(400).json({ success: false, message: 'Invalid transaction data' });

    const portfolio = await Portfolio.findOne({ _id: id, user: req.user.id });
    if (!portfolio) return res.status(404).json({ success: false, message: 'Portfolio not found' });

    // create transaction
    const txn = new Transaction({ portfolio: id, symbol: symbol.toUpperCase(), type, quantity: qty, price: unitPrice });
    await txn.save();

    // update holding
    let holding = await Holding.findOne({ portfolio: id, symbol: symbol.toUpperCase() });
    if (type === 'buy') {
      if (holding) {
        const oldQty = holding.quantity || 0;
        const oldAvg = holding.avgPrice || 0;
        const newQty = oldQty + qty;
        const newAvg = newQty > 0 ? ((oldAvg * oldQty) + unitPrice * qty) / newQty : 0;
        holding.quantity = newQty;
        holding.avgPrice = newAvg;
        holding.currentPrice = unitPrice; // optional: set to latest
        await holding.save();
      } else {
        holding = new Holding({ portfolio: id, symbol: symbol.toUpperCase(), quantity: qty, avgPrice: unitPrice, currentPrice: unitPrice });
        await holding.save();
      }
    } else if (type === 'sell') {
      if (!holding) return res.status(400).json({ success: false, message: 'No holding to sell' });
      const oldQty = holding.quantity || 0;
      const newQty = oldQty - qty;
      if (newQty < 0) return res.status(400).json({ success: false, message: 'Sell quantity exceeds holding' });
      if (newQty === 0) {
        await Holding.deleteOne({ _id: holding._id });
      } else {
        holding.quantity = newQty;
        holding.currentPrice = unitPrice;
        await holding.save();
      }
    } else {
      return res.status(400).json({ success: false, message: 'Invalid transaction type' });
    }

    return res.status(201).json({ success: true, transaction: txn, holding });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

exports.getHolding = async (req, res) => {
  try {
    if (!isDbConnected()) return res.status(503).json({ success: false, message: 'Database not connected' });
    const { id, symbol } = req.params;
    const portfolio = await Portfolio.findOne({ _id: id, user: req.user.id });
    if (!portfolio) return res.status(404).json({ success: false, message: 'Portfolio not found' });
    const holding = await Holding.findOne({ portfolio: id, symbol: symbol.toUpperCase() });
    if (!holding) return res.status(404).json({ success: false, message: 'Holding not found' });
    const investedValue = (holding.avgPrice || 0) * (holding.quantity || 0);
    const currentValue = (holding.currentPrice || 0) * (holding.quantity || 0);
    const profitLoss = currentValue - investedValue;
    const roi = investedValue > 0 ? (profitLoss / investedValue) * 100 : null;
    return res.json({ success: true, holding: Object.assign({}, holding.toObject(), { investedValue, currentValue, profitLoss, roi }) });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};
