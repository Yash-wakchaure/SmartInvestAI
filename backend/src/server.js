const express = require("express");
const cors = require("cors");
require("dotenv").config();

// connect to database (if configured)
const connectDB = require("./config/db");

const app = express();

const PORT = process.env.PORT || 5000;

app.use(cors());
app.use(express.json());

app.get("/api/health", (req, res) => {
  res.status(200).json({
    success: true,
    message: "SmartInvest AI Backend is running",
  });
});

// attempt DB connection if MONGO_URI is provided
if (process.env.MONGO_URI) {
  connectDB().catch((err) => console.error('DB connection failed:', err.message));
} else {
  console.warn('MONGO_URI not set — running without MongoDB');
}

// Mount auth routes
app.use('/api/auth', require('./routes/authRoutes'));
app.use('/api/portfolios', require('./routes/portfolioRoutes'));

app.listen(PORT, () => {
  console.log(`SmartInvest AI server running on port ${PORT}`);
});
