import pandas as pd
import urllib.request
import zipfile
import io
from sqlalchemy import create_engine

print("=== NZ Vehicle Database Builder (NZTA Data as at 30 Nov 2025) ===\n")

DB_FILE = 'nz_vehicles.db'
engine = create_engine(f'sqlite:///{DB_FILE}')

all_dfs = []

# Pre-1990
pre_url = "https://wksprdgisopendata.blob.core.windows.net/motorvehicleregister/VehicleYear-Pre1990.zip"
print("Fetching pre-1990...")
try:
    with urllib.request.urlopen(pre_url) as resp:
        zip_data = io.BytesIO(resp.read())
        with zipfile.ZipFile(zip_data) as z:
            csv_file = next(n for n in z.namelist() if n.lower().endswith('.csv'))
            with z.open(csv_file) as f:
                df = pd.read_csv(f, low_memory=False)
                df.columns = df.columns.str.lower().str.strip()
                df['make'] = df['make'].fillna('').astype(str).str.upper().str.strip()
                df['model'] = df['model'].fillna('').astype(str).str.upper().str.strip()
                all_dfs.append(df)
                print("Pre-1990 loaded.")
except Exception as e:
    print(f"Pre-1990 error: {e}")

# Yearly
year = 1990
while year <= 2026:
    url = f"https://wksprdgisopendata.blob.core.windows.net/motorvehicleregister/VehicleYear-{year}.csv"
    print(f"Fetching {year}...")
    try:
        with urllib.request.urlopen(url) as resp:
            df = pd.read_csv(io.StringIO(resp.read().decode('utf-8')), low_memory=False)
            df.columns = df.columns.str.lower().str.strip()
            df['make'] = df['make'].fillna('').astype(str).str.upper().str.strip()
            df['model'] = df['model'].fillna('').astype(str).str.upper().str.strip()
            all_dfs.append(df)
            print(f"{year} loaded.")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("End of data.")
            break
        else:
            print(f"Error: {e}")
            break
    except Exception as e:
        print(f"Error: {e}")
        break
    year += 1

# Combine and save to DB
if all_dfs:
    combined = pd.concat(all_dfs, ignore_index=True)
    combined.to_sql('vehicles', engine, if_exists='replace', index=False)
    print("\nDatabase created/updated: nz_vehicles.db")
    print("Total vehicles: ", len(combined))
else:
    print("No data loaded.")

input("Press Enter to exit...")