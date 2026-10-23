const jwt = require('jsonwebtoken');
const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const User = require('../models/User');

const inMemoryUsers = [];

const isDbConnected = () => mongoose.connection.readyState === 1;
const normalizeEmail = (email = '') => String(email).trim().toLowerCase();

const makeMemoryUser = async ({ name, email, password }) => {
  const hashedPassword = await bcrypt.hash(password, 10);
  const user = {
    _id: new mongoose.Types.ObjectId().toString(),
    name,
    email: normalizeEmail(email),
    password: hashedPassword,
    role: 'user',
    createdAt: new Date(),
    updatedAt: new Date(),
    comparePassword(candidatePassword) {
      return bcrypt.compare(candidatePassword, this.password);
    },
    toJSON() {
      const { password, ...safeUser } = this;
      return safeUser;
    },
  };

  return user;
};

const findMemoryUserByEmail = async (email) => {
  const normalizedEmail = normalizeEmail(email);
  return inMemoryUsers.find((user) => user.email === normalizedEmail) || null;
};

const findMemoryUserById = async (id) => {
  return inMemoryUsers.find((user) => user._id.toString() === id.toString()) || null;
};

const signToken = (user) => {
  const payload = { id: user._id, email: user.email };
  const secret = process.env.JWT_SECRET || 'dev-secret-key';
  const options = { expiresIn: '1h' };
  return jwt.sign(payload, secret, options);
};

exports.register = async (req, res) => {
  try {
    const { name, email, password } = req.body;
    if (!name || !email || !password) {
      return res.status(400).json({ success: false, message: 'Missing required fields' });
    }

    if (isDbConnected()) {
      const existing = await User.findOne({ email: normalizeEmail(email) });
      if (existing) {
        return res.status(409).json({ success: false, message: 'Email already registered' });
      }

      const user = new User({ name, email: normalizeEmail(email), password });
      await user.save();

      const token = signToken(user);
      return res.status(201).json({ success: true, user: user.toJSON(), token });
    }

    const existing = await findMemoryUserByEmail(email);
    if (existing) {
      return res.status(409).json({ success: false, message: 'Email already registered' });
    }

    const user = await makeMemoryUser({ name, email, password });
    inMemoryUsers.push(user);

    const token = signToken(user);
    return res.status(201).json({ success: true, user: user.toJSON(), token });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

exports.login = async (req, res) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) {
      return res.status(400).json({ success: false, message: 'Missing email or password' });
    }

    if (isDbConnected()) {
      const user = await User.findOne({ email: normalizeEmail(email) });
      if (!user) return res.status(401).json({ success: false, message: 'Invalid credentials' });

      const isMatch = await user.comparePassword(password);
      if (!isMatch) return res.status(401).json({ success: false, message: 'Invalid credentials' });

      const token = signToken(user);
      return res.json({ success: true, user: user.toJSON(), token });
    }

    const user = await findMemoryUserByEmail(email);
    if (!user) return res.status(401).json({ success: false, message: 'Invalid credentials' });

    const isMatch = await user.comparePassword(password);
    if (!isMatch) return res.status(401).json({ success: false, message: 'Invalid credentials' });

    const token = signToken(user);
    return res.json({ success: true, user: user.toJSON(), token });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};

exports.profile = async (req, res) => {
  try {
    if (isDbConnected()) {
      const user = await User.findById(req.user.id).select('-password');
      if (!user) return res.status(404).json({ success: false, message: 'User not found' });
      return res.json({ success: true, user });
    }

    const user = await findMemoryUserById(req.user.id);
    if (!user) return res.status(404).json({ success: false, message: 'User not found' });
    return res.json({ success: true, user: user.toJSON() });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error' });
  }
};
