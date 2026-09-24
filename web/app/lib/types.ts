export type LatLon = { lat: number; lon: number };

export type Front = {
  name: string;
  lengthM: number;
  start: string;
  end: string;
  someSun: string;
  wholeFrontage: string;
  points?: LatLon[];
  rows: { time: string; cells: boolean[] }[];
};

export type Result = {
  building: {
    name: string;
    lat: number;
    lon: number;
    quality: string;
    imageryDate: string;
    outline?: LatLon[];
  };
  date: string;
  groundM: number;
  offsetM: number;
  streets: string[];
  fronts: Front[];
};

export type Job =
  | { status: "queued" | "running"; message?: string }
  | { status: "done"; result: Result }
  | { status: "error"; error: string };
