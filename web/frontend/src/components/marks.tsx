/** Cell marks and ship outlines — SVG from the design/*.dc.html mockups. Colors via CSS variables. */

export function MissMark() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <circle cx="20" cy="20.5" r="3" fill="var(--ink)" fillOpacity="var(--miss-opacity)" />
    </svg>
  );
}

export function HitMark() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <path d="M11 10.5 Q20.5 20 30 30" fill="none" stroke="var(--hit)" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M29.5 10.5 Q20 20.5 10.5 30" fill="none" stroke="var(--hit)" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

export function AimMark() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <rect x="0.5" y="0.5" width="39" height="39" fill="var(--ink)" fillOpacity="var(--aim-opacity)" />
      <path d="M20 5 L20 14 M20 26 L20 35 M5 20 L14 20 M26 20 L35 20" fill="none" stroke="var(--ink)" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="20" cy="20" r="6.5" fill="none" stroke="var(--ink)" strokeWidth="1.3" strokeDasharray="2.5 3" />
    </svg>
  );
}

// outlines with deliberately uneven vertices; key — `${size}${h|v}`
const SHIP_PATHS: Record<string, { w: number; h: number; d: string }> = {
  "1h": { w: 40, h: 40, d: "M6 6.4 L34.4 5.4 L35 33.8 L5.6 34.8 Z" },
  "1v": { w: 40, h: 40, d: "M6 6.4 L34.4 5.4 L35 33.8 L5.6 34.8 Z" },
  "2h": { w: 80, h: 40, d: "M6 6.2 L74.2 5.2 L75 34 L5.4 35 Z" },
  "2v": { w: 40, h: 80, d: "M6 6.2 L34.6 5.2 L35 74.2 L5.2 75 Z" },
  "3h": { w: 120, h: 40, d: "M6.4 6 L60 4.9 L114 6.2 L114.8 34 L60 35.5 L5.2 34.4 Z" },
  "3v": { w: 40, h: 120, d: "M6.2 6 L34.8 5.2 L35.4 60 L34.2 114.4 L5.4 115 L4.9 60 Z" },
  "4h": { w: 160, h: 40, d: "M6 6.3 L80 4.9 L154 6.1 L154.8 34.1 L80 35.6 L5.4 34.3 Z" },
  "4v": { w: 40, h: 160, d: "M6.3 6 L34.9 5.4 L35.6 80 L34.1 154 L5.4 154.8 L4.9 80 Z" },
};

export type ShipTone = "ink" | "sunk" | "danger";

export function ShipOutline({ size, horizontal, tone = "ink" }: { size: number; horizontal: boolean; tone?: ShipTone }) {
  const p = SHIP_PATHS[`${size}${horizontal ? "h" : "v"}`];
  const stroke = tone === "ink" ? "var(--ink)" : "var(--hit)";
  const fill = tone === "ink" ? "var(--ship-fill)" : tone === "sunk" ? "var(--sunk-fill)" : "var(--danger-fill)";
  return (
    <svg viewBox={`0 0 ${p.w} ${p.h}`} width="100%" height="100%" aria-hidden="true" style={{ display: "block" }}>
      <path d={p.d} fill={fill} stroke={stroke} strokeWidth="2.2" strokeLinejoin="round" />
    </svg>
  );
}

export function MoonIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <path d="M15.5 12.4 A6.4 6.4 0 0 1 7.4 4.4 A6.6 6.6 0 1 0 15.5 12.4 Z" fill="none" stroke="var(--ink)" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function SunIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <circle cx="10" cy="10" r="4" fill="none" stroke="var(--ink)" strokeWidth="1.5" />
      <path d="M10 1.5 L10 3.6 M10 16.4 L10 18.5 M1.5 10 L3.6 10 M16.4 10 L18.5 10 M4 4 L5.5 5.5 M14.5 14.5 L16 16 M16 4 L14.5 5.5 M5.5 14.5 L4 16" fill="none" stroke="var(--ink)" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
