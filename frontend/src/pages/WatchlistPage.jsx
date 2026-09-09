const watchlist = [
  { symbol: 'META', price: 515.2, change: '+2.15%' },
  { symbol: 'AMD', price: 168.7, change: '+1.64%' },
  { symbol: 'INTC', price: 57.8, change: '-0.42%' },
  { symbol: 'SHOP', price: 79.3, change: '+3.08%' },
  { symbol: 'PLTR', price: 27.2, change: '+2.63%' },
];

function WatchlistPage() {
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">Watchlist</p>
          <h1>Stocks to Monitor</h1>
        </div>
      </div>

      <div className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Price</th>
                <th>Change</th>
                <th>Trend</th>
              </tr>
            </thead>
            <tbody>
              {watchlist.map((item) => (
                <tr key={item.symbol}>
                  <td>{item.symbol}</td>
                  <td>₹{item.price}</td>
                  <td className={item.change.startsWith('-') ? 'negative' : 'positive'}>{item.change}</td>
                  <td>{item.change.startsWith('-') ? 'Cooling' : 'Momentum'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default WatchlistPage;
