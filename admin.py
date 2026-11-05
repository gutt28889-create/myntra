"""
SoulChat - Admin Panel (admin.py)
Run separately: python admin.py  →  opens on http://127.0.0.1:5001/admin

Requires: index.py already created users.json / folders.
"""

import os
import json
import time
import uuid
from datetime import datetime

from flask import (
    Flask, request, session, redirect, url_for,
    render_template_string, send_from_directory
)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

# ==================================================================
# CONFIG (must match index.py)
# ==================================================================
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
USERS_FILE     = os.path.join(BASE_DIR, 'users.json')
MESSAGES_FILE  = os.path.join(BASE_DIR, 'messages.json')
MUSIC_JSON     = os.path.join(BASE_DIR, 'music', 'music.json')
UPLOAD_PHOTOS  = os.path.join(BASE_DIR, 'uploads', 'photos')
UPLOAD_VIDEOS  = os.path.join(BASE_DIR, 'uploads', 'videos')
MUSIC_DIR      = os.path.join(BASE_DIR, 'music')

AUTO_LOGOUT_TIME = 5 * 60
MAX_PHOTO_SIZE   = 10 * 1024 * 1024
MAX_VIDEO_SIZE   = 50 * 1024 * 1024
MAX_MUSIC_SIZE   = 20 * 1024 * 1024

ALLOWED_MUSIC_EXT = {'mp3', 'wav', 'ogg', 'm4a'}
ADMIN_USERS = ['SOUMIK', 'SANAYA']
SECRET_KEY  = 'soulchat-change-this-secret-key-12345'


# ==================================================================
# HELPERS
# ==================================================================
def ensure_dirs():
    for d in [UPLOAD_PHOTOS, UPLOAD_VIDEOS, MUSIC_DIR]:
        os.makedirs(d, exist_ok=True)


def load_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, OSError): return default


def save_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def get_users():     return load_json(USERS_FILE, {})
def save_users(u):   save_json(USERS_FILE, u)
def get_music():     return load_json(MUSIC_JSON, [])
def save_music(m):   save_json(MUSIC_JSON, m)


def format_file_size(size):
    if size >= 1024 ** 3: return f"{size/(1024**3):.2f} GB"
    if size >= 1024 ** 2: return f"{size/(1024**2):.2f} MB"
    if size >= 1024:      return f"{size/1024:.2f} KB"
    return f"{size} B"


# ==================================================================
# FLASK APP
# ==================================================================
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_MUSIC_SIZE
ensure_dirs()


# ----- Static serving for admin preview -----
@app.route('/music/<path:f>')
def serve_music(f): return send_from_directory(MUSIC_DIR, f)


# ==================================================================
# ADMIN PANEL
# ==================================================================
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def admin(path):
    # ---- Session from same-domain? No: admin panel has own session.
    # ---- For simplicity we re-use login via a quick check:
    if 'user' not in session:
        return redirect('http://127.0.0.1:5000/')

    if session['user'] not in ADMIN_USERS:
        return "Access denied! Only SOUMIK and SANAYA can access admin panel.", 403

    success = None
    error   = None

    # ---------- UPLOAD MUSIC ----------
    if request.method == 'POST' and 'upload_music' in request.form:
        file = request.files.get('music_file')
        title = (request.form.get('music_title') or '').strip()
        artist = (request.form.get('music_artist') or '').strip()

        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in ALLOWED_MUSIC_EXT:
                file.seek(0, os.SEEK_END); size = file.tell(); file.seek(0)
                if size > MAX_MUSIC_SIZE:
                    error = f"❌ Music file too big (max {format_file_size(MAX_MUSIC_SIZE)})!"
                else:
                    safe = secure_filename(file.filename) or 'song'
                    fname = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe}"
                    file.save(os.path.join(MUSIC_DIR, fname))

                    song = {
                        'id': int(time.time() * 1000),
                        'title': title or os.path.splitext(file.filename)[0],
                        'artist': artist or 'Unknown Artist',
                        'file': f"music/{fname}",
                        'filename': file.filename,
                        'size': size,
                        'size_formatted': format_file_size(size),
                        'uploaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    data = get_music(); data.append(song); save_music(data)
                    success = "✅ Music uploaded successfully! 🎵"
            else:
                error = "❌ Only MP3, WAV, OGG, M4A files are allowed!"

    # ---------- DELETE MUSIC ----------
    if 'delete_music' in request.args:
        try: mid = int(request.args['delete_music'])
        except ValueError: mid = -1
        data = get_music(); new_data = []
        for s in data:
            if s['id'] == mid:
                p = os.path.join(BASE_DIR, s['file'])
                if os.path.exists(p):
                    try: os.remove(p)
                    except OSError: pass
            else:
                new_data.append(s)
        save_music(new_data)
        success = "🗑️ Music deleted successfully!"

    # ---------- CHANGE PASSWORD ----------
    if request.method == 'POST' and 'change_password' in request.form:
        target = request.form.get('user', '')
        p1 = request.form.get('new_password', '')
        p2 = request.form.get('confirm_password', '')
        if p1 != p2 or not p1 or len(p1) < 4:
            error = "❌ Passwords don't match or must be at least 4 characters!"
        else:
            users = get_users()
            if target in users:
                users[target]['password'] = generate_password_hash(p1)
                save_users(users)
                success = f"✅ Password for <strong>{target}</strong> changed successfully! 💕"
            else:
                error = "❌ User not found!"

    # ---------- STATS ----------
    users = get_users()
    music_list = get_music()
    total_songs = len(music_list)
    total_size  = sum(s.get('size', 0) for s in music_list)

    photos = [f for f in os.listdir(UPLOAD_PHOTOS) if os.path.isfile(os.path.join(UPLOAD_PHOTOS, f))]
    videos = [f for f in os.listdir(UPLOAD_VIDEOS) if os.path.isfile(os.path.join(UPLOAD_VIDEOS, f))]
    photo_size = sum(os.path.getsize(os.path.join(UPLOAD_PHOTOS, f)) for f in photos)
    video_size = sum(os.path.getsize(os.path.join(UPLOAD_VIDEOS, f)) for f in videos)

    return render_template_string(ADMIN_HTML,
        success=success, error=error,
        users=users,
        music_list=list(reversed(music_list)),
        total_songs=total_songs,
        total_size_formatted=format_file_size(total_size),
        total_photos=len(photos),
        total_videos=len(videos),
        photos_size_formatted=format_file_size(photo_size),
        videos_size_formatted=format_file_size(video_size),
        max_photo_size_formatted=format_file_size(MAX_PHOTO_SIZE),
        max_video_size_formatted=format_file_size(MAX_VIDEO_SIZE),
        auto_logout_min=AUTO_LOGOUT_TIME // 60)


# ==================================================================
# ADMIN HTML TEMPLATE
# ==================================================================
ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚙️ Admin Panel - SoulChat</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0a0a0a,#1a1a2e,#16213e);min-height:100vh;padding:20px}
.admin-container{max-width:1200px;margin:0 auto}
.admin-header{text-align:center;padding:30px 0;margin-bottom:30px}
.admin-header .icon{font-size:60px;display:block}
.admin-header h1{font-size:36px;background:linear-gradient(135deg,#ff69b4,#ff1493);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:5px 0}
.admin-header .sub{color:rgba(255,255,255,.4);font-size:14px;letter-spacing:2px}
.decorative-line{width:60px;height:3px;background:linear-gradient(90deg,#ff69b4,#ff1493);margin:10px auto;border-radius:5px}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;margin-bottom:30px}
.stat-card{background:rgba(255,255,255,.03);padding:20px;border-radius:15px;border:1px solid rgba(255,255,255,.05);text-align:center;transition:all .3s}
.stat-card:hover{border-color:rgba(255,20,147,.2);transform:translateY(-5px)}
.stat-card .number{font-size:28px;font-weight:700;color:#fff}
.stat-card .label{font-size:12px;color:rgba(255,255,255,.3);margin-top:5px}
.stat-card .size{font-size:13px;color:#ff69b4;margin-top:3px}
.admin-grid{display:grid;grid-template-columns:1fr 1fr;gap:25px}
@media (max-width:768px){.admin-grid{grid-template-columns:1fr}}
.card{background:rgba(255,255,255,.03);border-radius:20px;padding:25px;border:1px solid rgba(255,255,255,.05);margin-bottom:25px}
.card-title{color:#fff;font-size:18px;font-weight:600;margin-bottom:20px;display:flex;align-items:center;gap:10px}
.card-title .badge{background:linear-gradient(135deg,#ff69b4,#ff1493);color:#fff;font-size:12px;padding:2px 12px;border-radius:20px}
.upload-area{border:2px dashed rgba(255,255,255,.1);border-radius:15px;padding:30px;text-align:center;transition:all .3s;cursor:pointer}
.upload-area:hover{border-color:rgba(255,20,147,.3);background:rgba(255,20,147,.03)}
.upload-area .icon{font-size:40px;display:block;margin-bottom:10px}
.upload-area .text{color:rgba(255,255,255,.4);font-size:14px}
.upload-area .sub-text{color:rgba(255,255,255,.2);font-size:12px;margin-top:5px}
.upload-area input[type="file"]{display:none}
.form-group{margin-bottom:15px}
.form-group label{display:block;color:rgba(255,255,255,.4);font-size:13px;margin-bottom:5px}
.form-group input{width:100%;padding:12px 16px;border:1px solid rgba(255,255,255,.05);border-radius:12px;font-size:14px;background:rgba(255,255,255,.03);color:#fff;transition:all .3s}
.form-group input:focus{outline:none;border-color:rgba(255,20,147,.3);background:rgba(255,255,255,.05)}
.form-group input::placeholder{color:rgba(255,255,255,.2)}
.btn{padding:12px 30px;border:none;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;transition:all .3s;width:100%}
.btn-primary{background:linear-gradient(135deg,#ff69b4,#ff1493);color:#fff}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(255,20,147,.3)}
.btn-danger{background:linear-gradient(135deg,#ff6b6b,#ee5a24);color:#fff;font-size:12px;padding:6px 15px;width:auto}
.btn-danger:hover{transform:scale(1.05);box-shadow:0 5px 20px rgba(238,90,36,.3)}
.btn-small{padding:6px 15px;font-size:12px;width:auto}
.music-list{max-height:400px;overflow-y:auto}
.music-list::-webkit-scrollbar{width:4px}
.music-list::-webkit-scrollbar-thumb{background:rgba(255,182,193,.3);border-radius:10px}
.music-item{display:flex;align-items:center;justify-content:space-between;padding:12px 15px;background:rgba(255,255,255,.02);border-radius:12px;margin-bottom:8px;border:1px solid rgba(255,255,255,.03);transition:all .3s}
.music-item:hover{background:rgba(255,255,255,.05);border-color:rgba(255,20,147,.1)}
.music-item .info{flex:1;min-width:0}
.music-item .info .title{color:#fff;font-size:14px;font-weight:500}
.music-item .info .artist{color:rgba(255,255,255,.3);font-size:12px}
.music-item .info .size{color:rgba(255,255,255,.2);font-size:11px}
.music-item .actions{display:flex;gap:8px;flex-shrink:0}
.music-item .play-btn{background:rgba(255,20,147,.1);border:1px solid rgba(255,20,147,.2);color:#ff69b4;padding:5px 12px;border-radius:20px;cursor:pointer;font-size:12px;transition:all .3s}
.music-item .play-btn:hover{background:rgba(255,20,147,.2)}
.password-box{background:rgba(255,255,255,.02);padding:20px;border-radius:15px;border:1px solid rgba(255,255,255,.05);margin-bottom:15px}
.password-box h4{color:#fff;font-size:16px;margin-bottom:15px;display:flex;align-items:center;gap:10px}
.msg{padding:15px;border-radius:12px;margin-bottom:15px;text-align:center;font-weight:500}
.msg.success{background:rgba(76,175,80,.1);color:#4caf50;border:1px solid rgba(76,175,80,.2)}
.msg.error{background:rgba(255,20,147,.1);color:#ff1493;border:1px solid rgba(255,20,147,.2)}
.back-link{display:inline-block;margin-top:20px;color:rgba(255,255,255,.4);text-decoration:none;font-weight:600;transition:all .3s}
.back-link:hover{color:#ff69b4}
.empty-state{text-align:center;color:rgba(255,255,255,.2);padding:30px}
.empty-state .icon{font-size:40px;display:block;margin-bottom:10px}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);backdrop-filter:blur(20px);z-index:1000;justify-content:center;align-items:center}
.modal.show{display:flex}
.modal-content{background:rgba(255,255,255,.05);padding:30px;border-radius:25px;max-width:400px;width:90%;text-align:center;border:1px solid rgba(255,255,255,.1)}
.modal-content .title{color:#fff;font-size:20px;margin-bottom:5px}
.modal-content .artist{color:rgba(255,255,255,.4);font-size:14px;margin-bottom:20px}
.modal-content audio{width:100%;margin:15px 0}
.modal-content .close-btn{margin-top:15px;padding:10px 30px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:#fff;border-radius:12px;cursor:pointer;transition:all .3s}
.modal-content .close-btn:hover{background:rgba(255,20,147,.1);border-color:rgba(255,20,147,.3)}
.upload-limits{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:15px}
.limit-item{background:rgba(255,255,255,.02);padding:8px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.05);text-align:center}
.limit-item .label{color:rgba(255,255,255,.3);font-size:10px}
.limit-item .value{color:#ff69b4;font-size:13px;font-weight:600}
</style>
</head>
<body>
<div class="admin-container">
    <div class="admin-header">
        <span class="icon">⚙️</span>
        <h1>Admin Panel</h1>
        <div class="sub">💕 Complete Management Dashboard</div>
        <div class="decorative-line"></div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="number">🎵 {{ total_songs }}</div>
            <div class="label">Total Songs</div>
            <div class="size">{{ total_size_formatted }}</div>
        </div>
        <div class="stat-card">
            <div class="number">📷 {{ total_photos }}</div>
            <div class="label">Photos</div>
            <div class="size">{{ photos_size_formatted }}</div>
        </div>
        <div class="stat-card">
            <div class="number">🎬 {{ total_videos }}</div>
            <div class="label">Videos</div>
            <div class="size">{{ videos_size_formatted }}</div>
        </div>
        <div class="stat-card">
            <div class="number">👥 {{ users|length }}</div>
            <div class="label">Users</div>
            <div class="size">💕 SOUMIK & SANAYA</div>
        </div>
    </div>

    {% if success %}<div class="msg success">{{ success|safe }}</div>{% endif %}
    {% if error %}<div class="msg error">{{ error|safe }}</div>{% endif %}

    <div class="admin-grid">
        <div>
            <div class="card">
                <div class="card-title">🎵 Upload Music <span class="badge">MP3/WAV/OGG</span></div>
                <div class="upload-limits">
                    <div class="limit-item">
                        <div class="label">📷 Max Photo Size</div>
                        <div class="value">{{ max_photo_size_formatted }}</div>
                    </div>
                    <div class="limit-item">
                        <div class="label">🎬 Max Video Size</div>
                        <div class="value">{{ max_video_size_formatted }}</div>
                    </div>
                </div>
                <form method="POST" enctype="multipart/form-data" id="uploadForm">
                    <div class="upload-area" onclick="document.getElementById('musicFile').click()">
                        <span class="icon">🎵</span>
                        <div class="text">Click to upload music file</div>
                        <div class="sub-text">Supported: MP3, WAV, OGG, M4A</div>
                        <input type="file" id="musicFile" name="music_file" accept=".mp3,.wav,.ogg,.m4a" required onchange="document.getElementById('uploadForm').submit()">
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px">
                        <div class="form-group">
                            <label>🎵 Song Title</label>
                            <input type="text" name="music_title" placeholder="Enter song title..." id="musicTitle">
                        </div>
                        <div class="form-group">
                            <label>🎤 Artist Name</label>
                            <input type="text" name="music_artist" placeholder="Enter artist name..." id="musicArtist">
                        </div>
                    </div>
                    <button type="submit" name="upload_music" class="btn btn-primary">🎵 Upload Music</button>
                </form>
            </div>

            <div class="card">
                <div class="card-title">🎵 Music Library <span class="badge">{{ total_songs }} songs</span></div>
                {% if not music_list %}
                    <div class="empty-state">
                        <span class="icon">🎵</span>
                        <div>No music uploaded yet</div>
                        <div style="font-size:12px;margin-top:5px">Upload your first song above! 💕</div>
                    </div>
                {% else %}
                    <div class="music-list">
                        {% for song in music_list %}
                        <div class="music-item">
                            <div class="info">
                                <div class="title">🎵 {{ song.title }}</div>
                                <div class="artist">🎤 {{ song.artist }}</div>
                                <div class="size">📁 {{ song.size_formatted }} • {{ song.uploaded_at[:10] }}</div>
                            </div>
                            <div class="actions">
                                <button class="play-btn" onclick="playMusic('/{{ song.file }}','{{ song.title|replace("'", "\\'") }}','{{ song.artist|replace("'", "\\'") }}')">▶️ Play</button>
                                <a href="?delete_music={{ song.id }}" class="btn btn-danger btn-small" onclick="return confirm('Delete this song? 💔')">🗑️</a>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                {% endif %}
            </div>
        </div>

        <div>
            <div class="card">
                <div class="card-title">🔑 Password Management <span class="badge">Secure</span></div>
                {% for user in users %}
                <div class="password-box">
                    <h4><span style="font-size:24px">{{ '👨' if user == 'SOUMIK' else '👩' }}</span> {{ user }}</h4>
                    <form method="POST">
                        <input type="hidden" name="user" value="{{ user }}">
                        <div class="form-group">
                            <label>🔑 New Password (min 4 chars)</label>
                            <input type="password" name="new_password" placeholder="Enter new password..." required minlength="4">
                        </div>
                        <div class="form-group">
                            <label>🔐 Confirm Password</label>
                            <input type="password" name="confirm_password" placeholder="Confirm new password..." required minlength="4">
                        </div>
                        <button type="submit" name="change_password" class="btn btn-primary">💕 Change Password</button>
                    </form>
                </div>
                {% endfor %}
                <div style="text-align:center;color:rgba(255,255,255,.2);font-size:12px;margin-top:10px">
                    🔒 Passwords are securely hashed
                </div>
            </div>

            <div class="card">
                <div class="card-title">ℹ️ System Info <span class="badge">v2.0</span></div>
                <div style="color:rgba(255,255,255,.3);font-size:13px;line-height:1.8">
                    <div>📁 Total Music: {{ total_songs }} songs</div>
                    <div>📷 Total Photos: {{ total_photos }}</div>
                    <div>🎬 Total Videos: {{ total_videos }}</div>
                    <div>👥 Users: SOUMIK & SANAYA</div>
                    <div>⏰ Auto-Logout: {{ auto_logout_min }} Minutes</div>
                    <div>💾 Storage: JSON + Files</div>
                </div>
            </div>
        </div>
    </div>

    <div style="text-align:center">
        <a href="http://127.0.0.1:5000/" class="back-link">💌 Back to Chat</a>
        <div style="color:rgba(255,255,255,.15);font-size:11px;margin-top:10px">
            Only SOUMIK and SANAYA can access this panel 💕
        </div>
    </div>
</div>

<div class="modal" id="musicModal">
    <div class="modal-content">
        <div class="title" id="modalTitle">Song Title</div>
        <div class="artist" id="modalArtist">Artist Name</div>
        <audio controls autoplay id="modalAudio"><source src="" type="audio/mpeg"></audio>
        <button class="close-btn" onclick="closeMusic()">✕ Close</button>
    </div>
</div>

<script>
document.getElementById('musicFile').addEventListener('change',function(){
    const f=this.files[0];
    if(f&&!document.getElementById('musicTitle').value){
        document.getElementById('musicTitle').value=f.name.replace(/\.[^/.]+$/,'');
    }
});
function playMusic(file,title,artist){
    document.getElementById('modalTitle').textContent='🎵 '+title;
    document.getElementById('modalArtist').textContent='🎤 '+artist;
    document.getElementById('modalAudio').src=file;
    document.getElementById('musicModal').classList.add('show');
    document.getElementById('modalAudio').play();
}
function closeMusic(){
    const a=document.getElementById('modalAudio');
    a.pause();a.src='';
    document.getElementById('musicModal').classList.remove('show');
}
document.getElementById('musicModal').addEventListener('click',function(e){
    if(e.target===this)closeMusic();
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMusic();});
</script>
</body>
</html>
"""


# ==================================================================
if __name__ == '__main__':
    print("\n" + "="*55)
    print("  ⚙️  SoulChat Admin Panel")
    print("="*55)
    print("  URL: http://127.0.0.1:5001/")
    print("  NOTE: Run index.py first to create users.json!")
    print("  NOTE: Login via main app → then open admin panel")
    print("="*55 + "\n")
    app.run(host='0.0.0.0', port=5001, debug=True)
