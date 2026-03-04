from flask import Flask, request, render_template, jsonify
from sqlalchemy import create_engine, text
import pandas as pd
import os
from dotenv import load_dotenv
import json
import logging
from collections import defaultdict

# Set up logging (shows in Vercel function logs)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Only load .env in local development (Vercel uses real env vars)
if os.getenv('VERCEL') is None:
    load_dotenv()

app = Flask(__name__)
app.jinja_env.auto_reload = True
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    logger.warning("No DATABASE_URL in env - falling back to local SQLite.")
    DATABASE_URL = 'sqlite:///nz_full_vehicles.db'
else:
    if 'supabase.co' in DATABASE_URL and 'sslmode' not in DATABASE_URL:
        DATABASE_URL += '?sslmode=require'
    logger.info("Using Supabase: %s://...", DATABASE_URL.split('://')[0])

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)

# Load total fleet
total_fleet = 0
try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT SUM(count) FROM counts_current"))
        total_fleet = result.scalar() or 0
    logger.info("Light passenger fleet loaded: %s", f"{total_fleet:,}")
except Exception as e:
    logger.error("Error loading total fleet: %s", str(e))
    total_fleet = 3603554  # fallback

# Path to curated per-make JSON files
FILTERED_MAKES_DIR = os.path.join(os.path.dirname(__file__), 'filtered_makes')

def get_all_makes_from_folder():
    """Scan filtered_makes/ folder and extract make names from filenames"""
    makes = []
    if not os.path.exists(FILTERED_MAKES_DIR):
        logger.warning(f"filtered_makes directory not found: {FILTERED_MAKES_DIR}")
        return []
    
    for filename in os.listdir(FILTERED_MAKES_DIR):
        if filename.endswith('.json'):
            # Reverse safe_make transformation: filename → make name
            # e.g. TOYOTA.json → TOYOTA, MAZDA_3.json → MAZDA 3
            make_name = filename[:-5].replace('_', ' ')
            makes.append(make_name)
    
    makes = sorted(set(makes))  # dedupe + alphabetical
    logger.info(f"Loaded {len(makes)} makes from filtered_makes folder")
    return makes

@app.route('/')
def home():
    makes = get_all_makes_from_folder()
    return render_template('home.html', makes=makes)

@app.route('/api/make/<make>')
def api_make_data(make):
    """Serve curated make data from filtered_makes/*.json for frontend dropdowns"""
    if not make:
        return jsonify({"error": "No make provided"}), 400

    # Normalize filename to match generation script
    safe_make = make.strip().upper().replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_')
    file_path = os.path.join(FILTERED_MAKES_DIR, f"{safe_make}.json")

    if not os.path.exists(file_path):
        logger.warning(f"Make JSON not found: {file_path}")
        return jsonify([])  # empty → frontend shows no options

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {file_path}: {e}")
        return jsonify({"error": "Invalid JSON"}), 500
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return jsonify({"error": "Server error"}), 500

@app.route('/browse')
def browse():
    """A-Z browse page for makes"""
    try:
        sql = text("""
            SELECT DISTINCT make
            FROM counts_current
            WHERE make IS NOT NULL AND make != ''
            ORDER BY make ASC
        """)
        
        with engine.connect() as conn:
            result = conn.execute(sql)
            all_makes = [row[0].strip() for row in result if row[0] and row[0].strip()]

        grouped = defaultdict(list)
        for make in all_makes:
            first_char = make[0].upper() if make else '?'
            group_key = '0-9' if first_char.isdigit() else first_char
            grouped[group_key].append(make)

        for key in grouped:
            grouped[key] = sorted(set(grouped[key]))

        letters = sorted([k for k in grouped if k != '0-9'])
        if '0-9' in grouped:
            letters.append('0-9')

        grouped_makes = {letter: grouped[letter] for letter in letters}

        return render_template('browse.html', grouped_makes=grouped_makes)

    except Exception as e:
        logger.exception("Error in browse")
        return render_template('browse.html', grouped_makes={}, error=str(e)), 500

@app.route('/browse/<make>')
def browse_make(make):
    """Show all models for a specific make"""
    try:
        make_clean = make.strip().upper()

        sql_models = text("""
            SELECT DISTINCT model
            FROM counts_current
            WHERE make ILIKE :make
              AND model IS NOT NULL
              AND model != ''
            ORDER BY model ASC
        """)

        with engine.connect() as conn:
            result = conn.execute(sql_models, {"make": make_clean})
            models = [row[0].strip() for row in result if row[0] and row[0].strip()]

        logger.info(f"Models for {make_clean}: {len(models)} found")

        return render_template(
            'browse_make.html',
            make=make_clean,
            models=models
        )

    except Exception as e:
        logger.exception(f"Error in browse_make for {make}")
        return render_template(
            'browse_make.html',
            make=make,
            models=[],
            error=str(e)
        ), 500

@app.route('/advanced-search')
def advanced_search():
    makes = get_all_makes_from_folder()
    return render_template('advanced_search.html', makes=makes)

@app.route('/how-to-use')
def how_to_use():
    return render_template('how-to-use.html')

# Legacy routes (optional – can be removed if not used anymore)
@app.route('/models')
def get_models():
    make = request.args.get('make', '').strip().upper()
    if not make:
        return jsonify([])

    logger.info("Fetching models for make: %s", make)
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

    logger.info("Returning %d models for %s", len(models), make)
    return jsonify(models)

@app.route('/submodels')
def get_submodels():
    make = request.args.get('make', '').strip().upper()
    models_list = request.args.getlist('models') or request.args.getlist('model[]') or request.args.getlist('models[]')
    if not make or not models_list:
        return jsonify([])

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

    with engine.connect() as conn:
        try:
            result = conn.execute(sql, params)
            submodels = [row[0] for row in result]
        except Exception as e:
            logger.error("SQL error in /submodels: %s", str(e))
            submodels = []

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

    logger.info("DEBUG search params: query='%s', make='%s', models=%s, submodels=%s, year_from='%s', year_to='%s', keywords='%s', fuel_types=%s",
                query, make, models, submodels, year_from, year_to, keywords, fuel_types)

    use_advanced = make or models or submodels or year_from or year_to or keywords or fuel_types
    if use_advanced:
        logger.info("DEBUG: Advanced params detected → using advanced filtering")
        query = ''
    else:
        logger.info("DEBUG: No advanced params → using single-box fallback")

    where_clauses = []
    params = {}

    if query and not use_advanced:
        query_upper = query.upper().strip()
        words = query_upper.split()
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
    logger.info("DEBUG WHERE clause: %s", where_sql)
    logger.info("DEBUG params: %s", params)

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
                    logger.error("JSON decode failed: %s on value: %s", e, val)
                    return []
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                return [val]
            logger.warning("Unexpected type in JSON parse: %s - value: %s", type(val), val)
            return []

        yearly_list = safe_json_parse(yearly_json)
        fuel_list = safe_json_parse(fuel_json)

        if total == 0:
            return render_template('results.html', search_summary=search_summary, total=0, rarity='N/A', error="No matching vehicles found")

        rarity = total_fleet // total if total > 0 else 'N/A'

        rarity_level = {'quality': 'N/A', 'hex': '#6c757d'}
        if rarity != 'N/A':
            if total > 100000:
                rarity_level = {'quality': 'Extremely Common', 'hex': '#28a745'}
            elif total >= 30000:
                rarity_level = {'quality': 'Very Common', 'hex': '#198754'}
            elif total >= 10000:
                rarity_level = {'quality': 'Common', 'hex': '#0d6efd'}
            elif total >= 3000:
                rarity_level = {'quality': 'Fairly Uncommon', 'hex': '#ffc107'}
            elif total >= 1000:
                rarity_level = {'quality': 'Uncommon', 'hex': '#fd7e14'}
            elif total >= 300:
                rarity_level = {'quality': 'Rare', 'hex': '#fb923c'}
            elif total >= 100:
                rarity_level = {'quality': 'Very Rare', 'hex': '#f87171'}
            else:
                rarity_level = {'quality': 'Extremely Rare', 'hex': '#dc3545'}

        rarity_colors = [
            '#00FF7F', '#00FA9A', '#00BFFF', '#FFD700',
            '#FF8C00', '#FF6347', '#FF3366', '#C71585'
        ]

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
            results=variants_df.to_dict('records'),
            rarity_colors=rarity_colors
        )

    except Exception as e:
        logger.error("Search error: %s", str(e))
        return render_template('results.html', search_summary="Search Error", total=0, rarity='N/A', error="Database error – please try again")

@app.route('/test-db')
def test_db():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
        return f"Database connected! Test query returned: {result}"
    except Exception as e:
        logger.error("DB test connection failed: %s", str(e))
        return f"Connection failed: {str(e)}", 500

# Required for Vercel/gunicorn serverless deployment
application = app

if __name__ == '__main__':
    # Local development only
    app.run(debug=True, host='0.0.0.0', port=5000)