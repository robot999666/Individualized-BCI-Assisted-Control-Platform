/** Deterministic procedural cortex, shared by first-paint SVG and WebGL. */
export type Point3 = [number, number, number];
export function cortexPoint(u: number, v: number, side: number): Point3 {
  const phi = u * Math.PI * 2, theta = v * Math.PI;
  const folds = 1 + .065 * Math.sin(phi * 9 + theta * 5) * Math.sin(theta * 8) + .035 * Math.cos(phi * 15 - theta * 4);
  const sin = Math.sin(theta);
  return [side * (.16 + (1 + Math.cos(phi)) * .59 * sin * folds), Math.cos(theta) * 1.58 * folds + .1 * Math.sin(phi * 3) * sin, Math.sin(phi) * 1.12 * sin * folds + .12 * Math.cos(theta * 2)];
}
export function seededRandom(seed = 71) {
  return () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
}
