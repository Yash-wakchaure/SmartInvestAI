const mongoose = require("mongoose");

const connectDB = async () => {
  const uri = process.env.MONGO_URI;

  if (!uri) {
    console.warn("MongoDB is disabled or MONGO_URI is missing.");
    return false;
  }

  try {
    await mongoose.connect(uri, {
      serverSelectionTimeoutMS: 10000,
    });

    console.log("MongoDB connected successfully");
    return true;
  } catch (err) {
    console.error("MongoDB connection failed:", err.message);
    return false;
  }
};

module.exports = connectDB;