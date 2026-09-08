const mongoose = require('mongoose');
require('dotenv').config();

const connectDB = async () => {
  const uri = process.env.MONGO_URI;
  if (!uri) {
    console.warn('MONGO_URI is not defined in environment. Skipping MongoDB connection.');
    return;
  }

  try {
    await mongoose.connect(uri, {
      // options are kept minimal; mongoose v6+ uses sensible defaults
    });
    console.log('MongoDB connected');
  } catch (err) {
    console.error('MongoDB connection error:', err.message);
    throw err;
  }
};

module.exports = connectDB;
