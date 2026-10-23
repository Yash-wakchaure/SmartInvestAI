import { useState, useEffect } from 'react';
import PredictionCard from '../components/PredictionCard';

function PredictionsPage() {
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('http://localhost:8000/predictions/batch')
      .then((res) => {
        if (!res.ok) {
          throw new Error('Failed to fetch predictions from ML service');
        }
        return res.json();
      })
      .then((data) => {
        setPredictions(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching ML predictions:', err);
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">AI Signals</p>
          <h1>Predictions</h1>
        </div>
      </div>

      {loading && <p style={{ color: '#aaa', padding: '1rem 0' }}>Analyzing market signals & running ML models...</p>}
      {error && <p style={{ color: '#ff6b6b' }}>Error connecting to ML model: {error}</p>}

      {!loading && !error && (
        <div className="grid-3">
          {predictions.map((item) => (
            <PredictionCard key={item.symbol} {...item} />
          ))}
        </div>
      )}
    </div>
  );
}

export default PredictionsPage;