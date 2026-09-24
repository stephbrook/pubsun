"use client";

import { useEffect, useState } from "react";
import type { Job, Result } from "../lib/types";
import { AddressField } from "./address-field";
import { LoadingSun } from "./loading-sun";
import { SunMap, sunSummary } from "./sun-map";

function melbourneToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Australia/Melbourne",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg?: string }) => d.msg).join(" ");
    if (typeof body.error === "string") return body.error;
  } catch {
    /* ignore */
  }
  return res.statusText || "Request failed";
}

function line(n: number, lat0: number, lon0: number, lat1: number, lon1: number) {
  return Array.from({ length: n }, (_, i) => {
    const t = n === 1 ? 0 : i / (n - 1);
    return { lat: lat0 + (lat1 - lat0) * t, lon: lon0 + (lon1 - lon0) * t };
  });
}

function timesOf(result: Result) {
  return result.fronts[0]?.rows.map((r) => r.time) ?? [];
}

function hasMapGeometry(result: Result) {
  return Boolean(result.building.outline?.length || result.fronts.some((f) => f.points?.length));
}

const DEMO: Result = {
  building: {
    name: "The Standard",
    lat: -37.79651,
    lon: 144.97882,
    quality: "MEDIUM",
    imageryDate: "2023-02-01",
    outline: [
      { lat: -37.79638, lon: 144.9787 },
      { lat: -37.79638, lon: 144.97894 },
      { lat: -37.79664, lon: 144.97894 },
      { lat: -37.79664, lon: 144.9787 },
      { lat: -37.79638, lon: 144.9787 },
    ],
  },
  date: "2026-09-24",
  groundM: 21.3,
  offsetM: 1.5,
  streets: ["Brunswick Street", "St David Street"],
  fronts: [
    {
      name: "Brunswick Street",
      lengthM: 22,
      start: "S",
      end: "N",
      someSun: "09:15–11:40, 14:05–16:20",
      wholeFrontage: "10:00–10:45",
      points: line(22, -37.79664, 144.97897, -37.79638, 144.97897),
      rows: [
        { time: "09:00", cells: [false, false, false, true, true, true, true, true, false, false, false, false, false, true, true, true, true, true, true, true, true, true] },
        { time: "09:15", cells: [false, false, true, true, true, true, true, true, true, false, false, false, true, true, true, true, true, true, true, true, true, true] },
        { time: "12:00", cells: [true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, true, false, false, false, false] },
        { time: "15:00", cells: [true, true, true, true, false, false, false, false, false, false, true, true, true, true, true, true, false, false, false, false, false, false] },
      ],
    },
    {
      name: "St David Street",
      lengthM: 12,
      start: "W",
      end: "E",
      someSun: "11:00–15:30",
      wholeFrontage: "12:15–13:00",
      points: line(12, -37.79666, 144.9787, -37.79666, 144.97894),
      rows: [
        { time: "09:00", cells: [false, false, false, false, false, false, false, false, false, false, false, false] },
        { time: "12:00", cells: [true, true, true, true, true, true, true, true, true, true, true, true] },
        { time: "15:00", cells: [true, true, true, false, false, false, false, false, true, true, true, true] },
      ],
    },
  ],
};

export function Lookup() {
  const [address, setAddress] = useState("");
  const [placeId, setPlaceId] = useState<string | null>(null);
  const [date, setDate] = useState(melbourneToday);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("demo")) {
      setJob({ status: "done", result: DEMO });
    }
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const poll = async () => {
      const res = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
      if (!res.ok) {
        if (!cancelled) {
          setJob({ status: "error", error: await readError(res) });
          setBusy(false);
        }
        return;
      }
      const next = (await res.json()) as Job;
      if (cancelled) return;
      setJob(next);
      if (next.status === "done" || next.status === "error") {
        setBusy(false);
        return;
      }
      window.setTimeout(poll, 1500);
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!placeId) return;
    setBusy(true);
    setJob({ status: "queued", message: "Hunting for the sunny table…" });
    setJobId(null);
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: address.trim(), date, placeId }),
      });
      if (!res.ok) {
        setJob({ status: "error", error: await readError(res) });
        setBusy(false);
        return;
      }
      const data = (await res.json()) as { jobId: string };
      setJobId(data.jobId);
    } catch (err) {
      setJob({
        status: "error",
        error: err instanceof Error ? err.message : "Could not reach the server.",
      });
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-10 py-10">
      <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-[1fr_auto_auto] sm:items-end">
        <label className="block">
          <span className="mb-1.5 block text-sm text-muted">Pub or address</span>
          <AddressField value={address} onChange={setAddress} onPlaceId={setPlaceId} disabled={busy} />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm text-muted">Date</span>
          <input
            type="date"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-full border-b border-ink bg-transparent py-2 text-base outline-none sm:w-40"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !placeId}
          className="border border-ink px-4 py-2 text-sm disabled:opacity-50"
        >
          {busy ? "Checking…" : "Check the sun"}
        </button>
      </form>

      {job?.status === "queued" || job?.status === "running" ? (
        <LoadingSun />
      ) : null}

      {job?.status === "error" ? (
        <p className="text-ink">{job.error}</p>
      ) : null}

      {job?.status === "done" ? <ResultView result={job.result} /> : null}
    </div>
  );
}

function ResultView({ result }: { result: Result }) {
  const times = timesOf(result);
  const [ti, setTi] = useState(() => Math.max(0, times.findIndex((t) => t >= "12:00")));
  const time = times[ti] ?? "";

  const shortName = result.building.name.split(",")[0];

  return (
    <div>
      <div className="flex items-end justify-between gap-4">
        <h2 className="text-3xl tracking-tight text-ink">🍺 {shortName}</h2>
        {time ? <p className="font-mono text-sm text-muted">{time}</p> : null}
      </div>
      {hasMapGeometry(result) && time ? (
        <div className="mt-2">
          <p className="text-muted">{sunSummary(result, time)}</p>
          <div className="mt-4 w-full">
            <SunMap result={result} time={time} />
            <label className="mt-4 block w-full">
            <input
              type="range"
              min={0}
              max={Math.max(0, times.length - 1)}
              value={ti}
              onChange={(e) => setTi(Number(e.target.value))}
              className="time-slider"
            />
            <span className="mt-1 flex justify-between text-sm text-muted">
              <span>Sunrise {times[0]}</span>
              <span>Sunset {times[times.length - 1]}</span>
            </span>
            <div className="mt-3 text-center text-sm text-muted">
              <p>Some notes:</p>
              <p>1. Nearby buildings' shadows are taken into account</p>
              <p>2. Sorry but I don’t know if it’s cloudy, I’m not magic. Look outside!</p>
            </div>
            </label>
          </div>
        </div>
      ) : null}
    </div>
  );
}
