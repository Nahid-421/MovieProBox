# ==============================================================================
# FINAL UNIFIED STREAMING APPLICATION (Universal Player Logic)
# File: app.py
# ==============================================================================

from flask import Flask, render_template_string, request, redirect, url_for, session, Response
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import timedelta
import os
import re
import requests # Used for Proxy Streaming

# ----------------- Configuration & Security Setup -----------------
app = Flask(__name__)

# Load configuration from Environment Variables (Crucial for Vercel)
app.secret_key = os.environ.get("SECRET_KEY", "a_very_secure_random_key_placeholder")
app.permanent_session_lifetime = timedelta(minutes=30)

# Admin Credentials
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

# MongoDB connection setup
mongo_uri = os.environ.get("MONGO_URI", 
    "mongodb+srv://mewayo8672:mewayo8672@cluster0.ozhvczp.mongodb.net/moviestreamingdb?retryWrites=true&w=majority&appName=Cluster0"
)
app.config["MONGO_URI"] = mongo_uri
try:
    mongo = PyMongo(app)
except Exception as e:
    print(f"MongoDB connection error: {e}")
    mongo = None

# ---------------- Helper Function (Universal Link Conversion) -----------------

def convert_link_for_stream(link):
    """
    Analyzes the link and determines if it should be handled internally (stream/proxy) 
    or externally (iframe).
    """
    link_lower = link.lower()
    
    # 1. Handle Google Drive Links (Convert to direct download/stream link)
    if "drive.google.com" in link:
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', link)
        if match:
            file_id = match.group(1)
            # Use uc?export=download for direct streaming via HTML5 <video> tag (no Drive UI)
            converted_link = f"https://drive.google.com/uc?export=download&id={file_id}"
            return converted_link, True # is_streamable = True

    # 2. Handle other known direct stream formats (MP4, MKV, etc.)
    if link_lower.endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
        # We need the original link for the stream proxy
        return link, True # is_streamable = True

    # 3. Default: Assume it's an external embed link (YouTube, Vimeo, StreamTape iframe src)
    return link, False # is_streamable = False

# ---------------- Stream Proxy Route (To prevent forced download) ----------------

@app.route('/stream/<movie_id>')
def stream(movie_id):
    """
    Proxies the video content from the external source, ensuring Content-Disposition: inline.
    This is essential for playing MP4/MKV links that usually force download.
    """
    if mongo is None: return "Database error.", 503
    
    movie = mongo.db.movies.find_one({"_id": ObjectId(movie_id)}, {"video_link": 1})
    if not movie: return "Video not found", 404

    original_link = movie['video_link'] 
    
    # Run conversion logic to get the final stream URL
    stream_url, is_streamable = convert_link_for_stream(original_link)
    
    if not is_streamable:
        return "Not a direct streamable link type.", 400

    try:
        # Use headers={'Range':...} for video seeking/scrubbing capability
        req = requests.get(stream_url, stream=True, headers={'Range': request.headers.get('Range', '')})
    except requests.exceptions.RequestException as e:
        print(f"External streaming error: {e}")
        return "Error fetching video content.", 500
    
    # Prepare response headers, excluding conflicting ones
    excluded_headers = ('content-encoding', 'transfer-encoding', 'content-disposition', 'connection')
    response_headers = [
        (name, value) for name, value in req.headers.items() 
        if name.lower() not in excluded_headers
    ]

    # Force the browser to play the video (inline) instead of downloading
    response_headers.append(('Content-Disposition', 'inline; filename="video.mp4"'))
    response_headers.append(('Content-Type', req.headers.get('Content-Type', 'video/mp4')))

    # Return the response as a stream
    return Response(
        req.iter_content(chunk_size=1024*10), 
        status=req.status_code, 
        headers=response_headers
    )

# ---------------- HTML Templates ----------------
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MovieZone+</title>
<style>
body{margin:0;font-family:Arial,sans-serif;background:#0b0b0b;color:white;}
header{background:#111;text-align:center;padding:15px;font-size:22px;color:#ff4444;}
.container{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;padding:20px;}
.movie{background:#1a1a1a;border-radius:10px;overflow:hidden;text-align:center;}
.movie img{width:100%;height:220px;object-fit:cover;}
.movie h3{padding:10px;color:#ff5555;}
.watch-btn{display:block;background:#ff4444;padding:10px;color:white;text-decoration:none;font-weight:bold;border-radius:0 0 10px 10px;}
.watch-btn:hover{background:#ff2222;}
footer{text-align:center;padding:15px;background:#111;color:gray;font-size:14px;}
</style>
</head>
<body>
<header>🎬 MovieZone+ | Watch Movies & Series</header>
<div class="container">
{% for movie in movies %}
<div class="movie">
<img src="{{ movie.poster or 'https://via.placeholder.com/200x300' }}" alt="{{ movie.title }}">
<h3>{{ movie.title }}</h3>
<a href="{{ url_for('player', movie_id=movie._id) }}" class="watch-btn">▶ Watch Now</a>
</div>
{% endfor %}
</div>
<footer>© 2025 MovieZone+. All Rights Reserved.</footer>
</body>
</html>
"""

player_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ movie.title }}</title>
<style>
body{margin:0;background:#000;color:white;font-family:Arial,sans-serif;text-align:center;}
/* Ensure video player or iframe covers the space */
.player iframe, .player video{width:100%;height:70vh;min-height:350px;border:none;background: black;}
.btn{display:inline-block;margin:10px;padding:10px 20px;background:#ff4444;color:white;text-decoration:none;border-radius:8px;}
.ad-box{margin-top:10px;padding:10px;background:#111;color:#bbb;font-size:14px;}
</style>
</head>
<body>
<h2>🎬 {{ movie.title }}</h2>
<p>{{ movie.description }}</p>
<div class="player">
{% if movie.is_streamable %}
    <!-- Use custom HTML5 video player for all proxied content (Drive, MP4, MKV) -->
    <video controls autoplay>
      <source src="{{ movie.video_link }}" type="video/mp4">
      Your browser does not support the video tag.
    </video>
{% else %}
    <!-- Use iframe for external embed codes (YouTube, Vimeo, etc.) -->
    <iframe src="{{ movie.video_link }}" allowfullscreen></iframe>
{% endif %}
</div>
<a href="{{ url_for('home') }}" class="btn">⬅ Back to Home</a>
<div class="ad-box">
🔸 Ad Space (PropellerAds/Adsterra)
</div>
</body>
</html>
"""

login_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Login</title>
<style>
body{font-family:Arial,sans-serif;background:#0b0b0b;color:white;text-align:center;padding-top:50px;}
input{padding:10px;margin:5px;width:200px;}
button{padding:10px 20px;background:#ff4444;color:white;border:none;border-radius:5px;}
</style>
</head>
<body>
<h2>Admin Login</h2>
<form method="POST">
<input type="text" name="username" placeholder="Username" required><br>
<input type="password" name="password" placeholder="Password" required><br>
<button type="submit">Login</button>
</form>
</body>
</html>
"""

admin_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Panel</title>
<style>
body{font-family:Arial,sans-serif;background:#0b0b0b;color:white;padding:20px;}
input, textarea{width:100%;padding:10px;margin:5px 0;}
button{padding:10px 20px;background:#ff4444;color:white;border:none;border-radius:5px;margin-top:5px;}
ul{list-style:none;padding:0;}
li{padding:5px 0;}
a{color:#ff5555;text-decoration:none;margin-left:10px;}
</style>
</head>
<body>
<h2>Admin Dashboard</h2>
<h3>Add Movie</h3>
<form action="{{ url_for('add_movie') }}" method="POST">
<input type="text" name="title" placeholder="Movie Title" required><br>
<textarea name="description" placeholder="Description"></textarea><br>
<input type="text" name="poster" placeholder="Poster URL"><br>
<input type="text" name="video_link" placeholder="Video Link" required><br>
<input type="text" name="language" placeholder="Language"><br>
<button type="submit">Add Movie</button>
</form>

<h3>All Movies</h3>
<ul>
{% for movie in movies %}
<li>{{ movie.title }} - <a href="{{ url_for('delete_movie', movie_id=movie._id) }}">Delete</a></li>
{% endfor %}
</ul>
<a href="{{ url_for('logout') }}">Logout</a>
</body>
</html>
"""

# ---------------- Routes ----------------
@app.route('/')
def home():
    if mongo is None: return "Database not available.", 503
    movies = mongo.db.movies.find().sort("title",1)
    return render_template_string(index_html, movies=movies)

@app.route('/player/<movie_id>')
def player(movie_id):
    if mongo is None: return "Database not available.", 503
    if not ObjectId.is_valid(movie_id): return "Invalid Movie ID", 400
    
    movie = mongo.db.movies.find_one({"_id": ObjectId(movie_id)})
    if not movie: return "Movie not found", 404

    # Determine if the link requires streaming/proxying
    _, is_streamable = convert_link_for_stream(movie['video_link'])
    
    movie['is_streamable'] = is_streamable
    
    if is_streamable:
        # Point the video source to our internal proxy route
        movie['video_link'] = url_for('stream', movie_id=movie_id)
    else:
        # Use the original link for external iframe embeds
        movie['video_link'], _ = convert_link_for_stream(movie['video_link'])

    return render_template_string(player_html, movie=movie)

@app.route('/login', methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form.get("username")==ADMIN_USER and request.form.get("password")==ADMIN_PASS:
            session.permanent=True
            session['admin']=True
            return redirect(url_for("admin_panel"))
        else:
            return render_template_string(login_html) + "<p style='color:red;text-align:center;'>Login Failed</p>"
    return render_template_string(login_html)

@app.route('/admin')
def admin_panel():
    if 'admin' not in session: return redirect(url_for("login"))
    if mongo is None: return "Database not available for Admin.", 503
    movies = mongo.db.movies.find().sort("title",1)
    return render_template_string(admin_html, movies=movies)

@app.route('/add_movie', methods=["POST"])
def add_movie():
    if 'admin' not in session: return redirect(url_for("login"))
    if mongo is None: return "Database not available.", 503
        
    title = request.form.get("title")
    video_link = request.form.get("video_link")
    
    if not title or not video_link: return "Title and Video Link required", 400
        
    mongo.db.movies.insert_one({
        "title": title,
        "description": request.form.get("description"),
        "poster": request.form.get("poster"),
        "video_link": video_link,
        "language": request.form.get("language")
    })
    return redirect(url_for("admin_panel"))

@app.route('/delete_movie/<movie_id>')
def delete_movie(movie_id):
    if 'admin' not in session: return redirect(url_for("login"))
    if mongo is None: return "Database not available.", 503
    if not ObjectId.is_valid(movie_id): return "Invalid Movie ID", 400
        
    mongo.db.movies.delete_one({"_id": ObjectId(movie_id)})
    return redirect(url_for("admin_panel"))

@app.route('/logout')
def logout():
    session.pop('admin',None)
    return redirect(url_for("login"))

# Vercel Execution Ready
