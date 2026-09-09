const marketData = [
  { symbol: 'NIFTY 50', value: '24,860', change: '+1.26%' },
  { symbol: 'SENSEX', value: '81,420', change: '+0.92%' },
  { symbol: 'NASDAQ', value: '19,840', change: '+1.76%' },
  { symbol: 'DOW', value: '39,880', change: '+0.48%' },
  { symbol: 'USD/INR', value: '83.42', change: '-0.18%' },
];

function MarketsPage() {
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">Markets</p>
          <h1>Market Snapshot</h1>
        </div>
      </div>

      <div className="market-grid">
        {marketData.map((item) => (
          <div className="panel market-card" key={item.symbol}>
            <div className="market-header">
              <span className="market-symbol">{item.symbol}</span>
              <span className="market-change positive">{item.change}</span>
            </div>
            <h3>{item.value}</h3>
          </div>
        ))}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h3>Macro Signals</h3>
        </div>
        <ul className="signal-list">
          <li>Global equities remain strong as earnings revisions improve.</li>
          <li>Bond yields are stable, supporting quality growth names.</li>
          <li>Domestic flows continue to favor large-cap sectors with resilient earnings.</li>
        </ul>
      </div>
    </div>
  );
}

export default MarketsPage;
