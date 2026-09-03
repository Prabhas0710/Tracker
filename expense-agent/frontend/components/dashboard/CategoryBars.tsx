export function CategoryBars({
  rows,
  total,
}: {
  rows: { category: string; amount: number }[];
  total: number;
}) {
  const max = rows[0]?.amount || 1;
  return (
    <div className="stack">
      {rows.map((row) => (
        <div key={row.category}>
          <div className="row">
            <span>{row.category}</span>
            <span>
              ₹{row.amount.toLocaleString("en-IN")}
              {total ? ` · ${Math.round((row.amount / total) * 100)}%` : ""}
            </span>
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(row.amount / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
