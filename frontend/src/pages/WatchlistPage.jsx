import { useState, useEffect } from 'react';

function WatchlistPage() {
  const [watchlist, setWatchlist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('http://localhost:8000/watchlist/live')
      .then((res) => {
        if (!res.ok) {
          throw new Error('Failed to fetch watchlist from ML service');
        }
        return res.json();
      })
      .then((data) => {
        setWatchlist(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching watchlist:', err);
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">Watchlist</p>
          <h1>Stocks to Monitor</h1>
        </div>
      </div>

      {loading && <p style={{ color: '#aaa', padding: '1rem 0' }}>Fetching live prices...</p>}
      {error && <p style={{ color: '#ff6b6b' }}>Error loading watchlist: {error}</p>}

      {!loading && !error && (
        <div className="card table-container">
          <table className="watchlist-table">
            <thead>
              <tr>
                <th>SYMBOL</th>
                <th>PRICE</th>
                <th>CHANGE</th>
                <th>TREND</th>
              </tr>
            </thead>
            <tbody>
              {watchlist.map((item) => {
                const isPositive = item.change && !item.change.startsWith('-');
                return (
                  <tr key={item.symbol}>
                    <td className="symbol-cell">{item.symbol}</td>
                    <td>{item.price}</td>
                    <td style={{ color: isPositive ? '#22c55e' : '#ef4444' }}>
                      {item.change}
                    </td>
                    <td>
                      <span className={`badge ${item.trend.toLowerCase()}`}>
                        {item.trend}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default WatchlistPage;