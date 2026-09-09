function SignalBadge({ signal }) {
  const value = (signal || 'HOLD').toUpperCase();
  return <span className={`signal-badge ${value.toLowerCase()}`}>{value}</span>;
}

export default SignalBadge;
