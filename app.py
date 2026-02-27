from flask import Flask, request, render_template, jsonify
from sqlalchemy import create_engine, text
import pandas as pd
import os
from dotenv import load_dotenv
import json

load_dotenv()

app = Flask(__name__)
app.jinja_env.auto_reload = True
app.config['TEMPLATES_AUTO_RELOAD'] = True

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("No DATABASE_URL in env - falling back to local SQLite.")
    DATABASE_URL = 'sqlite:///nz_full_vehicles.db'
else:
    if 'supabase.co' in DATABASE_URL and 'sslmode' not in DATABASE_URL:
        DATABASE_URL += '?sslmode=require'
    print("Using Supabase:", DATABASE_URL.split('://')[0] + "://...")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)

# Load current total light passenger fleet from Supabase counts_current
total_fleet = 0
try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT SUM(count) FROM counts_current"))
        total_fleet = result.scalar() or 0
    print(f"Light passenger fleet loaded from Supabase: {total_fleet:,}")
except Exception as e:
    print(f"Error loading total fleet: {e}")
    total_fleet = 3603554  # fallback

@app.route('/')
def home():
    try:
        with open('nzta_makes_models_filtered.json', 'r', encoding='utf-8') as f:
            makes_models = json.load(f)
        makes = sorted(makes_models.keys())
    except Exception as e:
        print(f"Error loading makes/models JSON: {e}")
        makes = []
        makes_models = {}

    return render_template('index.html', makes=makes, makes_models=makes_models)

@app.route('/advanced-search')
def advanced_search():
    try:
        with open('nzta_makes_models_filtered.json', 'r', encoding='utf-8') as f:
            makes_models = json.load(f)
        makes = sorted(makes_models.keys())
    except Exception as e:
        print(f"Error loading makes/models JSON: {e}")
        makes = []
        makes_models = {}

    return render_template('advanced_search.html', makes=makes)

@app.route('/how-to-use')
def how_to_use():
    return render_template('how-to-use.html')

@app.route('/models')
def get_models():
    make = request.args.get('make', '').strip().upper()
    if not make:
        return jsonify([])

    print(f"Fetching models for make: {make}")
    sql = text("""
        SELECT model
        FROM counts_current
        WHERE make ILIKE :make
          AND model IS NOT NULL
          AND model != ''
        GROUP BY model
        ORDER BY
          CASE WHEN model ~ '^[A-Za-z]' THEN 0 ELSE 1 END ASC,
          LOWER(model) ASC
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {"make": make})
        models = [row[0].strip() for row in result if row[0] and row[0].strip()]

    print(f"Returning {len(models)} models for {make}")
    return jsonify(models)

@app.route('/submodels')
def get_submodels():
    make = request.args.get('make', '').strip().upper()
    models_list = request.args.getlist('models') or request.args.getlist('model[]') or request.args.getlist('models[]')
    print(f"DEBUG /submodels called with raw args: {request.args}")
    print(f"DEBUG make: '{make}', models_list: {models_list}")

    if not make or not models_list:
        print("DEBUG /submodels early return: missing make or models")
        return jsonify([])

    print(f"DEBUG Fetching submodels for make: {make}, models: {models_list}")

    sql = text("""
        SELECT COALESCE(submodel, '') AS submodel
        FROM counts_current
        WHERE make ILIKE :make
          AND model IN :models
        GROUP BY COALESCE(submodel, '')
        ORDER BY
          CASE 
            WHEN COALESCE(submodel, '') = ''                  THEN 0
            WHEN COALESCE(submodel, '') ~ '^[A-Za-z]' THEN 1
            ELSE 2
          END ASC,
          LOWER(COALESCE(submodel, '')) ASC
    """)
    params = {"make": make, "models": tuple(models_list)}

    print(f"DEBUG executing SQL: {sql} with params: {params}")

    with engine.connect() as conn:
        try:
            result = conn.execute(sql, params)
            submodels = [row[0] for row in result]
            print(f"DEBUG query returned {len(submodels)} submodels")
        except Exception as e:
            print(f"DEBUG SQL error: {str(e)}")
            submodels = []

    print(f"Returning {len(submodels)} submodels (including blanks)")
    return jsonify(submodels)

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        make = request.form.get('make', '').strip().upper()
        models = request.form.getlist('model') or request.form.getlist('model[]')
        submodels = request.form.getlist('submodel') or request.form.getlist('submodel[]')
        year_from = request.form.get('year_from', '')
        year_to = request.form.get('year_to', '')
        keywords = request.form.get('keywords', '').strip().upper()
        fuel_types = request.form.getlist('fuel_type') or request.form.getlist('fuel_type[]')
    else:
        query = request.args.get('query', '').strip()
        make = request.args.get('make', '').strip().upper()
        models = request.args.getlist('model') or request.args.getlist('model[]')
        submodels = request.args.getlist('submodel') or request.args.getlist('submodel[]')
        year_from = request.args.get('year_from', '')
        year_to = request.args.get('year_to', '')
        keywords = request.args.get('keywords', '').strip().upper()
        fuel_types = request.args.getlist('fuel_type') or request.args.getlist('fuel_type[]')

    print(f"DEBUG search params: query='{query}', make='{make}', models={models}, submodels={submodels}, year_from='{year_from}', year_to='{year_to}', keywords='{keywords}', fuel_types={fuel_types}")

    use_advanced = make or models or submodels or year_from or year_to or keywords or fuel_types
    if use_advanced:
        print("DEBUG: Advanced params detected → using advanced filtering")
        query = ''
    else:
        print("DEBUG: No advanced params → using single-box fallback")

    where_clauses = []
    params = {}

    if query and not use_advanced:
        query_upper = query.upper().strip()
        words = query_upper.split()  # split into words
        if words:
            clauses = []
            for i, word in enumerate(words):
                key = f'q{i}'
                params[key] = f"%{word}%"
                clauses.append(f"(make ILIKE :{key} OR model ILIKE :{key} OR submodel ILIKE :{key})")
            where_clauses.append(" AND ".join(clauses))
        else:
            params['query'] = '%%'
            where_clauses.append("TRUE")
    else:
        if make:
            params['make'] = f"%{make}%"
            where_clauses.append("make ILIKE :make")

        if models:
            where_clauses.append("model IN :models")
            params['models'] = tuple(models)

        if submodels:
            where_clauses.append("submodel IN :submodels")
            params['submodels'] = tuple(submodels)

        if year_from:
            try:
                params['year_from'] = int(year_from)
                where_clauses.append("vehicle_year >= :year_from")
            except ValueError:
                pass

        if year_to:
            try:
                params['year_to'] = int(year_to)
                where_clauses.append("vehicle_year <= :year_to")
            except ValueError:
                pass

        if keywords:
            params['keywords'] = f"%{keywords}%"
            where_clauses.append("(make ILIKE :keywords OR model ILIKE :keywords OR submodel ILIKE :keywords)")

        if fuel_types:
            where_clauses.append("fuel_type IN :fuel_types")
            params['fuel_types'] = tuple(fuel_types)

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    print(f"DEBUG WHERE clause: {where_sql}")
    print(f"DEBUG params: {params}")

    # Build human-readable search summary – no quotes for home page search
    search_summary_parts = []
    if query and not use_advanced:
        search_summary_parts.append(query.strip())
    else:
        if make:
            search_summary_parts.append(make.title())
        if models:
            model_str = " ".join([m.title() for m in models if m])
            if model_str:
                search_summary_parts.append(model_str)
        if submodels and any(s.strip() for s in submodels):
            sub_str = ", ".join([s.strip() for s in submodels if s.strip()])
            if sub_str:
                search_summary_parts.append(f"+ {sub_str}")
        if year_from or year_to:
            year_range = f"{year_from or 'Any'}–{year_to or 'Any'}"
            search_summary_parts.append(f"({year_range})")
        if keywords:
            search_summary_parts.append(f'keywords "{keywords}"')
        if fuel_types:
            search_summary_parts.append(f"fuel: {', '.join(fuel_types)}")

    search_summary = " ".join(search_summary_parts) if search_summary_parts else "All Vehicles"

    try:
        combined_sql = text(f"""
            WITH filtered AS (
                SELECT vehicle_year, fuel_type, count
                FROM counts_current
                WHERE {where_sql}
            ),
            total_agg AS (
                SELECT COALESCE(SUM(count), 0) AS total FROM filtered
            ),
            yearly_agg AS (
                SELECT vehicle_year, COALESCE(SUM(count), 0) AS count
                FROM filtered
                GROUP BY vehicle_year
            ),
            fuel_agg AS (
                SELECT fuel_type, COALESCE(SUM(count), 0) AS count
                FROM filtered
                GROUP BY fuel_type
            )
            SELECT 
                (SELECT total FROM total_agg) AS total,
                (SELECT COALESCE(json_agg(json_build_object('year', vehicle_year, 'count', count) ORDER BY vehicle_year), '[]') 
                 FROM yearly_agg) AS yearly,
                (SELECT COALESCE(json_agg(json_build_object('fuel', fuel_type, 'count', count) ORDER BY count DESC), '[]') 
                 FROM fuel_agg) AS fuel
        """)

        with engine.connect() as conn:
            result = conn.execute(combined_sql, params).fetchone()

        total = int(result[0]) if result[0] is not None else 0
        yearly_json = result[1] or '[]'
        fuel_json = result[2] or '[]'

        def safe_json_parse(val):
            if val is None:
                return []
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except json.JSONDecodeError as e:
                    print(f"JSON decode failed: {e} on value: {val}")
                    return []
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                return [val]
            print(f"Unexpected type in JSON parse: {type(val)} - value: {val}")
            return []

        yearly_list = safe_json_parse(yearly_json)
        fuel_list = safe_json_parse(fuel_json)

        if total == 0:
            return render_template('results.html', search_summary=search_summary, total=0, rarity='N/A', error="No matching vehicles found")

        # Rarity calculation: relative to current total fleet
        rarity = total_fleet // total if total > 0 else 'N/A'

        # Tail-heavy thresholds focused on rare/classic cars
        rarity_level = {'quality': 'N/A', 'hex': '#6c757d'}
        if rarity != 'N/A':
            if rarity < 500:
                rarity_level = {'quality': 'Very Common', 'hex': '#0d6efd'}
            elif rarity < 2000:
                rarity_level = {'quality': 'Common', 'hex': '#28a745'}
            elif rarity < 10000:
                rarity_level = {'quality': 'Uncommon', 'hex': '#ffc107'}
            elif rarity < 40000:
                rarity_level = {'quality': 'Rare', 'hex': '#fd7e14'}
            else:
                rarity_level = {'quality': 'Very Rare', 'hex': '#dc3545'}

            if total < 1000 and rarity > 20000:
                rarity_level = {'quality': 'Very Rare', 'hex': '#dc3545'}

        years = [str(item.get('year', '')) for item in yearly_list if isinstance(item, dict)]
        counts_per_year = [item.get('count', 0) for item in yearly_list if isinstance(item, dict)]
        table_data = [
            {'vehicle_year': item.get('year', ''), 'count': item.get('count', 0)}
            for item in yearly_list if isinstance(item, dict)
        ]
        table_data = sorted(table_data, key=lambda x: x['vehicle_year'], reverse=True)

        fuel_labels = [item.get('fuel') or 'Unknown' for item in fuel_list if isinstance(item, dict)]
        fuel_data = [item.get('count', 0) for item in fuel_list if isinstance(item, dict)]

        variants_sql = text(f"""
            SELECT make, model, submodel, vehicle_year, fuel_type, count
            FROM counts_current
            WHERE {where_sql}
            ORDER BY count DESC
            LIMIT 100
        """)
        variants_df = pd.read_sql(variants_sql, engine, params=params)

        by_gen = {}
        if 'generation' in variants_df.columns:
            by_gen = variants_df.groupby('generation')['count'].sum().to_dict()

        return render_template(
            'results.html',
            search_summary=search_summary,
            total=total,
            rarity=rarity,
            rarity_level=rarity_level,
            by_gen=by_gen,
            years=years,
            counts_per_year=counts_per_year,
            fuel_labels=fuel_labels,
            fuel_data=fuel_data,
            table_data=table_data,
            results=variants_df.to_dict('records')
        )

    except Exception as e:
        print(f"Search error: {str(e)}")
        return render_template('results.html', search_summary="Search Error", total=0, rarity='N/A', error="Database error – please try again")

@app.route('/test-db')
def test_db():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
        return f"Database connected! Test query returned: {result}"
    except Exception as e:
        return f"Connection failed: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)