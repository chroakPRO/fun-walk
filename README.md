# Fun Path

Fun Path is a walking-route planner that compares the shortest route with
enjoyment-focused alternatives. The backend downloads a walkable OpenStreetMap
network, enriches its edges with nearby parks, woods, water, viewpoints,
attractions, and historic features, then searches for diverse routes within
explicit detour limits.

## What makes a route “fun”

The score combines:

- path character (trails, pedestrian streets, footways, and road exposure);
- surface and expected walking speed;
- nearby scenery, including features mapped separately from the path itself;
- safety signals such as sidewalks, road speed, lane count, tunnels, access,
  and difficult trail tags;
- feature variety, with diminishing returns so one heavily tagged area cannot
  dominate the whole route;
- detour and repeated-edge penalties.

The `MOST_FUN` route is limited to 45% extra distance, `BALANCED` to 25%, and
`PARK_HUNTER` to 60%. Alternatives are also checked for route overlap.

The planner can generate one selected style instead of computing everything:

- **Scenic & fun** for the most enjoyable general walk;
- **Parks & nature** for green areas, forests, and waterfronts;
- **Shopping** for shops, markets, cafés, restaurants, and pedestrian streets;
- **Balanced** for a smaller scenic detour;
- **Fastest** for direct walking; or
- **Compare all styles** when side-by-side alternatives are useful.

## Run With Docker

Start both services in Docker with hot reload:

```bash
./run.sh dev
```

To build and run production containers:

```bash
./run.sh prod
```

Running `./run.sh` without a mode prints usage and exits.

Extra Docker Compose `up` options can be passed after the mode:

```bash
./run.sh dev -d
```

The frontend is exposed at [http://localhost:3000](http://localhost:3000), and
the backend API is exposed at [http://localhost:8000](http://localhost:8000).
The Docker dev mode runs both services in development mode. Source files are
mounted into the containers, so frontend and backend code changes apply without
rebuilding the images. Python dependencies, Node dependencies, the Next.js build
cache, and the OSMnx cache stay in Docker volumes.

If you change `requirements.txt` or `fun-path-nextjs/package-lock.json`, rerun
the selected mode:

```bash
./run.sh dev
```

## Run locally without Docker

The app has a FastAPI routing backend and a Next.js frontend.

To start both without Docker:

```bash
./run-nodocker.sh
```

This creates `.venv` if needed, installs Python and Node dependencies, starts
the backend on port 8000, and starts the frontend on port 3000.

Or start each service manually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

In another terminal:

```bash
cd fun-path-nextjs
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The first route request in
an area can be slower because it downloads OSM network and feature data;
subsequent requests benefit from OSMnx's cache.

For a backend running elsewhere, set `ROUTING_API_URL` before starting Next.js:

```bash
ROUTING_API_URL=http://localhost:8000 npm run dev
```

### Satellite tree-cover data

Quiet-spot searches can verify vegetation with the Copernicus Data Space
Ecosystem Tree Cover Density layer. Put the CDSE credentials in the root
backend `.env` file (never in `fun-path-nextjs`):

```dotenv
CDSE_CLIENT_ID=your-client-id
CDSE_CLIENT_SECRET=your-client-secret
```

Local runs load this file in `api.py`. Docker Compose passes the same two
values only to the backend container, and `.env` is excluded from Git and
Docker build contexts. If CDSE is temporarily unavailable, searches continue
using the stricter OpenStreetMap-only checks. Tree-cover samples are stored in
`cache/tree_cover.sqlite3`; repeated coordinates are served locally without
spending another CDSE request. The cache is versioned so it can be invalidated
when the source layer or sampling method changes.

### Eye-level vegetation from NMD

For stronger screening estimates, download Naturvårdsverket's NMD 2023
`Objekthöjd/objekttäckning` ZIP archive. It is roughly 4.4 GB, so the app does
not download it automatically. Import only the two coverage rasters the scorer
needs:

```bash
python scripts/import_nmd_vegetation.py ~/Downloads/NMD2023_Tillaggsskikt_Objekthojd_objekttackning_v1_1.zip
```

The importer writes `data/nmd/low_vegetation_coverage.tif` (objects 0.5–5 m)
and `data/nmd/tall_vegetation_coverage.tif` (objects 5–45 m). The API detects
them automatically and stores sampled results in
`cache/vegetation_structure.sqlite3`. NMD files and caches are excluded from
Git and Docker images; Compose mounts the local NMD directory read-only into
the backend. Set `NMD_LOW_VEGETATION_RASTER` and
`NMD_TALL_VEGETATION_RASTER` if the files live elsewhere.

If disk space is limited, add `--low-only`. The low layer contains the primary
eye-level screening signal and works without the optional tall layer.

## Verification

```bash
python -m unittest -v test_api_routing.py
cd fun-path-nextjs
npm run lint
npm run build
```

The backend tests use synthetic graphs, so route-quality regressions can be
checked without calling OpenStreetMap services.
