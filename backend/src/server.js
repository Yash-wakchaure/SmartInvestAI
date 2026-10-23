const dns = require("dns");
dns.setServers(["8.8.8.8"]);


const express = require("express");
const cors = require("cors");
require("dotenv").config();

const connectDB = require("./config/db");

const app = express();
const PORT = process.env.PORT || 5000;

app.use(cors());
app.use(express.json());  

// Health check
app.get("/api/health", (req, res) => {
  res.status(200).json({
    success: true,
    message: "SmartInvest AI Backend is running",
  });
});

// Connect to MongoDB
if (process.env.MONGO_URI) {
  connectDB();
} else {
  console.warn("MongoDB is disabled or MONGO_URI is missing");
}

// Routes
app.use("/api/auth", require("./routes/authRoutes"));
app.use("/api/portfolios", require("./routes/portfolioRoutes"));

app.listen(PORT, () => {
  console.log(`SmartInvest AI server running on port ${PORT}`);
});