import { cortexPoint, seededRandom, type Point3 } from "./neuralGeometry";
import styles from "./hero.module.css";
function project([x, y, z]: Point3) { return [350 + (x * .92 + z * .39) * 103, 275 - (y * .98 - z * .14) * 103]; }
export default function NeuralFallback() {
  const random = seededRandom();
  const points = Array.from({ length: 650 }, (_, i) => project(cortexPoint(random(), random(), i % 2 ? -1 : 1)));
  const contours = [-1, 1].flatMap(side => Array.from({ length: 13 }, (_, j) => Array.from({ length: 81 }, (_, i) => project(cortexPoint(i / 80, (j + 1) / 14, side))).map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ")));
  return <svg viewBox="0 0 700 570" className={styles.fallback} aria-hidden="true">
    <defs>
      <radialGradient id="neural-halo"><stop stopColor="#22d3b4" stopOpacity=".12" /><stop offset="1" stopColor="#22d3b4" stopOpacity="0" /></radialGradient>
      <linearGradient id="neural-contour"><stop stopColor="#48dfbc" /><stop offset=".55" stopColor="#64d4f2" /><stop offset="1" stopColor="#988ad9" /></linearGradient>
    </defs>
    <ellipse cx="350" cy="280" rx="240" ry="240" fill="url(#neural-halo)" />
    <g fill="none" stroke="url(#neural-contour)">
      <ellipse cx="350" cy="290" rx="246" ry="84" transform="rotate(-21 350 290)" opacity=".24" />
      <ellipse cx="350" cy="295" rx="206" ry="160" transform="rotate(32 350 295)" opacity=".12" strokeDasharray="3 9" />
      {contours.map((d, i) => <path key={i} d={d} opacity=".25" strokeWidth=".65" />)}
      <path d="M12 327 Q74 285 130 303 T235 291 M469 288 Q533 198 610 194 M477 324 Q538 365 646 393" opacity=".55" />
      <path d="M0 310h18l9-5 10 18 11-38 10 52 10-27h23l8-8 8 15 8-7h47" opacity=".7" />
    </g>
    <g>{points.map(([cx, cy], i) => <circle key={i} cx={cx} cy={cy} r={i % 11 === 0 ? 1.6 : .75} fill={i % 3 ? "#72dccf" : "#a09be3"} opacity={i % 7 === 0 ? .8 : .4} />)}</g>
  </svg>;
}
