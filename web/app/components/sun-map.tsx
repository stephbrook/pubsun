"use client";

import type { Front, LatLon, Result } from "../lib/types";

const W = 720;
const H = 420;
const PAD = 72;
const SUN_BAND = 88;
const MIN_FRONT_M = 8;

type XY = { x: number; y: number };

function seatingFronts(result: Result): Front[] {
  return result.fronts.filter((front) => (front.points?.length ?? 0) >= 8 || front.lengthM >= MIN_FRONT_M);
}

function allPoints(result: Result): LatLon[] {
  const pts: LatLon[] = [];
  if (result.building.outline) pts.push(...result.building.outline);
  for (const front of seatingFronts(result)) {
    if (front.points) pts.push(...front.points);
  }
  if (!pts.length) pts.push({ lat: result.building.lat, lon: result.building.lon });
  return pts;
}

function hasStreetOnTop(result: Result) {
  const lat = result.building.lat;
  return seatingFronts(result).some((front) => {
    const pts = front.points ?? [];
    if (!pts.length) return false;
    const mid = pts.reduce((s, p) => s + p.lat, 0) / pts.length;
    return mid > lat;
  });
}

function projector(result: Result) {
  const pts = allPoints(result);
  const lats = pts.map((p) => p.lat);
  const lons = pts.map((p) => p.lon);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const cos = Math.cos((midLat * Math.PI) / 180) || 1;
  const xs = lons.map((lon) => lon * cos);
  const ys = lats;
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1e-6);
  const spanY = Math.max(maxY - minY, 1e-6);
  const top = hasStreetOnTop(result) ? SUN_BAND + 56 : PAD;
  const scale = Math.min((W - PAD * 2) / spanX, (H - top - PAD) / spanY);
  const ox = (W - spanX * scale) / 2;
  const oy = top + (H - top - PAD - spanY * scale) / 2;
  return (p: LatLon): XY => ({
    x: ox + (p.lon * cos - minX) * scale,
    y: oy + (maxY - p.lat) * scale,
  });
}

function centroid(points: XY[]): XY {
  const n = points.length || 1;
  return {
    x: points.reduce((s, p) => s + p.x, 0) / n,
    y: points.reduce((s, p) => s + p.y, 0) / n,
  };
}

function minutes(time: string) {
  const [h, m] = time.split(":").map(Number);
  return h * 60 + m;
}

function sunPos(time: string, start: string, end: string, ceiling: number): XY {
  const span = Math.max(1, minutes(end) - minutes(start));
  const t = Math.min(1, Math.max(0, (minutes(time) - minutes(start)) / span));
  const a = t * Math.PI;
  const y = Math.min(32, ceiling - 36);
  return { x: W / 2 + 210 * Math.cos(a), y: Math.max(22, y) };
}

function straighten(pts: XY[], centre: XY, gap = 28): XY[] {
  const mid = centroid(pts);
  const horizontal = Math.abs(pts[pts.length - 1].x - pts[0].x) >= Math.abs(pts[pts.length - 1].y - pts[0].y);
  if (horizontal) {
    const y = mid.y < centre.y ? Math.min(...pts.map((p) => p.y)) - gap : Math.max(...pts.map((p) => p.y)) + gap;
    const a = Math.min(...pts.map((p) => p.x));
    const b = Math.max(...pts.map((p) => p.x));
    return pts.map((_, i) => ({
      x: a + ((b - a) * i) / Math.max(1, pts.length - 1),
      y,
    }));
  }
  const x = mid.x < centre.x ? Math.min(...pts.map((p) => p.x)) - gap : Math.max(...pts.map((p) => p.x)) + gap;
  const a = Math.min(...pts.map((p) => p.y));
  const b = Math.max(...pts.map((p) => p.y));
  return pts.map((_, i) => ({
    x,
    y: a + ((b - a) * i) / Math.max(1, pts.length - 1),
  }));
}

function streetName(name: string) {
  return name.replace(/\bStreet\b/i, "St");
}

function SmileySun({ x, y }: XY) {
  return (
    <g transform={`translate(${x} ${y})`} strokeLinecap="round" strokeLinejoin="round">
      <g stroke="var(--sun)" strokeWidth="1.6" fill="none">
        <line x1="0" y1="-16" x2="0" y2="-20" />
        <line x1="0" y1="16" x2="0" y2="20" />
        <line x1="-16" y1="0" x2="-20" y2="0" />
        <line x1="16" y1="0" x2="20" y2="0" />
        <line x1="-11" y1="-11" x2="-14" y2="-14" />
        <line x1="11" y1="11" x2="14" y2="14" />
        <line x1="11" y1="-11" x2="14" y2="-14" />
        <line x1="-11" y1="11" x2="-14" y2="14" />
      </g>
      <circle r="11" fill="var(--sun)" stroke="var(--ink)" strokeWidth="1.3" />
      <circle cx="-3.5" cy="-2" r="1.2" fill="var(--ink)" />
      <circle cx="3.5" cy="-2" r="1.2" fill="var(--ink)" />
      <path d="M-4 3.5 Q0 7 4 3.5" fill="none" stroke="var(--ink)" strokeWidth="1.3" />
    </g>
  );
}

type Props = {
  result: Result;
  time: string;
};

export function SunMap({ result, time }: Props) {
  const toXY = projector(result);
  const outline = (result.building.outline ?? []).map(toXY);
  const centre = outline.length ? centroid(outline) : toXY({ lat: result.building.lat, lon: result.building.lon });
  const dayTimes = result.fronts[0]?.rows.map((r) => r.time) ?? [];
  const shortName = result.building.name.split(",")[0];

  const streets = seatingFronts(result).flatMap((front) => {
    const pts = (front.points ?? []).map(toXY);
    if (!pts.length) return [];
    const row = front.rows.find((r) => r.time === time);
    const count = Math.min(6, pts.length);
    const indexes = Array.from({ length: count }, (_, i) =>
      Math.round((i * (pts.length - 1)) / Math.max(1, count - 1)),
    );
    const placed = straighten(
      indexes.map((i) => pts[i]),
      centre,
    );
    const mid = centroid(placed);
    const dx = mid.x - centre.x;
    const dy = mid.y - centre.y;
    const len = Math.hypot(dx, dy) || 1;
    return [
      {
        name: streetName(front.name),
        label: { x: mid.x + (dx / len) * 24, y: mid.y + (dy / len) * 24 },
        marks: placed.map((p, n) => ({
          x: p.x,
          y: p.y,
          sun: Boolean(row?.cells[indexes[n]]),
          metre: indexes[n],
        })),
      },
    ];
  });

  const above = streets.flatMap((s) => [s.label, ...s.marks]).filter((p) => p.y < centre.y);
  const ceiling = above.length ? Math.min(...above.map((p) => p.y)) : 80;
  const sun = sunPos(time, dayTimes[0] ?? "06:00", dayTimes[dayTimes.length - 1] ?? "18:00", ceiling);

  return (
    <div className="sun-map">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${shortName} at ${time}`}>
        <text x="28" y="28" fontSize="11" fontFamily="var(--font-sans)" fill="var(--muted)">
          N
        </text>
        <SmileySun x={sun.x} y={sun.y} />

        {outline.length > 2 ? (
          <polygon
            points={outline.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="#fff"
            stroke="var(--ink)"
            strokeWidth="1.5"
          />
        ) : (
          <rect x={centre.x - 36} y={centre.y - 24} width="72" height="48" fill="#fff" stroke="var(--ink)" strokeWidth="1.5" />
        )}

        <text
          x={centre.x}
          y={centre.y + 4}
          textAnchor="middle"
          fontSize="15"
          fontFamily="var(--font-display)"
          fill="var(--ink)"
        >
          🍺 {shortName.length > 22 ? `${shortName.slice(0, 20)}…` : shortName}
        </text>
      </svg>
      <div className="sun-map-marks">
        {streets.flatMap((street) => [
          <span
            key={`l-${street.name}`}
            className="sun-map-label"
            style={{ left: `${(street.label.x / W) * 100}%`, top: `${(street.label.y / H) * 100}%` }}
          >
            {street.name}
          </span>,
          ...street.marks.map((m, i) => (
            <span
              key={`e-${street.name}-${i}`}
              className="sun-map-emoji"
              style={{ left: `${(m.x / W) * 100}%`, top: `${(m.y / H) * 100}%` }}
              title={`${street.name}, ${m.metre} m, ${m.sun ? "sun" : "shade"}`}
            >
              {m.sun ? "☀️" : "🌙"}
            </span>
          )),
        ])}
      </div>
    </div>
  );
}

export function sunSummary(result: Result, time: string) {
  const bits = seatingFronts(result).map((front) => {
    const row = front.rows.find((r) => r.time === time);
    const n = row?.cells.filter(Boolean).length ?? 0;
    return { name: streetName(front.name), any: n > 0 };
  });
  const sunny = bits.filter((b) => b.any);
  if (!sunny.length) return "Shade on every side right now.";
  if (sunny.length === bits.length) return "Sun on every side.";
  if (sunny.length === 1) return `${sunny[0].name} is in the sun.`;
  return `${sunny.map((b) => b.name).join(" and ")} are in the sun.`;
}
