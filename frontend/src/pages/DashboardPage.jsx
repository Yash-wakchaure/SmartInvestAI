import { useAuth } from '../context/AuthContext';
import PortfolioChart from '../components/PortfolioChart';
import StatCard from '../components/StatCard';

const portfolioHistory = [
  { date: 'Jan', value: 780000 },
  { date: 'Feb', value: 820000 },
  { date: 'Mar', value: 810000 },
  { date: 'Apr', value: 860000 },
  { date: 'May', value: 905000 },
  { date: 'Jun', value: 940000 },
  { date: 'Jul', value: 980000 },
];

const topHoldings = [
  { symbol: 'AAPL', shares: 45, price: 214.5, value: 9640, allocation: 28 },
  { symbol: 'MSFT', shares: 32, price: 412.4, value: 13197, allocation: 24 },
  { symbol: 'NVDA', shares: 18, price: 124.8, value: 2247, allocation: 18 },
  { symbol: 'AMZN', shares: 27, price: 190.2, value: 5135, allocation: 16 },
  { symbol: 'GOOGL', shares: 24, price: 175.1, value: 4202, allocation: 14 },
];

function DashboardPage() {
  const { user } = useAuth();

  const totalInvestment = 780000;
  const currentValue = 980000;
  const pnl = currentValue - totalInvestment;
  const roi = ((pnl / totalInvestment) * 100).toFixed(2);

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">Overview</p>
          <h1>Welcome back, {user?.name || 'Investors'}</h1>
        </div>
        <button className="primary-btn" type="button">Add Portfolio</button>
      </div>

      <div className="stats-grid">
        <StatCard title="Total Investment" value="₹7,80,000" subtitle="Across 5 active positions" tone="purple" />
        <StatCard title="Current Value" value="₹9,80,000" subtitle="+₹2,00,000 this month" tone="green" />
        <StatCard title="Profit / Loss" value="₹2,00,000" subtitle="Net gain" tone="positive" />
        <StatCard title="ROI" value={`${roi}%`} subtitle="Annualized view" tone="info" />
      </div>

      <div className="content-grid two-column">
        <PortfolioChart data={portfolioHistory} />
        <div className="panel">
          <div className="panel-header">
            <h3>Allocation</h3>
          </div>
          <div className="allocation-list">
            {topHoldings.map((holding) => (
              <div className="allocation-item" key={holding.symbol}>
                <div className="allocation-meta">
                  <span>{holding.symbol}</span>
                  <strong>₹{holding.value.toLocaleString()}</strong>
                </div>
                <div className="progress-bar">
                  <span style={{ width: `${holding.allocation}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h3>Top Holdings</h3>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Shares</th>
                <th>Price</th>
                <th>Value</th>
                <th>Allocation</th>
              </tr>
            </thead>
            <tbody>
              {topHoldings.map((holding) => (
                <tr key={holding.symbol}>
                  <td>{holding.symbol}</td>
                  <td>{holding.shares}</td>
                  <td>₹{holding.price}</td>
                  <td>₹{holding.value.toLocaleString()}</td>
                  <td>{holding.allocation}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;
