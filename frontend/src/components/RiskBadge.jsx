function RiskBadge({ risk }) {
  const value = (risk || 'MEDIUM').toUpperCase();
  return <span className={`risk-badge ${value.toLowerCase()}`}>{value}</span>;
}

export default RiskBadge;
