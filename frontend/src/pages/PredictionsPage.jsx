import PredictionCard from '../components/PredictionCard';

const predictions = [
  { symbol: 'AAPL', prediction: 'up', confidence: 82, risk: 'low', signal: 'bullish' },
  { symbol: 'MSFT', prediction: 'up', confidence: 78, risk: 'medium', signal: 'momentum' },
  { symbol: 'NVDA', prediction: 'up', confidence: 88, risk: 'medium', signal: 'breakout' },
  { symbol: 'AMZN', prediction: 'hold', confidence: 66, risk: 'low', signal: 'steady' },
  { symbol: 'TSLA', prediction: 'down', confidence: 72, risk: 'high', signal: 'risk-off' },
];

function PredictionsPage() {
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">AI Signals</p>
          <h1>Predictions</h1>
        </div>
      </div>

      <div className="grid-3">
        {predictions.map((item) => (
          <PredictionCard key={item.symbol} {...item} />
        ))}
      </div>
    </div>
  );
}

export default PredictionsPage;
