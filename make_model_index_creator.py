# generate_filtered_makes.py
# Creates one JSON file per make in 'filtered_makes' folder
# Structure: list of models with total count and simple submodels array (no counts)
# Models sorted by total count DESC → submodels sorted alphabetically
# Filtered to passenger/light classes (MA, MB)

import sqlite3
import json
import os
from collections import defaultdict

# === CONFIG ===
DB_PATH = r"E:\Website projects\Database\nz_vehicles.db"
OUTPUT_FOLDER = "filtered_makes"
TABLE_NAME = "counts_current"  # aggregated table

# Check DB exists
if not os.path.isfile(DB_PATH):
    print(f"ERROR: Database not found at: {DB_PATH}")
    exit(1)

print(f"Connecting to: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Step 1: Get all unique makes (passenger/light only)
makes_query = f"""
    SELECT DISTINCT make
    FROM {TABLE_NAME}
    WHERE make != '' AND make IS NOT NULL
      AND class IN ('MA', 'MB')
    ORDER BY UPPER(make) ASC
"""
cursor.execute(makes_query)
makes = [row[0].strip() for row in cursor.fetchall() if row[0] and row[0].strip()]

print(f"Found {len(makes)} unique makes (passenger/light only).")

# Create output folder
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Step 2: Process each make
for idx, make in enumerate(makes, 1):
    print(f"[{idx}/{len(makes)}] Processing: {make}")

    # Get models + total count per model
    models_query = f"""
        SELECT 
            model,
            SUM(count) as model_total
        FROM {TABLE_NAME}
        WHERE make = ?
          AND model != '' AND model IS NOT NULL
          AND class IN ('MA', 'MB')
        GROUP BY model
        ORDER BY model_total DESC, LOWER(model) ASC
    """
    cursor.execute(models_query, (make,))
    model_rows = cursor.fetchall()

    if not model_rows:
        print(f"  → Skipping {make} (no models)")
        continue

    models_data = []

    for model_name_raw, model_total in model_rows:
        model_name = model_name_raw.strip()
        if not model_name:
            continue

        # Get unique submodels (no counts)
        sub_query = f"""
            SELECT DISTINCT COALESCE(submodel, 'Base') as sub_name
            FROM {TABLE_NAME}
            WHERE make = ?
              AND model = ?
              AND class IN ('MA', 'MB')
            ORDER BY LOWER(sub_name) ASC
        """
        cursor.execute(sub_query, (make, model_name))
        sub_rows = cursor.fetchall()

        submodels_list = []
        seen = set()
        for (sub_raw,) in sub_rows:
            sub_name = sub_raw.strip()
            if sub_name and sub_name not in seen:
                submodels_list.append(sub_name)
                seen.add(sub_name)

        models_data.append({
            "model": model_name,
            "count": model_total or 0,
            "submodels": submodels_list
        })

    if not models_data:
        continue

    # Safe filename (avoid invalid chars)
    safe_make = make.replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_')
    file_path = os.path.join(OUTPUT_FOLDER, f"{safe_make}.json")

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(models_data, f, indent=2, ensure_ascii=False)

    print(f"  → Saved {len(models_data)} models to {file_path}")

conn.close()

# Final summary
print("\n=== Export complete ===")
exported_count = len([f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.json')])
print(f"Total makes exported: {exported_count}")

print("\nPreview of first 5 makes (showing top 2 models + submodel count):")
preview_files = sorted([f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.json')])[:5]

for file in preview_files:
    with open(os.path.join(OUTPUT_FOLDER, file), 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not data:
        continue
    preview_lines = []
    for m in data[:2]:
        line = f"  {m['model']} ({m['count']})"
        if m['submodels']:
            line += f" → {len(m['submodels'])} submodels"
        preview_lines.append(line)
    print(f"{file.replace('.json', '')}:")
    print("\n".join(preview_lines))
    print(f"  (total models: {len(data)})\n")

print("\nNext steps for curation:")
print("1. Open filtered_makes/*.json")
print("2. For each make:")
print("   - Review models from top (highest count) to bottom")
print("   - Delete junk models (low count ≤20, typos, 'UNKNOWN', 'TEST', codes like 'ABC123')")
print("   - For real models: review/fix submodels list")
print("     - Delete junk subs")
print("     - Rename/normalize (e.g. 'LE ' → 'LE')")
print("     - Add 'is_relevant': true/false, 'reason': '...' for borderline cases later")
print("3. Save → git add/commit/push → Vercel redeploys")