import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

function PortfolioChart({ data }) {
  return (
    <div className="panel chart-panel">
      <div className="panel-header">
        <h3>Portfolio Performance</h3>
      </div>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.6} />
                <stop offset="95%" stopColor="#7c3aed" stopOpacity={0.08} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="date" stroke="#64748b" />
            <YAxis stroke="#64748b" tickFormatter={(value) => `₹${value / 1000}k`} />
            <Tooltip formatter={(value) => [`₹${Number(value).toLocaleString()}`, 'Value']} />
            <Area type="monotone" dataKey="value" stroke="#7c3aed" fill="url(#portfolioFill)" strokeWidth={3} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default PortfolioChart;
