# Schooner Weather

Which side of the pub is in the sun. Type an address, get a metre-by-metre sun chart for each street the building faces.

The site is a Next.js app on Vercel. The shade math stays in Python (GDAL, OSM, Google Solar) and runs on Railway. There is no database and no login.

## Local

You need a [Google Solar API](https://developers.google.com/maps/documentation/solar) key.

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# put GOOGLE_KEY=... in .env
python run.py
# do not use: uvicorn main:app --reload
# that watches .venv and restarts in a loop
```

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The Next app proxies `/api/*` to the Python server. `/?demo=1` shows a sample chart without the API.

The first lookup for a place downloads a height map and caches it in `api/cache/`. Later lookups for the same address reuse that file.

## Deploy

1. Push this repo.
2. **Railway** — new service, root directory `api`, Dockerfile. Set `GOOGLE_KEY`. Mount a volume at `/data` (the image already sets `CACHE_DIR=/data`). Add `CORS_ORIGINS` if you ever call the API from the browser directly.
3. **Vercel** — new project, root directory `web`. Set `API_URL` to the Railway public URL (no trailing slash), e.g. `https://schooner-weather.up.railway.app`.

That is the whole stack. Supabase is not used.

## API

- `POST /analyze` `{ "address": "...", "date": "2026-09-24" }` → `{ "jobId": "..." }`
- `GET /jobs/{id}` → queued / running / done / error
- `GET /health`

Times are Australia/Melbourne. Defaults match the original CLI: seated eye height 1.2 m, tables 1.5 m off the wall, sun checked every 5 minutes.
