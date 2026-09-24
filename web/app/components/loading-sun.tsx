"use client";

import { useEffect, useState } from "react";

const LINES = [
  "Finding the optimal beer-drinking time…",
  "Asking the sun where to sit…",
  "Hunting for the last patch of light…",
  "Seeing who steals your sunshine…",
  "Timing the golden-hour schooner…",
  "Working out when to take it outside…",
  "Looking for the least tragic seat…",
  "Calculating pint o'clock…",
  "Checking if it's a pot-in-the-sun kind of day…",
  "Negotiating with the verandah…",
];

export function LoadingSun() {
  const [i, setI] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setI((n) => (n + 1) % LINES.length), 1800);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="loading-sun" aria-live="polite" aria-busy="true">
      <svg viewBox="0 0 200 120" width="200" height="120" aria-hidden="true">
        <g className="loading-orbit">
          <g transform="translate(100 22)">
            <g className="loading-star">
              <circle r="8" fill="var(--sun)" />
              <g stroke="var(--sun)" strokeWidth="1.6" strokeLinecap="round">
                <line x1="0" y1="-13" x2="0" y2="-17" />
                <line x1="0" y1="13" x2="0" y2="17" />
                <line x1="-13" y1="0" x2="-17" y2="0" />
                <line x1="13" y1="0" x2="17" y2="0" />
                <line x1="-9" y1="-9" x2="-12" y2="-12" />
                <line x1="9" y1="9" x2="12" y2="12" />
                <line x1="9" y1="-9" x2="12" y2="-12" />
                <line x1="-9" y1="9" x2="-12" y2="12" />
              </g>
            </g>
          </g>
        </g>
        <rect x="70" y="62" width="60" height="40" fill="#f4f4f4" stroke="var(--ink)" strokeWidth="1.5" />
        <rect x="94" y="80" width="12" height="22" fill="var(--ink)" />
        <path d="M66 62 L100 42 L134 62" fill="none" stroke="var(--ink)" strokeWidth="1.5" />
        <line x1="40" y1="102" x2="160" y2="102" stroke="var(--ink)" strokeWidth="1.2" />
      </svg>
      <p className="text-muted">{LINES[i]}</p>
    </div>
  );
}
