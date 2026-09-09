import api from './api';

export const portfolioService = {
  getPortfolios: async () => {
    const response = await api.get('/portfolios');
    return response.data;
  },

  createPortfolio: async (portfolioData) => {
    const response = await api.post('/portfolios', portfolioData);
    return response.data;
  },

  getPortfolio: async (portfolioId) => {
    const response = await api.get(`/portfolios/${portfolioId}`);
    return response.data;
  },

  addHolding: async (portfolioId, holding) => {
    const response = await api.post(`/portfolios/${portfolioId}/holdings`, holding);
    return response.data;
  },

  addTransaction: async (portfolioId, transaction) => {
    const response = await api.post(`/portfolios/${portfolioId}/transactions`, transaction);
    return response.data;
  },
};
