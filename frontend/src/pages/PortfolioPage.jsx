import { useState, useEffect } from 'react';

function PortfolioPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('http://localhost:8000/portfolio/summary')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load portfolio metrics');
        return res.json();
      })
      .then((resData) => {
        setData(resData);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="page-content">
        <p style={{ color: '#aaa', padding: '1.5rem 0' }}>Syncing live portfolio metrics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-content">
        <p style={{ color: '#ef4444', padding: '1.5rem 0' }}>Error connecting to portfolio service: {error}</p>
      </div>
    );
  }

  const isProfit = data.gain >= 0;

  return (
    <div className="page-content">
      {/* Header with Future Broker Sync Action */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <p className="eyebrow" style={{ color: '#38bdf8', letterSpacing: '0.05em' }}>PORTFOLIO TRACKER</p>
          <h1 style={{ margin: '0.25rem 0' }}>Primary Investments</h1>
          <p style={{ color: '#64748b', fontSize: '0.85rem', margin: 0 }}>
            Sandbox tracking mode • Ready for Zerodha / Groww Demat link
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button 
            className="btn" 
            style={{ 
              background: '#0f172a', 
              border: '1px solid #334155', 
              color: '#38bdf8', 
              padding: '0.6rem 1.2rem', 
              borderRadius: '8px',
              fontWeight: 600,
              cursor: 'pointer'
            }}
            onClick={() => alert("Broker API Integration (Zerodha/Groww) is scheduled for the next release.")}
          >
            ⚡ Link Demat Account
          </button>
          <button className="btn btn-primary" style={{ padding: '0.6rem 1.2rem', borderRadius: '8px', fontWeight: 600 }}>
            + New Position
          </button>
        </div>
      </div>

      {/* Primary Metrics */}
      <div className="grid-4" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
        <div className="card metric-card">
          <p className="metric-label">Invested</p>
          <h2 className="metric-value">₹{data.total_invested.toLocaleString('en-IN')}</h2>
          <span className="metric-sub">Total capital deployed</span>
        </div>

        <div className="card metric-card">
          <p className="metric-label">Market Value</p>
          <h2 className="metric-value">₹{data.current_value.toLocaleString('en-IN')}</h2>
          <span className="metric-sub">Current portfolio valuation</span>
        </div>

        <div className="card metric-card">
          <p className="metric-label">Gain / Loss</p>
          <h2 className="metric-value" style={{ color: isProfit ? '#22c55e' : '#ef4444' }}>
            {isProfit ? '+' : ''}₹{data.gain.toLocaleString('en-IN')}
          </h2>
          <span className="metric-sub">Unrealized profit/loss</span>
        </div>

        <div className="card metric-card">
          <p className="metric-label">ROI</p>
          <h2 className="metric-value" style={{ color: isProfit ? '#22c55e' : '#ef4444' }}>
            {data.roi}%
          </h2>
          <span className="metric-sub">Net overall return</span>
        </div>
      </div>

      {/* Holdings Table */}
      <div className="card table-container" style={{ padding: '1.5rem', borderRadius: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>Active Holdings (NSE India)</h3>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Live prices via Yahoo Finance</span>
        </div>

        <table className="watchlist-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid #1e293b', color: '#64748b', fontSize: '0.85rem' }}>
              <th style={{ padding: '0.75rem 0.5rem' }}>SYMBOL</th>
              <th style={{ padding: '0.75rem 0.5rem' }}>QTY</th>
              <th style={{ padding: '0.75rem 0.5rem' }}>AVG COST</th>
              <th style={{ padding: '0.75rem 0.5rem' }}>LTP</th>
              <th style={{ padding: '0.75rem 0.5rem' }}>VALUE</th>
              <th style={{ padding: '0.75rem 0.5rem' }}>P&L</th>
            </tr>
          </thead>
          <tbody>
            {data.holdings.map((h) => {
              const holdingProfit = h.pnl >= 0;
              return (
                <tr key={h.symbol} style={{ borderBottom: '1px solid #0f172a' }}>
                  <td className="symbol-cell" style={{ fontWeight: 600, padding: '1rem 0.5rem' }}>{h.symbol}</td>
                  <td style={{ padding: '1rem 0.5rem' }}>{h.qty}</td>
                  <td style={{ padding: '1rem 0.5rem' }}>₹{h.avg_cost.toLocaleString('en-IN')}</td>
                  <td style={{ padding: '1rem 0.5rem' }}>₹{h.ltp.toLocaleString('en-IN')}</td>
                  <td style={{ padding: '1rem 0.5rem' }}>₹{h.value.toLocaleString('en-IN')}</td>
                  <td style={{ padding: '1rem 0.5rem', color: holdingProfit ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                    {holdingProfit ? '+' : ''}₹{h.pnl.toLocaleString('en-IN')} ({holdingProfit ? '+' : ''}{h.pnl_pct}%)
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default PortfolioPage;