function PredictionCard({ symbol, prediction, confidence, risk, signal }) {
  const predictionText = prediction?.toUpperCase() || 'UP';
  const signalText = signal?.toUpperCase() || 'HOLD';
  const riskText = risk?.toUpperCase() || 'MEDIUM';

  return (
    <div className="prediction-card panel">
      <div className="prediction-header">
        <h4>{symbol}</h4>
      </div>
      <div className="prediction-grid">
        <div>
          <span className="label">Prediction</span>
          <p className={`prediction-value ${predictionText.toLowerCase()}`}>{predictionText}</p>
        </div>
        <div>
          <span className="label">Confidence</span>
          <p>{confidence ?? 0}%</p>
        </div>
      </div>
      <div className="prediction-footer">
        <span className={`risk-badge ${riskText.toLowerCase()}`}>{riskText}</span>
        <span className={`signal-badge ${signalText.toLowerCase()}`}>{signalText}</span>
      </div>
    </div>
  );
}

export default PredictionCard;
