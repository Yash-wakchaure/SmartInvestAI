import { useState, useEffect } from 'react';

function DashboardPage() {
  const [searchQuery, setSearchQuery] = useState('RELIANCE');
  const [stockData, setStockData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchStockAnalysis = (ticker) => {
    setLoading(true);
    setError(null);
    fetch(`http://localhost:8000/stock/analyze?symbol=${encodeURIComponent(ticker)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Stock "${ticker}" not found on NSE India`);
        return res.json();
      })
      .then((data) => {
        setStockData(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchStockAnalysis('RELIANCE');
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      fetchStockAnalysis(searchQuery.trim().toUpperCase());
    }
  };

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">AI RESEARCH & SCANNER</p>
          <h1>Market Intelligence Hub</h1>
        </div>
      </div>

      {/* 4 AI Metric Cards (No Fake Demat Money) */}
      <div className="grid-4" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
        <div className="card metric-card">
          <p className="metric-label">Tracked Universe</p>
          <h2 className="metric-value">NSE 500</h2>
          <span className="metric-sub">Live Equities Scanned</span>
        </div>

        <div className="card metric-card">
          <p className="metric-label">AI Market Sentiment</p>
          <h2 className="metric-value" style={{ color: '#22c55e' }}>BULLISH</h2>
          <span className="metric-sub">NIFTY 50 Direction</span>
        </div>

        <div className="card metric-card">
          <p className="metric-label">Model Architecture</p>
          <h2 className="metric-value">RandomForest</h2>
          <span className="metric-sub">15 Technical Indicators</span>
        </div>

        <div className="card metric-card">
          <p className="metric-label">Signal Frequency</p>
          <h2 className="metric-value">Daily</h2>
          <span className="metric-sub">Next-Day Forecast Horizon</span>
        </div>
      </div>

      {/* Stock Search Box */}
      <div className="card" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
        <h3 style={{ marginBottom: '0.75rem' }}>Scan Any Indian Stock with AI</h3>
        <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: '1rem' }}>
          Type any NSE ticker symbol (e.g. TCS, RELIANCE, INFY, TATAMOTORS, HDFCBANK) to run live indicators and model inference.
        </p>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.75rem' }}>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Enter NSE Symbol..."
            style={{
              flex: 1,
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              border: '1px solid #334155',
              background: '#0f172a',
              color: '#fff',
              fontSize: '1rem',
              textTransform: 'uppercase'
            }}
          />
          <button type="submit" className="btn btn-primary" style={{ padding: '0.75rem 1.5rem', fontWeight: 600 }}>
            {loading ? 'Analyzing...' : 'Scan Stock'}
          </button>
        </form>
      </div>

      {error && <p style={{ color: '#ef4444', marginBottom: '1.5rem' }}>Error: {error}</p>}

      {/* AI Analysis Result */}
      {stockData && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1.8fr', gap: '1.5rem', marginBottom: '2rem' }}>
          {/* Card 1: AI Recommendation */}
          <div className="card" style={{ padding: '1.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h2 style={{ fontSize: '1.75rem', margin: 0 }}>{stockData.symbol}</h2>
                <p style={{ color: '#64748b', margin: 0, fontSize: '0.85rem' }}>National Stock Exchange (NSE)</p>
              </div>
              <div style={{ textAlign: 'right' }}>
                <h3 style={{ margin: 0, fontSize: '1.5rem' }}>{stockData.current_price}</h3>
                <span style={{ color: stockData.change_pct.startsWith('-') ? '#ef4444' : '#22c55e', fontWeight: 600 }}>
                  {stockData.change_pct}
                </span>
              </div>
            </div>

            <hr style={{ borderColor: '#1e293b', margin: '1.25rem 0' }} />

            <div style={{ marginBottom: '1.25rem' }}>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.25rem' }}>AI NEXT-DAY STANCE</p>
              <h2 style={{
                color: stockData.prediction.includes('BUY') ? '#22c55e' : (stockData.prediction.includes('SELL') ? '#ef4444' : '#eab308'),
                margin: 0
              }}>
                {stockData.prediction}
              </h2>
            </div>

            <div>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.25rem' }}>MODEL CONFIDENCE</p>
              <h3 style={{ margin: 0 }}>{stockData.confidence}</h3>
            </div>
          </div>

          {/* Card 2: Technical Indicators Calculated by yfinance */}
          <div className="card" style={{ padding: '1.75rem' }}>
            <h3 style={{ marginBottom: '1.25rem' }}>Feature Snapshot (Model Inputs)</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.25rem' }}>
              <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '8px', border: '1px solid #1e293b' }}>
                <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: 0 }}>RSI (14-Day)</p>
                <h4 style={{ margin: '0.25rem 0' }}>{stockData.indicators.rsi}</h4>
                <span style={{ fontSize: '0.75rem', color: '#38bdf8' }}>{stockData.indicators.rsi_status}</span>
              </div>

              <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '8px', border: '1px solid #1e293b' }}>
                <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: 0 }}>MACD vs Signal</p>
                <h4 style={{ margin: '0.25rem 0' }}>{stockData.indicators.macd} / {stockData.indicators.macd_signal}</h4>
                <span style={{ fontSize: '0.75rem', color: '#38bdf8' }}>{stockData.indicators.macd_trend}</span>
              </div>

              <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '8px', border: '1px solid #1e293b' }}>
                <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: 0 }}>Bollinger Upper Band</p>
                <h4 style={{ margin: '0.25rem 0' }}>{stockData.indicators.bb_upper}</h4>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Resistance Channel</span>
              </div>

              <div style={{ background: '#0f172a', padding: '1rem', borderRadius: '8px', border: '1px solid #1e293b' }}>
                <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: 0 }}>Bollinger Lower Band</p>
                <h4 style={{ margin: '0.25rem 0' }}>{stockData.indicators.bb_lower}</h4>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Support Channel</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DashboardPage;