const express = require('express');
const router = express.Router();
const portfolioController = require('../controllers/portfolioController');
const authMiddleware = require('../middleware/authMiddleware');

// All portfolio routes are protected
router.use(authMiddleware);

router.post('/', portfolioController.createPortfolio);
router.get('/', portfolioController.getPortfolios);
router.get('/:id', portfolioController.getPortfolio);

router.post('/:id/holdings', portfolioController.addOrUpdateHolding);
router.put('/:id/holdings/:holdingId', portfolioController.updateHolding);
router.delete('/:id/holdings/:holdingId', portfolioController.removeHolding);
router.get('/:id/holdings/:symbol', portfolioController.getHolding);

router.post('/:id/transactions', portfolioController.recordTransaction);

module.exports = router;
