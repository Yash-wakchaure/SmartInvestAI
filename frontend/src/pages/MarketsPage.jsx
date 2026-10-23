import { useState, useEffect } from 'react';

function MarketsPage() {
  const [markets, setMarkets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('http://localhost:8000/markets/overview')
      .then((res) => {
        if (!res.ok) {
          throw new Error('Failed to fetch market overview');
        }
        return res.json();
      })
      .then((data) => {
        setMarkets(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching market data:', err);
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">Markets</p>
          <h1>Market Snapshot</h1>
        </div>
      </div>

      {loading && <p style={{ color: '#aaa', padding: '1rem 0' }}>Loading live market data...</p>}
      {error && <p style={{ color: '#ff6b6b' }}>Error loading markets: {error}</p>}

      {!loading && !error && (
        <div className="grid-5">
          {markets.map((m) => {
            const isPositive = m.change && !m.change.startsWith('-');
            return (
              <div key={m.name} className="card metric-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <p className="metric-label">{m.name}</p>
                  <span style={{ color: isPositive ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                    {m.change}
                  </span>
                </div>
                <h2 className="metric-value">{m.price}</h2>
              </div>
            );
          })}
        </div>
      )}

      {/* Macro Signals section */}
      <div className="card" style={{ marginTop: '1.5rem', padding: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Macro Signals</h3>
        <ul style={{ color: '#cbd5e1', lineHeight: '1.8', paddingLeft: '1.25rem' }}>
          <li>Global equities remain strong as earnings revisions improve.</li>
          <li>Bond yields are stable, supporting quality growth names.</li>
          <li>Domestic flows continue to favor large-cap sectors with resilient earnings.</li>
        </ul>
      </div>
    </div>
  );
}

export default MarketsPage;