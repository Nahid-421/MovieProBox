import os
import sys
import requests
import json
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import unquote, quote
from datetime import datetime
import math
import re

# =====================================================================
# === [CONFIGURATION & ENVIRONMENT] ===================================
# =====================================================================

# --- Core Configuration ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Demo270:Demo270@cluster0.ls1igsg.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Nahid421")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Nahid421")
WEBSITE_NAME = os.environ.get("WEBSITE_NAME", "NovaFlix Stream")
DEVELOPER_TELEGRAM_ID = os.environ.get("DEVELOPER_TELEGRAM_ID", "https://t.me/AllBotUpdatemy")

# --- Telegram & Auto-Post Settings ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID") # Channel ID to monitor/post to (Optional for webhook, used for security check)
WEBSITE_URL = os.environ.get("WEBSITE_URL") 
AUTO_POST_SECRET = os.environ.get("AUTO_POST_SECRET", "change_this_secret_key_for_security") 

# --- App Initialization ---
PLACEHOLDER_POSTER = "https://via.placeholder.com/400x600.png?text=Poster+Not+Found"
ITEMS_PER_PAGE = 20
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_super_secret_key_for_flash_messages")


# =====================================================================
# === [DB SETUP, AUTH & HELPERS] ======================================
# =====================================================================

# --- Database Connection ---
try:
    client = MongoClient(MONGO_URI)
    db = client["movie_db"]
    movies = db["movies"]
    settings = db["settings"]
    categories_collection = db["categories"]
    requests_collection = db["requests"]
    ott_collection = db["ott_platforms"]
    print("SUCCESS: Successfully connected to MongoDB!")

    if categories_collection.count_documents({}) == 0:
        default_categories = ["Trending", "Bangla", "Hindi", "English", "Series", "Action", "Romance"]
        categories_collection.insert_many([{"name": cat} for cat in default_categories])
    
    # Ensure indexes exist
    movies.create_index("title")
    movies.create_index("type")
    
except Exception as e:
    print(f"FATAL: Error connecting to MongoDB: {e}.")


# --- Authentication (standard) ---
def check_auth(username, password): return username == ADMIN_USERNAME and password == ADMIN_PASSWORD
def authenticate(): return Response('Could not verify your access level.', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password): return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- Helper Functions ---
def format_series_info(episodes, season_packs):
    # This is simplified for stream only, focusing on episode numbering
    info_parts = []
    if episodes:
        episodes_by_season = {};
        for ep in episodes:
            season = ep.get('season'); ep_num = ep.get('episode_number')
            if season is not None and ep_num is not None:
                episodes_by_season.setdefault(season, []).append(ep_num)
        for season in sorted(episodes_by_season.keys()):
            ep_nums = sorted(episodes_by_season[season])
            if not ep_nums: continue
            ep_range = f"EP{ep_nums[0]:02d}" if len(ep_nums) == 1 else f"EP{ep_nums[0]:02d}-{ep_nums[-1]:02d}"
            info_parts.append(f"S{season:02d} [{ep_range} ADDED]")
    return " & ".join(info_parts)

def send_telegram_notification(movie_data, content_id, notification_type='new', series_update_info=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID or not WEBSITE_URL: return
    try:
        movie_url = f"{WEBSITE_URL}/movie/{str(content_id)}"
        title_with_year = movie_data.get('title', 'N/A')
        quality_str = "WEB-DL"; language_str = movie_data.get('language', 'N/A')
        genres_str = ", ".join(movie_data.get('genres', [])) if movie_data.get('genres') else "N/A"
        clean_url = WEBSITE_URL.replace('https://', '').replace('www.', '')
        
        caption_header = f"🔥 **NEW STREAM : {title_with_year}**\n"
        caption = caption_header
        caption += f"\n🌐 Language: **{language_str}**"
        caption += f"\n🎭 Genres: **{genres_str}**"
        caption += f"\n\n🔗 Visit : **{clean_url}**"

        inline_keyboard = {"inline_keyboard": [[{"text": "▶️ Watch Now", "url": movie_url}]]}
        api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {'chat_id': TELEGRAM_CHANNEL_ID, 'photo': movie_data.get('poster', PLACEHOLDER_POSTER), 'caption': caption, 'parse_mode': 'Markdown', 'reply_markup': json.dumps(inline_keyboard)}
        
        requests.post(api_url, data=payload, timeout=15).raise_for_status()
    except Exception as e:
        print(f"ERROR: Failed to send Telegram notification: {e}")

def get_tmdb_details(tmdb_id, media_type):
    if not TMDB_API_KEY: return None
    search_type = "tv" if media_type == "series" else "movie"
    try:
        detail_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}?api_key={TMDB_API_KEY}"
        res = requests.get(detail_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        details = { "tmdb_id": tmdb_id, "title": data.get("title") or data.get("name"), "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None, "backdrop": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get('backdrop_path') else None, "overview": data.get("overview"), "release_date": data.get("release_date") or data.get("first_air_date"), "genres": [g['name'] for g in data.get("genres", [])], "vote_average": data.get("vote_average"), "type": "series" if search_type == "tv" else "movie", "original_language": data.get("original_language") }
        return details
    except requests.RequestException as e: return None

def time_ago(obj_id):
    if not isinstance(obj_id, ObjectId): return ""
    post_time = obj_id.generation_time.replace(tzinfo=None)
    now = datetime.utcnow()
    seconds = (now - post_time).total_seconds()
    if seconds < 60: return "just now"
    elif seconds < 3600: minutes = int(seconds / 60); return f"{minutes} min ago"
    elif seconds < 86400: hours = int(seconds / 3600); return f"{hours} hour ago"
    else: days = int(seconds / 86400); return f"{days} day ago"

app.jinja_env.filters['time_ago'] = time_ago
app.jinja_env.filters['striptags'] = lambda x: x
app.jinja_env.filters['truncate'] = lambda s, length: s[:length] + '...' if len(s) > length else s

class Pagination:
    def __init__(self, page, per_page, total_count):
        self.page = page; self.per_page = per_page; self.total_count = total_count
    @property
    def total_pages(self): return math.ceil(self.total_count / self.per_page)
    @property
    def has_prev(self): return self.page > 1
    @property
    def has_next(self): return self.page < self.total_pages
    @property
    def prev_num(self): return self.page - 1
    @property
    def next_num(self): return self.page + 1

@app.context_processor
def inject_globals():
    return dict(
        website_name=WEBSITE_NAME, 
        ad_settings=settings.find_one({"_id": "ad_config"}) or {},
        predefined_categories=[cat['name'] for cat in categories_collection.find().sort("name", 1)], 
        quote=quote, 
        datetime=datetime, 
        developer_telegram_id=DEVELOPER_TELEGRAM_ID,
        PLACEHOLDER_POSTER=PLACEHOLDER_POSTER
    )


# =====================================================================
# === [HTML TEMPLATES - NOVA-FLIX STYLE] ==============================
# =====================================================================

# --- 1. INDEX HTML ---
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ website_name }} - Stream Now</title>
<link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
<meta name="description" content="Watch and stream the latest movies and series on {{ website_name }}.">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Bebas+Neue&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
{{ ad_settings.ad_header | safe }}
<style>
  :root {
    --primary-color: #f7a53c; /* Nova-Flix Yellow/Orange */ 
    --bg-color: #121212; 
    --card-bg: #212121;
    --text-light: #ffffff; 
    --text-dark: #b0b0b0; 
    --nav-height: 60px;
  }
  body { font-family: 'Roboto', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding-bottom: 70px; }
  a { text-decoration: none; color: inherit; }
  .container { max-width: 1300px; margin: 0 auto; padding: 0 15px; }

  .main-header { position: sticky; top: 0; width: 100%; height: var(--nav-height); display: flex; align-items: center; z-index: 1000; background-color: rgba(18, 18, 18, 0.9); backdrop-filter: blur(5px); }
  .logo { font-family: 'Bebas Neue', cursive; font-size: 2.5rem; color: var(--primary-color); letter-spacing: 2px; }
  
  .home-search-section { padding: 20px 0; }
  .home-search-form { display: flex; max-width: 700px; margin: 0 auto; border-radius: 8px; overflow: hidden; background-color: var(--card-bg); border: 2px solid var(--primary-color); }
  .home-search-input { flex-grow: 1; border: none; background-color: transparent; color: var(--text-light); padding: 12px 20px; font-size: 1rem; outline: none; }
  .home-search-button { background-color: var(--primary-color); border: none; color: black; padding: 0 25px; cursor: pointer; font-size: 1.2rem; transition: background-color 0.2s ease; }

  .hero-slider-section { margin-bottom: 40px; }
  .hero-slider { width: 100%; height: 200px; border-radius: 12px; overflow: hidden; position: relative; }
  .hero-slider .swiper-slide { position: relative; display: block; }
  .hero-slider .hero-bg-img { width: 100%; height: 100%; object-fit: cover; filter: brightness(0.6); }
  .hero-slide-content { position: absolute; bottom: 0; left: 0; width: 100%; padding: 20px; z-index: 3; color: white; background: linear-gradient(to top, rgba(0,0,0,0.8), transparent); }
  .hero-title { font-size: 1.4rem; font-weight: 700; margin: 0; }
  .hero-meta { font-size: 0.8rem; color: var(--primary-color); }

  .category-section { margin: 30px 0; }
  .category-title { font-family: 'Bebas Neue', sans-serif; font-size: 1.8rem; margin-bottom: 15px; color: var(--text-light); border-left: 4px solid var(--primary-color); padding-left: 10px; }
  .movie-grid, .full-page-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }

  .movie-card { display: block; border-radius: 8px; overflow: hidden; background-color: var(--card-bg); transition: transform 0.2s; }
  .movie-card:hover { transform: translateY(-5px); box-shadow: 0 10px 20px rgba(0,0,0,0.3); }
  .poster-wrapper { position: relative; }
  .movie-poster { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; display: block; }
  .card-info { padding: 10px; }
  .card-title { font-size: 0.9rem; font-weight: 500; margin: 0 0 5px 0; min-height: 1.2em; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .card-meta { font-size: 0.75rem; color: var(--text-dark); }
  .type-tag { position: absolute; bottom: 8px; left: 8px; background-color: rgba(0,0,0,0.7); color: var(--primary-color); padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 0.65rem; }
  .time-tag { position: absolute; top: 8px; right: 8px; background-color: rgba(0,0,0,0.7); color: white; padding: 3px 8px; border-radius: 4px; font-weight: 500; font-size: 0.65rem; }

  .full-page-grid-container { padding-top: 80px; }
  .full-page-grid-title { font-size: 2rem; text-align: center; margin-bottom: 30px; color: var(--primary-color); }
  .pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin: 30px 0; }
  
  .bottom-nav { display: flex; position: fixed; bottom: 0; left: 0; right: 0; height: 65px; background-color: #000; box-shadow: 0 -2px 10px rgba(0,0,0,0.5); z-index: 1000; justify-content: space-around; align-items: center; padding-top: 5px; }
  .bottom-nav .nav-item { display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-dark); background: none; border: none; font-size: 11px; flex-grow: 1; font-weight: 500; }
  .bottom-nav .nav-item i { font-size: 24px; margin-bottom: 3px; }
  .bottom-nav .nav-item.active, .bottom-nav .nav-item:hover { color: var(--primary-color); }
  
  @media (min-width: 768px) { 
    .movie-grid, .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
    .hero-slider { height: 350px; }
    body { padding-bottom: 0; } .bottom-nav { display: none; }
  }
</style>
</head>
<body>
<header class="main-header"><div class="container"><a href="{{ url_for('home') }}" class="logo">{{ website_name }}</a></div></header>
<main>
  {% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        <img class="movie-poster" loading="lazy" src="{{ m.poster or PLACEHOLDER_POSTER }}" alt="{{ m.title }}">
        <span class="type-tag">{{ m.type | upper }}</span>
        <span class="time-tag">{{ m._id | time_ago }}</span>
      </div>
      <div class="card-info">
        <h4 class="card-title">{{ m.title }}</h4>
        <p class="card-meta">{{ m.language or 'Unknown' }}</p>
      </div>
    </a>
  {% endmacro %}

  {% if is_full_page_list %}
    <div class="full-page-grid-container container">
        <h2 class="full-page-grid-title">{{ query }}</h2>
        <div class="full-page-grid">{% for m in movies %}{{ render_movie_card(m) }}{% endfor %}</div>
        {% if pagination and pagination.total_pages > 1 %}
        <div class="pagination">
            {% if pagination.has_prev %}<a href="{{ url_for(request.endpoint, page=pagination.prev_num) }}">Prev</a>{% endif %}
            <span class="current">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
            {% if pagination.has_next %}<a href="{{ url_for(request.endpoint, page=pagination.next_num) }}">Next</a>{% endif %}
        </div>
        {% endif %}
    </div>
  {% else %}
    <div style="height: var(--nav-height);"></div>
    <section class="home-search-section container">
        <form action="{{ url_for('home') }}" method="get" class="home-search-form">
            <input type="text" name="q" class="home-search-input" placeholder="Search for content..." required>
            <button type="submit" class="home-search-button" aria-label="Search"><i class="fas fa-search"></i></button>
        </form>
    </section>

    {% if slider_content %}
    <section class="hero-slider-section container">
        <div class="swiper hero-slider">
            <div class="swiper-wrapper">
                {% for item in slider_content %}
                <div class="swiper-slide">
                    <a href="{{ url_for('movie_detail', movie_id=item._id) }}">
                        <img src="{{ item.backdrop or item.poster or PLACEHOLDER_POSTER }}" class="hero-bg-img" alt="{{ item.title }}">
                        <div class="hero-slide-content">
                            <h2 class="hero-title">{{ item.title }}</h2>
                            <p class="hero-meta">{{ item.language or 'Stream' }} | {{ item.type | upper }}</p>
                        </div>
                    </a>
                </div>
                {% endfor %}
            </div>
            <div class="swiper-pagination"></div>
        </div>
    </section>
    {% endif %}

    <div class="container">
      {% macro render_grid_section(title, movies_list) %}
          {% if movies_list %}
          <section class="category-section">
              <h2 class="category-title">{{ title }}</h2>
              <div class="movie-grid">
                  {% for m in movies_list %}
                      {{ render_movie_card(m) }}
                  {% endfor %}
              </div>
          </section>
          {% endif %}
      {% endmacro %}
      
      {{ render_grid_section('Latest Streams', latest_content) }}
      
      {% for cat_name, movies_list in categorized_content.items() %}
          {% if cat_name != 'Trending' %}
            {{ render_grid_section(cat_name, movies_list) }}
          {% endif %}
      {% endfor %}
    </div>
  {% endif %}
</main>
<footer style="text-align:center; padding: 20px; color: var(--text-dark); font-size: 0.8rem;">&copy; 2024 {{ website_name }}.</footer>
<nav class="bottom-nav">
  <a href="{{ url_for('home') }}" class="nav-item active"><i class="fas fa-home"></i><span>Home</span></a>
  <a href="{{ url_for('all_movies') }}" class="nav-item"><i class="fas fa-film"></i><span>Movies</span></a>
  <a href="{{ url_for('all_series') }}" class="nav-item"><i class="fas fa-tv"></i><span>Series</span></a>
  <a href="{{ url_for('request_content') }}" class="nav-item"><i class="fas fa-plus-circle"></i><span>Request</span></a>
</nav>
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<script>
    new Swiper('.hero-slider', {
        loop: true, autoplay: { delay: 5000, disableOnInteraction: false },
        pagination: { el: '.swiper-pagination', clickable: true },
        effect: 'fade', fadeEffect: { crossFade: true },
    });
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""

# --- 2. DETAIL HTML ---
detail_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ movie.title if movie else "Content Not Found" }} - {{ website_name }}</title>
<link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
<meta name="description" content="{{ movie.overview|striptags|truncate(160) }}">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Bebas+Neue&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
{{ ad_settings.ad_header | safe }}
<style>
  :root {
      --primary-color: #f7a53c;
      --bg-color: #0a0a0a;
      --card-bg: #1c1c1c;
      --text-light: #ffffff;
      --text-dark: #a0a0a0;
  }
  body { font-family: 'Roboto', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; }
  .container { max-width: 1200px; margin: 0 auto; padding: 20px 15px; }

  .hero-section {
      position: relative;
      background-size: cover;
      background-position: center;
      padding-top: 56.25%; /* 16:9 aspect ratio */
      border-radius: 10px;
      overflow: hidden;
      margin-bottom: 30px;
  }
  .hero-overlay {
      position: absolute; top: 0; left: 0; width: 100%; height: 100%;
      background: linear-gradient(to top, rgba(10, 10, 10, 1) 0%, rgba(10, 10, 10, 0.5) 50%, rgba(10, 10, 10, 1) 100%);
      z-index: 1;
  }
  .hero-content {
      position: absolute; bottom: 0; left: 0; width: 100%; padding: 30px; z-index: 2;
  }
  .movie-poster-mini {
      width: 80px; height: 120px; object-fit: cover; border-radius: 6px; float: left; margin-right: 15px;
  }
  .main-title {
      font-family: 'Bebas Neue', sans-serif; font-size: 2.5rem; margin: 0 0 5px 0; line-height: 1.1; color: var(--primary-color);
  }
  .meta-tags { font-size: 0.9rem; color: var(--text-dark); margin-bottom: 15px; display: flex; flex-wrap: wrap; gap: 10px; }
  .meta-tag { background: #333; padding: 4px 10px; border-radius: 4px; }
  
  .stream-action-box {
      background-color: var(--card-bg); padding: 20px; border-radius: 10px; margin-bottom: 30px;
  }
  .stream-action-box h2 { font-size: 1.5rem; margin-top: 0; color: var(--primary-color); }
  .stream-btn {
      display: block; width: 100%; text-align: center; padding: 15px; background-color: var(--primary-color);
      color: black; font-weight: 700; border-radius: 8px; font-size: 1.2rem; transition: background-color 0.2s;
  }
  .stream-btn:hover { background-color: #ffc161; }
  
  .links-container { margin-top: 20px; }
  .episode-list { display: flex; flex-direction: column; gap: 10px; }
  .episode-item { display: flex; align-items: center; justify-content: space-between; padding: 12px 15px; background: #282828; border-radius: 6px; transition: background 0.2s; }
  .episode-item:hover { background: #3a3a3a; }
  .episode-title { font-size: 1rem; font-weight: 500; }
  .episode-info { color: var(--primary-color); font-weight: 700; }

  @media (min-width: 768px) {
      .hero-section { padding-top: 300px; }
      .hero-content { display: flex; align-items: flex-end; }
      .movie-poster-mini { width: 150px; height: 225px; float: none; margin-right: 25px; }
  }
</style>
</head>
<body>
<header style="background:var(--bg-color); padding: 10px 0; border-bottom: 1px solid #1c1c1c;"><div class="container"><a href="{{ url_for('home') }}" class="main-title">{{ website_name }}</a></div></header>
<main>
{% if movie %}
<div class="hero-section" style="background-image: url('{{ movie.backdrop or movie.poster or PLACEHOLDER_POSTER }}');">
    <div class="hero-overlay"></div>
    <div class="hero-content container">
        <img src="{{ movie.poster or PLACEHOLDER_POSTER }}" alt="{{ movie.title }}" class="movie-poster-mini">
        <div>
            <h1 class="main-title">{{ movie.title }}</h1>
            <div class="meta-tags">
                <span class="meta-tag"><i class="fas fa-calendar-alt"></i> {{ movie.release_date.split('-')[0] if movie.release_date else 'N/A' }}</span>
                <span class="meta-tag"><i class="fas fa-globe"></i> {{ movie.language or 'Unknown' }}</span>
                <span class="meta-tag"><i class="fas fa-star"></i> {{ '%.1f'|format(movie.vote_average) if movie.vote_average else 'N/A' }}</span>
            </div>
            <p style="color: var(--text-dark); margin-bottom: 15px;">{{ movie.overview or 'No description available.'|truncate(200) }}</p>
        </div>
    </div>
</div>

<div class="container">
    <div class="stream-action-box">
        <h2>Stream Options</h2>

        {% if movie.type == 'movie' and movie.links %}
            {% for link_item in movie.links %}
                {% if link_item.watch_url %}
                    {% set watch_title = quote(movie.title + ' ' + link_item.quality + ' Stream') %}
                    <a href="{{ url_for('watch_online', target=quote(link_item.watch_url), title=watch_title) }}" class="stream-btn">
                        <i class="fas fa-play"></i> Start Stream ({{ link_item.quality or 'HD' }})
                    </a>
                    {% break %} 
                {% endif %}
            {% endfor %}
        {% elif movie.type == 'movie' and movie.manual_links %}
            {# Manual link fallback for movies #}
             {% for link in movie.manual_links %}
                {% set manual_title = quote(movie.title + ' ' + link.name) %}
                <a href="{{ url_for('watch_online', target=quote(link.url), title=manual_title) }}" class="stream-btn" style="background: #3a3a3a; color: var(--text-light); margin-bottom: 10px;">
                    <span>▶️ {{ link.name }}</span><i class="fas fa-play"></i>
                </a>
            {% endfor %}
        {% endif %}
        
        {% if movie.type == 'series' %}
            <p style="color: var(--text-dark); margin-bottom: 15px;">Select an episode to begin streaming.</p>
            {% set all_seasons = movie.episodes | map(attribute='season') | unique | sort %}
            
            {% for season_num in all_seasons %}
                <h3 style="color: var(--text-light); margin-top: 25px; margin-bottom: 10px;">Season {{ season_num }}</h3>
                <div class="episode-list">
                    {% set episodes_for_season = movie.episodes | selectattr('season', 'equalto', season_num) | list %}
                    {% for ep in episodes_for_season | sort(attribute='episode_number') %}
                        {% if ep.watch_link %}
                            {% set ep_title = quote(movie.title + ' S' + '%02d'|format(season_num|int) + ' E' + '%02d'|format(ep.episode_number|int)) %}
                            <a href="{{ url_for('watch_online', target=quote(ep.watch_link), title=ep_title) }}" class="episode-item">
                                <span class="episode-title">{{ ep.episode_number }}. {{ ep.title or 'Episode ' + ep.episode_number|string }}</span>
                                <span class="episode-info"><i class="fas fa-play-circle"></i> Watch</span>
                            </a>
                        {% endif %}
                    {% endfor %}
                </div>
            {% endfor %}
        {% endif %}

        {% if not movie.links and not movie.episodes and not movie.manual_links %}
            <p style="text-align:center; color: var(--text-dark);">Stream links loading soon.</p>
        {% endif %}
    </div>
    
</div>
{% else %}
<div style="text-align:center; padding: 100px;"><h2>Content not found.</h2></div>
{% endif %}
</main>
<footer style="text-align:center; padding: 20px; color: var(--text-dark); font-size: 0.8rem;">&copy; 2024 {{ website_name }}.</footer>
</body></html>
"""

# --- 3. WATCH HTML ---
watch_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{{ title }} - Watch Online</title>
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root { --primary-color: #f7a53c; --bg-color: #0a0a0a; --card-bg: #1c1c1c; --text-light: #ffffff; }
        body { font-family: 'Roboto', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding: 0; }
        .watch-container { max-width: 1200px; margin: 0 auto; padding: 20px 15px; }
        .player-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
        .player-header h1 { font-size: 1.5rem; margin: 0; color: var(--primary-color); }
        .back-link { display: inline-block; padding: 8px 15px; background-color: var(--card-bg); color: #999; border-radius: 50px; text-decoration: none; font-size: 0.9rem; transition: all 0.2s ease; }
        .back-link:hover { color: var(--text-light); background-color: #333; }
        .iframe-wrapper {
            position: relative;
            width: 100%;
            padding-top: 56.25%; /* 16:9 Aspect Ratio */
            margin-bottom: 30px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 0 20px rgba(0, 0, 0, 0.5);
            border: 2px solid #333;
        }
        .iframe-wrapper iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: none;
        }
        .ad-container { margin: 20px auto; width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
    </style>
</head>
<body>
    {{ ad_settings.ad_body_top | safe }}
    <div class="watch-container">
        <div class="player-header">
            <h1><i class="fas fa-play-circle"></i> Watching: {{ title }}</h1>
            <a href="#" onclick="window.history.back(); return false;" class="back-link">
                <i class="fas fa-arrow-left"></i> Go Back
            </a>
        </div>
        {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}
        
        <div class="iframe-wrapper">
            <iframe 
                src="{{ url | safe }}" 
                allowfullscreen 
                frameborder="0" 
                scrolling="no"
                referrerpolicy="origin"
                sandbox="allow-scripts allow-same-origin allow-popups allow-pointer-lock allow-forms"
            ></iframe>
        </div>
        
        <div style="text-align: center; color: #999; margin-top: 20px;">
            <p>If the player does not load, please open the link in a new tab: <a href="{{ url | safe }}" target="_blank" style="color: var(--primary-color);">Open Link</a></p>
        </div>
    </div>
    {{ ad_settings.ad_footer | safe }}
</body>
</html>
"""
# --- 4. REQUEST HTML --- (Defined earlier)

# --- 5. ADMIN HTML --- (Placeholder for restoration)
admin_html = """
<!DOCTYPE html><html><head><title>Admin Panel</title><style>:root { --primary-color: #f7a53c; --bg-color: #121212; --card-bg: #212121; --text-light: #ffffff; }</style></head><body style="background: var(--bg-color); color: var(--text-light); padding: 20px;">
<h1 style="color: var(--primary-color);">Admin Panel - Stream Ready</h1>
<p>The system is ready for streaming and Telegram Webhook automation.</p>
<h2>Configuration Steps:</h2>
<ol>
    <li><p>Ensure <code>WEBSITE_URL</code> and <code>TELEGRAM_BOT_TOKEN</code> are set in Vercel.</p></li>
    <li><p><strong>Run Webhook Setup (CRITICAL):</strong> <a href="{{ url_for('set_webhook') }}" style="background: #333; color: white; padding: 10px; border-radius: 5px; text-decoration: none;">Click to Set Telegram Webhook</a> (Requires Admin Login)</p></li>
</ol>
<h2>Key Endpoints:</h2>
<ul>
    <li><code style="color: var(--primary-color);">/telegram_update</code>: Receives file uploads from Telegram.</li>
    <li><code style="color: var(--primary-color);">/api/autopost</code>: Receives structured data from custom bots.</li>
</ul>
<p>Restore full Admin functionality (content CRUD, ads, categories) using your original code's admin_html.</p>
<a href="{{ url_for('home') }}" style="color: var(--primary-color);">Go to Site</a>
</body></html>
"""


# =====================================================================
# === [FLASK ROUTES] ==================================================
# =====================================================================

# --- General Routes (home, movie_detail, all_movies, etc.) remain as defined earlier ---

# --- Stream Specific Routes ---

@app.route('/watch')
def watch_online():
    encoded_url = request.args.get('target')
    title = request.args.get('title', 'Content')
    if not encoded_url: return redirect(url_for('home'))
    url_to_embed = unquote(encoded_url)
    return render_template_string(watch_html, url=url_to_embed, title=unquote(title))


# --- Auto Post API Endpoint (for structured custom bot data) ---
@app.route('/api/autopost', methods=['POST'])
def auto_post_content():
    # This route is optional if you use the webhook method, but kept for structured data posting
    data = request.json
    if data is None or data.get('secret_key') != AUTO_POST_SECRET:
        return jsonify({"status": "error", "message": "Unauthorized access"}), 401
    
    # Simplified logic to insert content from external structured POST request
    tmdb_id = data.get('tmdb_id')
    content_title = data.get('title') or "Untitled Content"
    content_type = data.get('type', 'movie').lower()
    stream_link = data.get('stream_link')
    
    if not stream_link: return jsonify({"status": "error", "message": "Stream link missing"}), 400

    movie_data = {
        "title": content_title, "type": content_type, "language": data.get('language', 'Unknown'),
        "categories": data.get('categories', ['Trending']), "view_count": 0, "tmdb_id": tmdb_id,
        "poster": data.get('poster') or PLACEHOLDER_POSTER, "overview": data.get('overview', "Posted automatically."),
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
    }
    
    # Add Stream Link (Simplified to links array)
    if content_type == 'movie':
        movie_data["links"] = [{"quality": data.get('quality', '720p').upper(), "watch_url": stream_link}]
    elif content_type == 'series':
        movie_data['episodes'] = data.get('episodes', []) # Expects episodes array
        if not movie_data['episodes']: movie_data["links"] = [{"quality": data.get('quality', '720p').upper(), "watch_url": stream_link}]
    
    try:
        result = movies.insert_one(movie_data)
        if result.inserted_id: send_telegram_notification(movie_data, result.inserted_id)
        return jsonify({"status": "success", "message": "Content posted"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"DB insertion failed: {e}"}), 500


# --- TELEGRAM WEBHOOK HANDLERS (New Core for Auto-Posting) ---

@app.route('/set_webhook', methods=['GET'])
@requires_auth 
def set_webhook():
    """Sets the Telegram webhook to the /telegram_update route."""
    if not TELEGRAM_BOT_TOKEN or not WEBSITE_URL:
        return "Telegram Bot Token or WEBSITE_URL is not set.", 500
        
    webhook_url = f"{WEBSITE_URL}/telegram_update"
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    response = requests.get(api_url, params={'url': webhook_url})
    
    if response.ok and response.json().get('ok'):
        return f"SUCCESS: Webhook set to: {webhook_url}", 200
    else:
        return f"FAILURE: Failed to set webhook. Response: {response.text}", 500


@app.route('/telegram_update', methods=['POST'])
def telegram_update():
    """Receives and processes updates from Telegram (triggered by the bot)."""
    data = request.json
    
    message = data.get('message')
    if not message: return jsonify(success=True)
    
    video = message.get('video')
    chat_id = message.get('chat', {}).get('id')
    
    # Only process new video file uploads
    if not video: return jsonify(success=True)

    file_id = video.get('file_id')
    caption = message.get('caption', video.get('file_name', 'Untitled Content'))
    
    # --- 1. Generate Direct Stream Link ---
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: BOT TOKEN missing for stream link generation.")
        return jsonify(success=True)
        
    def get_file_path(token, file_id):
        try:
            url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
            res = requests.get(url, timeout=5).json()
            return res.get('result', {}).get('file_path')
        except: return None
        
    file_path = get_file_path(TELEGRAM_BOT_TOKEN, file_id)
    stream_link = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}" if file_path else None
    
    if not stream_link:
        print("WARNING: Stream link could not be generated.")
        return jsonify(success=True)

    # --- 2. Extract Metadata & Insert ---
    content_title = caption.split('\n')[0].strip()
    
    movie_data = {
        "title": content_title,
        "type": "movie", # Default to movie
        "language": "Bangla/Hindi", # Default language
        "categories": ["Trending"],
        "view_count": 0,
        "poster": PLACEHOLDER_POSTER,
        "overview": caption,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    # Attempt to search TMDB using title (optional, can be time-consuming)
    tmdb_result = get_tmdb_details(None, "movie") # Requires proper search logic if implemented
    if tmdb_result:
        movie_data.update({"overview": tmdb_result.get('overview'), "poster": tmdb_result.get('poster')})

    # Add Link
    movie_data["links"] = [{"quality": "HD", "watch_url": stream_link, "download_url": None}]

    try:
        result = movies.insert_one(movie_data)
        if result.inserted_id: send_telegram_notification(movie_data, result.inserted_id, notification_type='new')
        print(f"AUTO-POST SUCCESS: {movie_data['title']}")
        return jsonify(success=True)
    except Exception as e:
        print(f"DB Insert Error during Webhook: {e}")
        return jsonify(success=True) 


# --- Admin Routes (Simplified, requires restoration) ---
# NOTE: The full logic for other admin CRUD functions (delete_movie, edit_movie, etc.)
# must be present in your final app.py file if you want them to work.

@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    # Only render the simplified admin HTML for instruction purposes
    return render_template_string(admin_html, website_name=WEBSITE_NAME)

@app.route('/delete_movie/<movie_id>')
@requires_auth
def delete_movie(movie_id):
    try: movies.delete_one({"_id": ObjectId(movie_id)})
    except: pass
    return redirect(url_for('admin'))

# --- General Routes (Restored) ---

@app.route('/request', methods=['GET', 'POST'])
def request_content():
    if request.method == 'POST':
        content_name = request.form.get('content_name', '').strip()
        extra_info = request.form.get('extra_info', '').strip()
        if content_name:
            requests_collection.insert_one({"name": content_name, "info": extra_info, "status": "Pending", "created_at": datetime.utcnow()})
            flash('Your request has been submitted successfully!', 'success')
        return redirect(url_for('request_content'))
    return render_template_string(request_html)

def get_paginated_content(query_filter, page):
    skip = (page - 1) * ITEMS_PER_PAGE
    total_count = movies.count_documents(query_filter)
    content_list = list(movies.find(query_filter).sort('updated_at', -1).skip(skip).limit(ITEMS_PER_PAGE))
    pagination = Pagination(page, ITEMS_PER_PAGE, total_count)
    return content_list, pagination

@app.route('/movies')
def all_movies():
    page = request.args.get('page', 1, type=int)
    content, pagination = get_paginated_content({"type": "movie"}, page)
    return render_template_string(index_html, movies=content, query="All Movies", is_full_page_list=True, pagination=pagination)

@app.route('/series')
def all_series():
    page = request.args.get('page', 1, type=int)
    content, pagination = get_paginated_content({"type": "series"}, page)
    return render_template_string(index_html, movies=content, query="All Series", is_full_page_list=True, pagination=pagination)

@app.route('/category')
def movies_by_category():
    title = request.args.get('name')
    if not title: return redirect(url_for('home'))
    page = request.args.get('page', 1, type=int)
    content, pagination = get_paginated_content({"categories": title}, page)
    return render_template_string(index_html, movies=content, query=title, is_full_page_list=True, pagination=pagination)


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 3000))
    app.run(debug=True, host='0.0.0.0', port=port)
