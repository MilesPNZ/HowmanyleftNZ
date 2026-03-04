# How Many Left? NZ - Project Brief

## Overview
How Many Left? NZ (live at [howmanyleft.co.nz](https://www.howmanyleft.co.nz)) is a New Zealand clone of the UK site [howmanyleft.co.uk](https://www.howmanyleft.co.uk). It shows real-time registration counts for vehicles from NZTA (NZ Transport Agency) public data, helping users discover rarity, trends, and availability (e.g., \"How many Toyota AE86 left?\" or \"Ford Falcon XT by year?\").

**Target Userbase:** Car enthusiasts, classic car collectors, buyers/sellers checking market rarity, researchers (NZ vehicle stats by make/model/year/fuel).

**Core Value/IP:** Public NZTA data is raw/messy (typos, junk like \"UNKNOWN\", duplicates, low-count gibberish). Site's edge is **curated, clean data** (filtered_makes JSON per make) for perfect UX/search. Commit to accuracy 100%, updates 6mo → 3mo.

Local dev: `E:\Cloud Shared Files\Website projects\Git Repo\HowmanyleftNZ`
Hosted: Vercel (GitHub repo auto-deploy).

## Tech Stack
- **Backend:** Python 3.14 + Flask (routes `@app.route`, gunicorn Vercel).
- **Frontend:** Jinja2 templates + Bootstrap 5.3.3 (responsive) + Tom Select 2.3.1 (searchable dropdowns, multi-select).
- **JS:** Vanilla jQuery (advanced_search), Bootstrap JS (navbar).
- **No heavy frameworks** (React/Vue) – lightweight, fast.

## Database
**Production:** PostgreSQL on Supabase (hosted, scalable).
- Main table: `counts_current` (aggregated stats):
  ```
  make (str), model (str), submodel (str), vehicle_year (int), fuel_type (str), class (str), count (int), snapshot_date (date)
  ```
  - Indexes: pg_trgm (ILIKE search), make/model/year/fuel/count.
  - Queries: Text SQLAlchemy for performance (e.g., GROUP BY make/model).

**Local Dev:** SQLite `nz_vehicles.db` (~34MB post-clean/VACUUM).
- Import: Python script from NZTA CSVs.
- Upload to Supabase: pgloader (Docker).

## Data Pipeline
1. **Raw Source:** NZTA CSVs (`VehicleYear-*.csv` + `Pre1990.zip`).
2. **Import/Aggregate (local Python):** Raw vehicles → `counts_current` (GROUP BY make/model/submodel/year/fuel/class, SUM(count)).
3. **Curation (your IP):** 
   - `makes/` folder: One JSON/make (e.g., `ALFA ROMEO.json`):
     ```
     [
       {"model": "GIULIA", "count": 403, "submodels": ["1300 SUPER", "1600 SPRINT", ...]},
       {"model": "TL105", "count": 1, "submodels": [], "is_relevant": false, "reason": "..."}
     ]
     ```
   - Process: Flag low-count (<=20) junk (UNKNOWN/ABC123/TRAILER), dedupe typos, verify web (Wikipedia/TradeMe NZ). NOTE - This process is a work in progress. 
4. **UI Data:** Filtered JSON loaded dynamically (Tom Select Make → Models).
5. **Updates:** Script fetch → aggregate → curate → deploy (6mo → 3mo).

## Features
1. **Home Quick Search:**
   - Hero image (NZ classics) + overlay form.
   - Tom Select: Make (single), Model (multi), Year range, Keywords.
   - \"Search Now\" → results page.

2. **Advanced Search:**  
   - Make (single), Model/Submodel (multi), Year From/To, Fuel (multi), Keywords.
   - Real-time SQL query → table/chart results.

3. **Browse/Index (A-Z):**
   - All makes by letter → make page (models list) → model details (years/counts).

4. **Results Page:** - Need to add persistent search bar that retains last search for user to tweak. 
   - Aggregated table/chart: Total, by year/fuel/class.
   - Pandas backend for grouping/sorting.

## Data Cleaning Challenge (Biggest Priority)
- **Problems:** Raw NZTA full of junk:
  | Junk Type | Examples |
  |-----------|----------|
  | Placeholders | UNKNOWN, TEST, N/A, MISC, OTHER |
  | Codes | ABC123, XYZ-999, TL105 |
  | Non-vehicles | TRAILER, TRACTOR, BOAT, PART |
  | Typos/Dups | \"Corolla \" vs \"Corolla\", low-count gibberish |
  | BMW/Ford Falcon mess | 100s submodels with junk/low-count.

- **Solution:** Python curation script:
  - Load counts_current → per-make JSON.
  - Flag/review low-count (<=20): web_search \"[make] [model] NZ car\" → false if junk, true if real classic/import.
  - Dedupe/merge variants (e.g., Corolla LE/GLE → submodels).
  - Output clean filtered_makes/ for UI.

**Automation Goal:** Script + AI (Grok) for 95% auto-clean, manual rares.

## Roadmap/Goals
- **Short-term:** Perfect data curation (makes/ clean), mobile UX tweaks.
- **Medium:** 3mo auto-updates, charts (years trends), compare UK/NZ.
- **Long:** Monetize (ads/premium stats), API, mobile app.
- **Metrics:** 100% accuracy, <2s search, 1k monthly users Year 1.

Paste this MD to new Grok chats for continuity. Update as evolves.

Last updated: 2026-03-04