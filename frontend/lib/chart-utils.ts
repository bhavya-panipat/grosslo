export function scale(values: number[], min: number, max: number, size: number, pad: number) {
  const span = max - min || 1;
  return values.map((v) => pad + ((v - min) / span) * (size - pad * 2));
}

// Catmull-Rom to cubic-bezier smoothing — no charting library needed.
export function smoothPath(xs: number[], ys: number[]) {
  if (xs.length < 2) return "";
  let d = `M ${xs[0]},${ys[0]}`;
  for (let i = 0; i < xs.length - 1; i++) {
    const x0 = xs[i - 1] ?? xs[i];
    const y0 = ys[i - 1] ?? ys[i];
    const x1 = xs[i];
    const y1 = ys[i];
    const x2 = xs[i + 1];
    const y2 = ys[i + 1];
    const x3 = xs[i + 2] ?? x2;
    const y3 = ys[i + 2] ?? y2;

    const cp1x = x1 + (x2 - x0) / 6;
    const cp1y = y1 + (y2 - y0) / 6;
    const cp2x = x2 - (x3 - x1) / 6;
    const cp2y = y2 - (y3 - y1) / 6;

    d += ` C ${cp1x},${cp1y} ${cp2x},${cp2y} ${x2},${y2}`;
  }
  return d;
}
