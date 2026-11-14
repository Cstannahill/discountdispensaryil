// Price per gram (or per 10 mg THC) as a small pill. The total price is the headline figure on every card;
// this sits beside or under it so the number the ranking uses stays easy to find.
export default function UnitBadge({
  price,
  unit,
  className = '',
}: {
  price: string;
  unit: string;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-baseline whitespace-nowrap rounded-md border border-emerald-500/35 bg-emerald-500/10 px-1.5 py-px font-mono text-[11px] font-bold leading-tight text-emerald-300 ${className}`}
    >
      {price}
      <span className="font-medium opacity-80">/{unit}</span>
    </span>
  );
}
