# api/index.py

from flask import Flask, render_template_string, request, redirect, url_for, session
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import os # Environment variables লোড করার জন্য

# ----------------- Configuration & Security Setup -----------------

app = Flask(__name__)

# IMPORTANT: Load sensitive configuration from Vercel Environment Variables
app.secret_key = os.environ.get("SECRET_KEY", "THIS_IS_A_FALLBACK_DEV_KEY")

# MongoDB Setup
mongo_uri = os.environ.get("MONGO_URI") 
if not mongo_uri:
    # If not set in environment (DEV ONLY), use hardcoded URI (DANGER IN PROD)
    mongo_uri = "mongodb+srv://mewayo8672:mewayo8672@cluster0.ozhvczp.mongodb.net/moviestreamingdb?retryWrites=true&w=majority&appName=Cluster0"
    
app.config["MONGO_URI"] = mongo_uri
mongo = PyMongo(app)

# Admin Credentials (Loaded from Vercel Env Vars)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")


# ---------------- HTML Templates ----------------
# NOTE: The templates are kept within the Python file for simplicity, 
# as using separate templates folders requires additional Vercel configuration.

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
/* Optimized for larger screens */
.player iframe{width:100%;height:70vh;min-height:350px;border:none;}
.btn{display:inline-block;margin:10px;padding:10px 20px;background:#ff4444;color:white;text-decoration:none;border-radius:8px;}
.ad-box{margin-top:10px;padding:10px;background:#111;color:#bbb;font-size:14px;}
</style>
</head>
<body>
<h2>🎬 {{ movie.title }}</h2>
<p>{{ movie.description }}</p>
<div class="player">
<iframe src="{{ movie.video_link }}" allowfullscreen></iframe>
</div>
<a href="{{ url_for('home') }}" class="btn">⬅ Back to Home</a>
<a href="#" class="btn">⏭ Next Episode</a>
<div class="ad-box">
🔸 Ad Space (Adsterra/PropellerAds)
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

# ----------------- Routes -----------------
@app.route('/')
def home():
    try:
        movies = mongo.db.movies.find().sort("title",1)
    except Exception as e:
        print(f"Database error: {e}")
        return "Database Connection Error.", 500
        
    return render_template_string(index_html, movies=movies)

@app.route('/player/<movie_id>')
def player(movie_id):
    try:
        # Validate ID format before querying
        if not ObjectId.is_valid(movie_id):
            return "Invalid Movie ID format", 400
            
        movie = mongo.db.movies.find_one({"_id": ObjectId(movie_id)})
    except Exception as e:
        print(f"Error fetching movie: {e}")
        return "An internal server error occurred.", 500

    if movie:
        return render_template_string(player_html, movie=movie)
    return "Movie not found", 404

@app.route('/login', methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        # Checking against Environment Variables (ADMIN_USER, ADMIN_PASS)
        if username == ADMIN_USER and password == ADMIN_PASS:
            session['admin']=True
            return redirect(url_for("admin_panel"))
        else:
            return "Login Failed"
    return render_template_string(login_html)

@app.route('/admin')
def admin_panel():
    if 'admin' not in session:
        return redirect(url_for("login"))
    movies = mongo.db.movies.find().sort("title",1)
    return render_template_string(admin_html, movies=movies)

@app.route('/add_movie', methods=["POST"])
def add_movie():
    if 'admin' not in session:
        return redirect(url_for("login"))
        
    title = request.form.get("title")
    description = request.form.get("description")
    poster = request.form.get("poster")
    video_link = request.form.get("video_link")
    language = request.form.get("language")
    
    # Basic input validation
    if not title or not video_link:
        return "Title and Video Link are required fields.", 400

    mongo.db.movies.insert_one({
        "title": title,
        "description": description,
        "poster": poster,
        "video_link": video_link,
        "language": language
    })
    return redirect(url_for("admin_panel"))

@app.route('/delete_movie/<movie_id>')
def delete_movie(movie_id):
    if 'admin' not in session:
        return redirect(url_for("login"))
        
    try:
        if not ObjectId.is_valid(movie_id):
            return "Invalid Movie ID format for deletion", 400
            
        mongo.db.movies.delete_one({"_id": ObjectId(movie_id)})
    except Exception as e:
        print(f"Deletion error: {e}")
        return "Could not delete movie due to server error.", 500
        
    return redirect(url_for("admin_panel"))

@app.route('/logout')
def logout():
    session.pop('admin',None)
    return redirect(url_for("login"))

# ----------------- Vercel EXECUTION READY -----------------
# Vercel needs the 'app' variable, but NO app.run() call.
# The code ends here.
