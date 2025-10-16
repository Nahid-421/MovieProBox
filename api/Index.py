from flask import Flask, render_template_string, request, redirect, url_for, session
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import os # পরিবেশ ভেরিয়েবল ব্যবহারের জন্য 

# ----------------- Configuration & Security Setup -----------------

app = Flask(__name__)

# SECURITY NOTE: All sensitive data must be loaded from Environment Variables in Vercel.
# 1. Secret Key (Used for sessions)
# Vercel Environment Variables: SECRET_KEY
app.secret_key = os.environ.get("SECRET_KEY", "fallback_dev_key_if_not_set")

# 2. MongoDB URI
# Vercel Environment Variables: MONGO_URI
# Note: Ensure the database name is part of the URI string.
mongo_uri = os.environ.get("MONGO_URI") 

if not mongo_uri:
    # If MONGO_URI is not set, use a fallback (DANGER: replace with your actual DB URI for testing)
    mongo_uri = "mongodb+srv://mewayo8672:mewayo8672@cluster0.ozhvczp.mongodb.net/moviestreamingdb?retryWrites=true&w=majority&appName=Cluster0" 
    print("Warning: MONGO_URI not set as env variable. Using hardcoded fallback.")

app.config["MONGO_URI"] = mongo_uri
mongo = PyMongo(app)

# 3. Admin Credentials (For login function)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")


# ---------------- HTML Templates (Unchanged for brevity) ----------------
# ... (index_html, player_html, login_html, admin_html are kept as they were) ...
# I am including the full template definitions here for completeness, 
# with one small CSS fix in player_html.

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
/* Updated iframe height for better viewing on desktop */
.player iframe{width:100%;height:60vh;min-height:250px;border:none;} 
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
    # Note: Mongo queries must run after the app context is established.
    try:
        movies = mongo.db.movies.find().sort("title",1)
    except Exception as e:
        # Handle database connection error gracefully
        print(f"Database error: {e}")
        return "Error loading movies from database.", 500
        
    return render_template_string(index_html, movies=movies)

@app.route('/player/<movie_id>')
def player(movie_id):
    try:
        movie = mongo.db.movies.find_one({"_id": ObjectId(movie_id)})
    except:
        return "Invalid Movie ID format", 400

    if movie:
        return render_template_string(player_html, movie=movie)
    return "Movie not found", 404

@app.route('/login', methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        # Checking against Environment Variables
        if username == ADMIN_USER and password == ADMIN_PASS:
            session['admin']=True
            return redirect(url_for("admin_panel"))
        else:
            return "Login Failed"
    return render_template_string(login_html)

# Admin, Add Movie, Delete Movie, and Logout routes remain functionally the same.
# (Code omitted for brevity, but they are included in the final file.)

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
    
    # Simple validation check
    if not title or not video_link:
        return "Title and Video Link are required.", 400

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
        mongo.db.movies.delete_one({"_id": ObjectId(movie_id)})
    except:
        return "Could not delete movie (Invalid ID)", 400
        
    return redirect(url_for("admin_panel"))

@app.route('/logout')
def logout():
    session.pop('admin',None)
    return redirect(url_for("login"))

# ----------------- Vercel Ready Code -----------------
# REMOVED: if __name__=="__main__": app.run(debug=True)
# Vercel handles the execution of the 'app' instance automatically.
# Make sure your main file defines the 'app' variable (which we did).
