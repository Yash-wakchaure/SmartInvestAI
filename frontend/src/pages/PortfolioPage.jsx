import PortfolioChart from '../components/PortfolioChart';
import StatCard from '../components/StatCard';

const portfolioHistory = [
  { date: 'Jan', value: 640000 },
  { date: 'Feb', value: 670000 },
  { date: 'Mar', value: 690000 },
  { date: 'Apr', value: 720000 },
  { date: 'May', value: 760000 },
  { date: 'Jun', value: 821000 },
  { date: 'Jul', value: 865000 },
];

const holdings = [
  { symbol: 'AAPL', qty: 60, avg: 196, ltp: 214.5, value: 12870, pnl: 1110 },
  { symbol: 'MSFT', qty: 28, avg: 394, ltp: 412.4, value: 11547, pnl: 515 },
  { symbol: 'NXPI', qty: 150, avg: 178, ltp: 183.2, value: 27480, pnl: 780 },
  { symbol: 'AMZN', qty: 38, avg: 182, ltp: 190.2, value: 7227, pnl: 312 },
];

function PortfolioPage() {
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">Portfolio</p>
          <h1>Primary Investments</h1>
        </div>
        <button className="primary-btn" type="button">New Position</button>
      </div>

      <div className="stats-grid">
        <StatCard title="Invested" value="₹6,50,000" subtitle="Total capital deployed" tone="purple" />
        <StatCard title="Market Value" value="₹8,65,000" subtitle="Current portfolio value" tone="green" />
        <StatCard title="Gain" value="₹2,15,000" subtitle="Unrealized profit" tone="positive" />
        <StatCard title="Daily Return" value="1.36%" subtitle="Based on current prices" tone="info" />
      </div>

      <PortfolioChart data={portfolioHistory} />

      <div className="panel">
        <div className="panel-header">
          <h3>Holdings</h3>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th>Avg Cost</th>
                <th>LTP</th>
                <th>Value</th>
                <th>P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((holding) => (
                <tr key={holding.symbol}>
                  <td>{holding.symbol}</td>
                  <td>{holding.qty}</td>
                  <td>₹{holding.avg}</td>
                  <td>₹{holding.ltp}</td>
                  <td>₹{holding.value.toLocaleString()}</td>
                  <td className="positive">₹{holding.pnl}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default PortfolioPage;
