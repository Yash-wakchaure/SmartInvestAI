function StatCard({ title, value, subtitle, tone = 'neutral' }) {
  return (
    <div className={`stat-card ${tone}`}>
      <p className="stat-label">{title}</p>
      <h3>{value}</h3>
      {subtitle && <span className="stat-subtitle">{subtitle}</span>}
    </div>
  );
}

export default StatCard;
