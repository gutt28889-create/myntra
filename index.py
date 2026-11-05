"""
SoulChat - Main Application (index.py)
Run this file: python index.py
First run automatically creates: users.json, messages.json, music/, uploads/
"""

import os
import json
import time
import uuid
import random
from datetime import datetime
from functools import wraps
from markupsafe import escape

from flask import (
    Flask, request, session, jsonify, redirect, url_for,
    render_template_string, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ==================================================================
# CONFIG (all in one place)
# ==================================================================
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
USERS_FILE     = os.path.join(BASE_DIR, 'users.json')
MESSAGES_FILE  = os.path.join(BASE_DIR, 'messages.json')
MUSIC_JSON     = os.path.join(BASE_DIR, 'music', 'music.json')
UPLOAD_PHOTOS  = os.path.join(BASE_DIR, 'uploads', 'photos')
UPLOAD_VIDEOS  = os.path.join(BASE_DIR, 'uploads', 'videos')
MUSIC_DIR      = os.path.join(BASE_DIR, 'music')

AUTO_LOGOUT_TIME  = 5 * 60                  # 5 minutes
MAX_PHOTO_SIZE    = 10 * 1024 * 1024        # 10 MB
MAX_VIDEO_SIZE    = 50 * 1024 * 1024        # 50 MB
MAX_MUSIC_SIZE    = 20 * 1024 * 1024        # 20 MB

ALLOWED_PHOTO_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'}
ALLOWED_VIDEO_TYPES = {'video/mp4', 'video/webm', 'video/ogg', 'video/quicktime', 'video/x-msvideo'}
ALLOWED_MUSIC_EXT   = {'mp3', 'wav', 'ogg', 'm4a'}

ADMIN_USERS = ['SOUMIK', 'SANAYA']
SECRET_KEY  = 'soulchat-change-this-secret-key-12345'


# ==================================================================
# HELPERS
# ==================================================================
def ensure_dirs():
    for d in [UPLOAD_PHOTOS, UPLOAD_VIDEOS, MUSIC_DIR]:
        os.makedirs(d, exist_ok=True)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def get_users():     return load_json(USERS_FILE, {})
def save_users(u):   save_json(USERS_FILE, u)
def get_messages():  return load_json(MESSAGES_FILE, [])
def save_messages(m):save_json(MESSAGES_FILE, m)
def get_music():     return load_json(MUSIC_JSON, [])
def save_music(m):   save_json(MUSIC_JSON, m)


def format_file_size(size):
    if size >= 1024 ** 3: return f"{size/(1024**3):.2f} GB"
    if size >= 1024 ** 2: return f"{size/(1024**2):.2f} MB"
    if size >= 1024:      return f"{size/1024:.2f} KB"
    return f"{size} B"


def update_last_seen(username):
    users = get_users()
    if username in users:
        users[username]['last_seen'] = time.time()
        save_users(users)


def mark_offline(username):
    users = get_users()
    if username in users:
        users[username]['last_seen'] = time.time() - 3600
        save_users(users)


def is_online(username):
    users = get_users()
    last = users.get(username, {}).get('last_seen')
    return bool(last) and (time.time() - last) < 15


def time_ago(ts):
    if not ts: return "a long time ago"
    d = int(time.time() - ts)
    if d < 10:    return "just now"
    if d < 60:    return f"{d}s ago"
    if d < 3600:  return f"{d//60}m ago"
    if d < 86400: return f"{d//3600}h ago"
    return f"{d//86400}d ago"


def init_files():
    """Create all data files + folders on first run."""
    ensure_dirs()
    if not os.path.exists(USERS_FILE):
        save_users({
            "SOUMIK": {"password": generate_password_hash("soumik123"), "last_seen": None},
            "SANAYA": {"password": generate_password_hash("sanaya123"), "last_seen": None},
        })
        print("✓ Created users.json  →  SOUMIK/soumik123  |  SANAYA/sanaya123")
    if not os.path.exists(MESSAGES_FILE):
        save_messages([])
    if not os.path.exists(MUSIC_JSON):
        save_music([])


# ==================================================================
# FLASK APP
# ==================================================================
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_VIDEO_SIZE
init_files()


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if 'user' not in session:
            return jsonify({'success': False, 'error': 'not_logged_in'}), 401
        return f(*a, **k)
    return w


@app.before_request
def check_auto_logout():
    if 'user' in session:
        lt = session.get('login_time', time.time())
        if time.time() - lt >= AUTO_LOGOUT_TIME:
            mark_offline(session['user'])
            session.clear()
            if request.args.get('action'):
                return jsonify({'success': False, 'auto_logout': True}), 401
            return redirect(url_for('index', auto_logout=1))


# ----- Static upload serving -----
@app.route('/uploads/photos/<path:f>')
def serve_photo(f): return send_from_directory(UPLOAD_PHOTOS, f)

@app.route('/uploads/videos/<path:f>')
def serve_video(f): return send_from_directory(UPLOAD_VIDEOS, f)

@app.route('/music/<path:f>')
def serve_music(f): return send_from_directory(MUSIC_DIR, f)


# ==================================================================
# MAIN ROUTE  (login page + chat page + all AJAX)
# ==================================================================
@app.route('/', methods=['GET', 'POST'])
def index():
    action = request.args.get('action')

    # ---------- LOGIN ----------
    if action == 'login' and request.method == 'POST':
        pw = request.form.get('password', '')
        for u, d in get_users().items():
            if check_password_hash(d['password'], pw):
                session['user'] = u
                session['login_time'] = time.time()
                update_last_seen(u)
                return jsonify({'success': True, 'user': u})
        return jsonify({'success': False})

    # ---------- GET MESSAGES ----------
    if action == 'get_messages' and 'user' in session:
        msgs = get_messages()
        cur = session['user']
        update_last_seen(cur)
        changed = False
        for m in msgs:
            if m.get('receiver') == cur and not m.get('seen', False):
                m['seen'] = True
                m['seen_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                changed = True
        if changed: save_messages(msgs)
        return jsonify(msgs)

    # ---------- SEND MESSAGE ----------
    if action == 'send_message' and 'user' in session:
        receiver = request.form.get('receiver', '')
        text = request.form.get('message', '')
        text = str(escape(text)) if text else ''

        msg = {
            'sender': session['user'],
            'receiver': receiver,
            'message': text,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'seen': False,
            'seen_time': None,
            'type': 'text'
        }

        file = request.files.get('file')
        if file and file.filename:
            mime = file.mimetype or ''
            file.seek(0, os.SEEK_END); size = file.tell(); file.seek(0)

            if mime in ALLOWED_PHOTO_TYPES and size <= MAX_PHOTO_SIZE:
                udir, mtype, rel = UPLOAD_PHOTOS, 'photo', 'uploads/photos'
            elif mime in ALLOWED_VIDEO_TYPES and size <= MAX_VIDEO_SIZE:
                udir, mtype, rel = UPLOAD_VIDEOS, 'video', 'uploads/videos'
            else:
                return jsonify({'success': False,
                                'error': 'Invalid file type or size exceeded'}), 400

            safe = secure_filename(file.filename) or 'file'
            fname = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe}"
            file.save(os.path.join(udir, fname))

            msg['file'] = f"{rel}/{fname}"
            msg['file_name'] = file.filename
            msg['file_size'] = size
            msg['file_size_formatted'] = format_file_size(size)
            msg['type'] = mtype

        msgs = get_messages()
        msgs.append(msg)
        save_messages(msgs)
        return jsonify({'success': True})

    # ---------- GET STATUS ----------
    if action == 'get_status' and 'user' in session:
        st = {}
        for u in get_users():
            last = get_users()[u].get('last_seen')
            st[u] = {'online': is_online(u), 'last_seen': last,
                     'last_seen_ago': time_ago(last)}
        return jsonify(st)

    # ---------- REMAINING TIME ----------
    if action == 'get_remaining_time' and 'user' in session:
        el = time.time() - session.get('login_time', time.time())
        return jsonify({'remaining': max(0, int(AUTO_LOGOUT_TIME - el))})

    # ---------- LOGOUT ----------
    if action == 'logout' and 'user' in session:
        mark_offline(session['user'])
        session.clear()
        return jsonify({'success': True})

    # ---------- RENDER LOGIN PAGE ----------
    if 'user' not in session:
        auto_logout = bool(request.args.get('auto_logout'))
        songs = get_music()
        login_song = None; has_music = False
        if songs:
            login_song = random.choice(songs)
            if os.path.exists(os.path.join(BASE_DIR, login_song['file'])):
                has_music = True
        if not login_song:
            login_song = {'title': 'Perfect', 'artist': 'Ed Sheeran', 'file': ''}

        return render_template_string(LOGIN_HTML,
            auto_logout=auto_logout,
            login_song=login_song,
            has_music=has_music,
            auto_logout_min=AUTO_LOGOUT_TIME // 60)

    # ---------- RENDER CHAT PAGE ----------
    cur = session['user']
    users = get_users()
    others = [u for u in users if u != cur]
    partner = request.args.get('chat_with')
    if partner not in others:
        partner = others[0] if others else ''

    el = time.time() - session.get('login_time', time.time())
    remaining = max(0, int(AUTO_LOGOUT_TIME - el))

    def initials(n):
        n = (n or '').strip()
        return n[:2].upper() if n else '?'

    return render_template_string(CHAT_HTML,
        current_user=cur,
        other_users=others,
        chat_partner=partner,
        remaining=remaining,
        auto_logout_time=AUTO_LOGOUT_TIME,
        max_photo_size=MAX_PHOTO_SIZE,
        max_video_size=MAX_VIDEO_SIZE,
        initials=initials)


# ==================================================================
# LOGIN PAGE TEMPLATE
# ==================================================================
LOGIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>💕 SoulChat - Premium</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0a0a0a,#1a1a2e,#16213e);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;overflow:hidden}
.bg-particles{position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0}
.particle{position:absolute;border-radius:50%;background:rgba(255,20,147,.3);animation:float linear infinite}
@keyframes float{0%{transform:translateY(100vh) rotate(0);opacity:0}10%{opacity:1}90%{opacity:1}100%{transform:translateY(-100vh) rotate(720deg);opacity:0}}
.login-container{position:relative;z-index:1;background:rgba(255,255,255,.03);backdrop-filter:blur(30px);padding:50px 40px;border-radius:40px;box-shadow:0 30px 80px rgba(255,20,147,.1),inset 0 1px 0 rgba(255,255,255,.05);text-align:center;max-width:450px;width:100%;border:1px solid rgba(255,255,255,.05);animation:floatContainer 3s ease-in-out infinite}
@keyframes floatContainer{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
.heart-icon{font-size:80px;cursor:pointer;transition:all .5s;display:inline-block;animation:heartPulse 1.5s ease-in-out infinite;filter:drop-shadow(0 0 30px rgba(255,20,147,.3));position:relative}
.heart-icon .ripple{position:absolute;border-radius:50%;border:2px solid rgba(255,20,147,.2);animation:ripple 2s ease-out infinite;pointer-events:none}
@keyframes ripple{0%{width:0;height:0;opacity:1;top:50%;left:50%;transform:translate(-50%,-50%)}100%{width:200px;height:200px;opacity:0;top:50%;left:50%;transform:translate(-50%,-50%)}}
@keyframes heartPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.15)}}
.heart-icon:hover{transform:scale(1.2) rotate(-5deg)}
.title{font-size:36px;font-weight:800;background:linear-gradient(135deg,#ff69b4,#ff1493,#ff6b6b);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:10px 0;text-shadow:0 0 40px rgba(255,20,147,.2)}
.subtitle{color:rgba(255,255,255,.4);font-size:14px;margin-bottom:25px;letter-spacing:3px}
.music-player{display:none;background:rgba(255,255,255,.03);border-radius:20px;padding:25px;margin:20px 0;border:1px solid rgba(255,255,255,.05);animation:slideUp .8s ease}
.music-player.show{display:block}
@keyframes slideUp{from{opacity:0;transform:translateY(30px) scale(.95)}to{opacity:1;transform:translateY(0) scale(1)}}
.music-player .music-icon{font-size:50px;display:block;margin-bottom:5px}
.music-player .music-title{color:#fff;font-size:20px;font-weight:700;margin-bottom:3px}
.music-player .music-artist{color:rgba(255,255,255,.4);font-size:14px;margin-bottom:15px}
.music-player .progress-bar{width:100%;height:4px;background:rgba(255,255,255,.05);border-radius:5px;overflow:hidden;margin:10px 0}
.music-player .progress-bar .fill{height:100%;background:linear-gradient(90deg,#ff69b4,#ff1493);border-radius:5px;width:0;transition:width .5s}
.music-player .time-display{display:flex;justify-content:space-between;font-size:11px;color:rgba(255,255,255,.2)}
.music-player .controls{display:flex;justify-content:center;gap:15px;margin-top:15px}
.music-player .controls button{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.05);color:#fff;padding:10px 25px;border-radius:30px;cursor:pointer;font-size:14px;transition:all .3s;font-weight:600}
.music-player .controls button:hover{background:rgba(255,20,147,.1);border-color:rgba(255,20,147,.2);transform:scale(1.05)}
.music-player .controls .skip-btn{background:rgba(255,20,147,.1);border-color:rgba(255,20,147,.2)}
.music-player .no-music{color:rgba(255,255,255,.3);font-size:13px;padding:10px}
.datetime-display{background:rgba(255,255,255,.02);padding:20px;border-radius:20px;margin:20px 0;border:1px solid rgba(255,255,255,.03)}
.datetime-display .time{font-size:34px;font-weight:700;color:#fff;font-family:'Courier New',monospace;text-shadow:0 0 20px rgba(255,20,147,.1)}
.datetime-display .date{color:rgba(255,255,255,.4);font-size:16px;margin-top:5px}
.datetime-display .day{color:#ff69b4;font-size:14px;font-weight:600;margin-top:3px}
.password-box{display:none;margin-top:25px;animation:slideDown .5s ease}
.password-box.show{display:block}
@keyframes slideDown{from{opacity:0;transform:translateY(-20px)}to{opacity:1;transform:translateY(0)}}
.password-box .secret-label{color:rgba(255,255,255,.4);font-size:13px;margin-bottom:10px;letter-spacing:2px}
.password-box .secret-label .highlight{color:#ff69b4;font-weight:600}
.password-box input{width:100%;padding:18px 22px;border:1px solid rgba(255,255,255,.05);border-radius:15px;font-size:16px;background:rgba(255,255,255,.03);color:#fff;transition:all .3s;margin-bottom:15px;outline:none}
.password-box input::placeholder{color:rgba(255,255,255,.2)}
.password-box input:focus{border-color:rgba(255,20,147,.3);box-shadow:0 0 30px rgba(255,20,147,.05);background:rgba(255,255,255,.05)}
.password-box button{width:100%;padding:18px;background:linear-gradient(135deg,#ff69b4,#ff1493);color:#fff;border:none;border-radius:15px;font-size:18px;font-weight:700;cursor:pointer;transition:all .3s;box-shadow:0 5px 25px rgba(255,20,147,.2);letter-spacing:1px}
.password-box button:hover{transform:translateY(-3px);box-shadow:0 8px 35px rgba(255,20,147,.3)}
.error-msg{color:#ff1493;font-size:14px;margin-top:12px;display:none;background:rgba(255,20,147,.05);padding:10px;border-radius:10px;border:1px solid rgba(255,20,147,.1)}
.auto-logout-msg{background:rgba(255,20,147,.05);color:#ff69b4;padding:15px;border-radius:15px;margin-bottom:15px;border:1px solid rgba(255,20,147,.1);display:{{ 'block' if auto_logout else 'none' }}}
.auto-logout-msg .icon{font-size:30px;display:block}
.auto-logout-msg .time-badge{display:inline-block;background:linear-gradient(135deg,#ff69b4,#ff1493);color:#fff;padding:3px 12px;border-radius:20px;font-size:14px;font-weight:600;margin-top:5px}
.footer-text{margin-top:20px;color:rgba(255,255,255,.2);font-size:12px;letter-spacing:1px}
.decorative-line{width:60px;height:3px;background:linear-gradient(90deg,#ff69b4,#ff1493);margin:15px auto;border-radius:5px}
.auto-badge{display:inline-block;background:linear-gradient(135deg,#ff69b4,#ff1493);color:#fff;padding:4px 15px;border-radius:20px;font-size:12px;font-weight:600;margin-top:5px}
.music-indicator{display:inline-block;background:rgba(255,20,147,.1);padding:2px 12px;border-radius:20px;font-size:11px;color:#ff69b4;margin-top:5px}
</style>
</head>
<body>
<div class="bg-particles" id="particles"></div>
<div class="login-container">
    <div class="heart-icon" id="heartIcon">❤️
        <span class="ripple"></span>
        <span class="ripple" style="animation-delay:.5s"></span>
        <span class="ripple" style="animation-delay:1s"></span>
    </div>
    <div class="title">SoulChat</div>
    <div class="subtitle">✨ Where Hearts Connect ✨</div>
    <div class="decorative-line"></div>

    <div class="auto-logout-msg">
        <span class="icon">⏰</span>
        <strong>Auto-Logged Out!</strong><br>
        <small>You were automatically logged out after {{ auto_logout_min }} minutes</small><br>
        <span class="time-badge">⏱️ {{ auto_logout_min }} MIN</span>
    </div>

    <div class="music-player" id="musicPlayer">
        <span class="music-icon">🎵</span>
        {% if has_music %}
            <div class="music-title">{{ login_song.title }}</div>
            <div class="music-artist">🎤 {{ login_song.artist }}</div>
            <audio id="musicAudio" preload="auto">
                <source src="/{{ login_song.file }}" type="audio/mpeg">
            </audio>
        {% else %}
            <div class="music-title">No Music Uploaded</div>
            <div class="music-artist">💕 Admin can upload from panel</div>
            <div class="no-music">
                <span style="font-size:30px;display:block">🎵</span>
                Upload music in admin panel<br>
                <small style="color:rgba(255,255,255,.2)">Go to Admin → Upload Music</small>
            </div>
        {% endif %}
        <div class="progress-bar"><div class="fill" id="musicProgress"></div></div>
        <div class="time-display">
            <span id="currentTime">0:00</span>
            <span id="totalTime">0:00</span>
        </div>
        <div class="controls">
            {% if has_music %}<button onclick="togglePlayPause()" id="playPauseBtn">⏸️ Pause</button>{% endif %}
            <button onclick="skipMusic()" class="skip-btn">⏭️ Skip</button>
        </div>
        {% if has_music %}<div class="music-indicator">🎵 {{ login_song.title }} playing...</div>{% endif %}
    </div>

    <div class="datetime-display">
        <div class="time" id="timeDisplay">--:--:--</div>
        <div class="date" id="dateDisplay">📅 Loading...</div>
        <div class="day" id="dayDisplay">📆 Loading...</div>
    </div>

    <div class="password-box" id="passwordBox">
        <div class="secret-label">🔑 Enter your <span class="highlight">Secret Key</span></div>
        <input type="password" id="passwordInput" placeholder="💕 Your secret password..." autofocus>
        <button onclick="doLogin()">💕 Unlock Love 💕</button>
        <div class="error-msg" id="errorMsg">❌ Wrong password! Please try again 💔</div>
    </div>
    <div class="footer-text">
        💝 Made with Love • <span class="auto-badge">⏰ Auto-Logout: {{ auto_logout_min }} MIN</span>
    </div>
</div>

<script>
(function(){
    const c=document.getElementById('particles');
    for(let i=0;i<30;i++){
        const p=document.createElement('div');
        p.className='particle';
        const s=Math.random()*6+2;
        p.style.width=s+'px';p.style.height=s+'px';
        p.style.left=Math.random()*100+'%';
        p.style.animationDuration=(Math.random()*20+15)+'s';
        p.style.animationDelay=(Math.random()*20)+'s';
        p.style.background=`rgba(255,20,147,${Math.random()*0.3+0.1})`;
        c.appendChild(p);
    }
})();

function updateDateTime(){
    const n=new Date();
    document.getElementById('timeDisplay').textContent=n.toLocaleTimeString('en-IN',{hour12:true,hour:'2-digit',minute:'2-digit',second:'2-digit'});
    document.getElementById('dateDisplay').textContent='📅 '+n.toLocaleDateString('en-IN',{weekday:'long',year:'numeric',month:'long',day:'numeric'});
    document.getElementById('dayDisplay').textContent='📆 '+n.toLocaleDateString('en-IN',{weekday:'long'});
}
updateDateTime();setInterval(updateDateTime,1000);

const HAS_MUSIC={{ 'true' if has_music else 'false' }};
let audio=null,isSkipped=false;

function formatTime(s){if(isNaN(s))return '0:00';return Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');}

if(HAS_MUSIC){
    audio=document.getElementById('musicAudio');
    audio.addEventListener('loadedmetadata',()=>{document.getElementById('totalTime').textContent=formatTime(audio.duration);});
    audio.addEventListener('timeupdate',()=>{
        const pct=(audio.currentTime/audio.duration)*100;
        document.getElementById('musicProgress').style.width=pct+'%';
        document.getElementById('currentTime').textContent=formatTime(audio.currentTime);
    });
    audio.addEventListener('ended',()=>{
        if(!isSkipped){
            document.getElementById('musicPlayer').classList.remove('show');
            document.getElementById('passwordBox').classList.add('show');
            document.getElementById('passwordInput').focus();
        }
    });
}

function togglePlayPause(){
    if(!audio)return;
    const b=document.getElementById('playPauseBtn');
    if(audio.paused){audio.play();b.textContent='⏸️ Pause';}
    else{audio.pause();b.textContent='▶️ Play';}
}
function skipMusic(){
    isSkipped=true;
    if(audio){audio.pause();audio.currentTime=0;}
    document.getElementById('musicPlayer').classList.remove('show');
    document.getElementById('passwordBox').classList.add('show');
    document.getElementById('passwordInput').focus();
}
document.getElementById('heartIcon').addEventListener('click',function(){
    const box=document.getElementById('passwordBox');
    const music=document.getElementById('musicPlayer');
    if(box.classList.contains('show')){
        box.classList.remove('show');music.classList.remove('show');
        if(audio){audio.pause();audio.currentTime=0;}
    } else {
        music.classList.add('show');
        if(audio){audio.play().catch(()=>{});document.getElementById('playPauseBtn').textContent='⏸️ Pause';}
        else {setTimeout(()=>{document.getElementById('passwordBox').classList.add('show');document.getElementById('passwordInput').focus();},800);}
    }
});

document.getElementById('passwordInput').addEventListener('keypress',e=>{if(e.key==='Enter')doLogin();});

function doLogin(){
    const pw=document.getElementById('passwordInput').value;
    if(!pw)return;
    const btn=document.querySelector('.password-box button');
    btn.textContent='⏳ Checking...';btn.disabled=true;
    fetch('/?action=login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'password='+encodeURIComponent(pw)})
    .then(r=>r.json())
    .then(d=>{
        if(d.success)window.location.reload();
        else{
            document.getElementById('errorMsg').style.display='block';
            document.getElementById('passwordInput').value='';
            document.getElementById('passwordInput').focus();
            setTimeout(()=>{document.getElementById('errorMsg').style.display='none';},3000);
            btn.textContent='💕 Unlock Love 💕';btn.disabled=false;
        }
    }).catch(()=>{btn.textContent='💕 Unlock Love 💕';btn.disabled=false;});
}
</script>
</body>
</html>
"""


# ==================================================================
# CHAT PAGE TEMPLATE
# ==================================================================
CHAT_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>💕 SoulChat - {{ current_user }}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0a0a0a,#1a1a2e,#16213e)}
.chat-container{width:100vw;height:100vh;background:rgba(255,255,255,.03);backdrop-filter:blur(20px);display:flex;overflow:hidden}
.sidebar{width:280px;min-width:280px;background:rgba(255,255,255,.03);padding:20px 15px;border-right:1px solid rgba(255,255,255,.05);display:flex;flex-direction:column;height:100vh;overflow:hidden}
.sidebar-header{text-align:center;padding-bottom:15px;border-bottom:1px solid rgba(255,255,255,.05);flex-shrink:0}
.sidebar-header .heart{font-size:30px;display:block;filter:drop-shadow(0 0 20px rgba(255,20,147,.3))}
.sidebar-header h2{color:#fff;font-size:20px;margin-top:3px;background:linear-gradient(135deg,#ff69b4,#ff1493);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sidebar-header .user-name{color:rgba(255,255,255,.6);font-weight:600;font-size:13px;margin-top:2px}
.sidebar-header .timer-box{margin-top:8px;padding:6px 12px;background:rgba(255,255,255,.05);border-radius:10px;border:1px solid rgba(255,255,255,.05)}
.sidebar-header .timer-box .label{font-size:10px;color:rgba(255,255,255,.3)}
.sidebar-header .timer-box .time{font-size:18px;font-weight:700;color:#ff69b4;font-family:'Courier New',monospace}
.sidebar-header .timer-box .time.warning{color:#ff1493;animation:blink .5s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.user-list{flex:1;margin-top:15px;overflow-y:auto;overflow-x:hidden}
.user-list::-webkit-scrollbar{width:4px}
.user-list::-webkit-scrollbar-thumb{background:rgba(255,182,193,.3);border-radius:10px}
.user-item{display:flex;align-items:center;padding:12px 15px;border-radius:12px;margin-bottom:8px;cursor:pointer;transition:all .3s;background:rgba(255,255,255,.02);border:1px solid transparent}
.user-item:hover{background:rgba(255,20,147,.05);transform:translateX(5px);border-color:rgba(255,20,147,.1)}
.user-item.active{background:rgba(255,20,147,.08);border-color:rgba(255,20,147,.3);box-shadow:0 0 30px rgba(255,20,147,.05)}
.user-avatar{width:45px;height:45px;border-radius:50%;background:linear-gradient(135deg,#ff69b4,#ff1493);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:18px;margin-right:12px;flex-shrink:0;box-shadow:0 3px 15px rgba(255,20,147,.2)}
.user-info{flex:1;min-width:0}
.user-info .name{font-weight:600;color:rgba(255,255,255,.9);font-size:14px}
.user-info .status-text{font-size:11px;color:rgba(255,255,255,.3);margin-top:2px}
.status-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:4px}
.status-dot.online{background:#4caf50;box-shadow:0 0 10px rgba(76,175,80,.5)}
.status-dot.offline{background:rgba(255,255,255,.2)}
.sidebar-bottom{flex-shrink:0;padding-top:10px;border-top:1px solid rgba(255,255,255,.05)}
.logout-btn{width:100%;padding:12px;background:linear-gradient(135deg,#ff6b6b,#ee5a24);color:#fff;border:none;border-radius:12px;font-size:14px;font-weight:600;cursor:pointer;transition:all .3s;letter-spacing:1px}
.logout-btn:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(238,90,36,.3)}
.admin-link{display:block;text-align:center;margin-top:8px;color:rgba(255,255,255,.3);text-decoration:none;font-size:11px;transition:opacity .3s}
.admin-link:hover{color:rgba(255,255,255,.6)}
.chat-main{flex:1;display:flex;flex-direction:column;background:rgba(0,0,0,.2);height:100vh;overflow:hidden}
.chat-header{padding:15px 25px;border-bottom:1px solid rgba(255,255,255,.05);display:flex;align-items:center;justify-content:space-between;background:rgba(0,0,0,.2);flex-shrink:0;flex-wrap:wrap;gap:8px}
.chat-header .partner-info{display:flex;align-items:center;gap:12px}
.chat-header .partner-name{font-size:18px;font-weight:700;color:#fff}
.chat-header .partner-status{font-size:12px;color:rgba(255,255,255,.4)}
.chat-header .last-seen-text{font-size:11px;color:rgba(255,255,255,.3)}
.chat-header .timer-badge{font-size:13px;color:#ff69b4;background:rgba(255,20,147,.05);padding:4px 15px;border-radius:20px;border:1px solid rgba(255,20,147,.1);font-weight:600}
.chat-header .timer-badge.warning{color:#ff1493;border-color:#ff1493;animation:blink .5s infinite}
.chat-messages{flex:1;padding:20px 25px;overflow-y:auto;background:rgba(0,0,0,.1);display:flex;flex-direction:column;min-height:0}
.chat-messages::-webkit-scrollbar{width:6px}
.chat-messages::-webkit-scrollbar-thumb{background:rgba(255,182,193,.2);border-radius:10px}
.message{margin-bottom:12px;animation:slideIn .3s ease}
@keyframes slideIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.message .msg-bubble{display:inline-block;padding:10px 18px;border-radius:20px;max-width:75%;word-wrap:break-word;position:relative;box-shadow:0 2px 10px rgba(0,0,0,.3)}
.message.sent{text-align:right;align-self:flex-end}
.message.sent .msg-bubble{background:linear-gradient(135deg,#ff69b4,#ff1493);color:#fff;border-bottom-right-radius:5px}
.message.received{text-align:left;align-self:flex-start}
.message.received .msg-bubble{background:rgba(255,255,255,.05);color:rgba(255,255,255,.9);border-bottom-left-radius:5px;border:1px solid rgba(255,255,255,.05)}
.message .msg-time{font-size:10px;opacity:.5;margin-top:4px;display:block}
.message.sent .msg-time{color:rgba(255,255,255,.6)}
.message .seen-status{font-size:10px;margin-left:4px}
.message .file-attachment{display:block;margin-top:6px;text-decoration:none;color:inherit}
.message .file-attachment img,.message .file-attachment video{max-width:250px;max-height:300px;border-radius:12px;display:block;box-shadow:0 3px 15px rgba(0,0,0,.3)}
.message .file-name-text{font-size:11px;margin-top:4px;opacity:.6}
.chat-input{padding:15px 25px;border-top:1px solid rgba(255,255,255,.05);display:flex;gap:10px;background:rgba(0,0,0,.2);align-items:flex-end;flex-shrink:0;flex-wrap:wrap}
.chat-input .input-wrapper{flex:1;display:flex;gap:10px;align-items:flex-end;min-width:0}
.chat-input textarea{flex:1;padding:12px 18px;border:1px solid rgba(255,255,255,.05);border-radius:25px;font-size:14px;resize:none;font-family:inherit;transition:all .3s;max-height:100px;min-height:45px;background:rgba(255,255,255,.03);color:#fff;line-height:1.4}
.chat-input textarea::placeholder{color:rgba(255,255,255,.2)}
.chat-input textarea:focus{outline:none;border-color:rgba(255,20,147,.3);box-shadow:0 0 30px rgba(255,20,147,.05);background:rgba(255,255,255,.05)}
.chat-input .file-upload-btn{padding:12px 16px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05);border-radius:25px;cursor:pointer;transition:all .3s;font-size:20px;display:flex;align-items:center;justify-content:center;min-width:48px;height:48px;color:rgba(255,255,255,.5)}
.chat-input .file-upload-btn:hover{background:rgba(255,20,147,.05);border-color:rgba(255,20,147,.2);color:#fff}
.chat-input .send-btn{padding:12px 30px;background:linear-gradient(135deg,#ff69b4,#ff1493);color:#fff;border:none;border-radius:25px;font-size:15px;font-weight:600;cursor:pointer;transition:all .3s;white-space:nowrap;box-shadow:0 5px 20px rgba(255,20,147,.2);height:48px}
.chat-input .send-btn:hover{transform:scale(1.05);box-shadow:0 8px 30px rgba(255,20,147,.3)}
.chat-input .send-btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
#fileInput{display:none}
.file-preview{padding:8px 15px;background:rgba(255,20,147,.05);border-radius:12px;font-size:12px;color:rgba(255,255,255,.6);display:none;align-items:center;gap:10px;border:1px solid rgba(255,20,147,.1);flex-shrink:0;width:100%}
.file-preview.show{display:flex}
.file-preview .remove-file{cursor:pointer;color:#ff1493;font-weight:700;font-size:16px}
.file-preview .file-info{flex:1;display:flex;flex-direction:column;gap:2px}
.file-preview .file-info .name{font-size:12px;color:rgba(255,255,255,.8)}
.file-preview .file-info .size{font-size:10px;color:rgba(255,255,255,.3)}
.file-preview .upload-progress{width:100%;height:3px;background:rgba(255,255,255,.05);border-radius:5px;overflow:hidden}
.file-preview .upload-progress .fill{height:100%;background:linear-gradient(90deg,#ff69b4,#ff1493);border-radius:5px;width:0;transition:width .3s}
.file-preview .progress-text{font-size:11px;color:#ff69b4;font-weight:600;min-width:45px;text-align:right}
.empty-chat{text-align:center;color:rgba(255,255,255,.2);padding:50px 20px;font-size:15px}
.empty-chat .big-heart{font-size:45px;display:block;margin-bottom:12px;filter:drop-shadow(0 0 30px rgba(255,20,147,.2))}
.chat-messages{scroll-behavior:smooth}
.fullscreen-toggle{background:none;border:1px solid rgba(255,255,255,.05);color:rgba(255,255,255,.3);font-size:18px;cursor:pointer;padding:5px 10px;border-radius:10px;transition:all .3s}
.fullscreen-toggle:hover{color:#fff;border-color:rgba(255,255,255,.1)}
@media (max-width:768px){
    .sidebar{width:200px;min-width:200px;padding:12px 10px}
    .user-avatar{width:35px;height:35px;font-size:14px;margin-right:8px}
    .user-item{padding:8px 10px}
    .user-info .name{font-size:12px}
    .chat-header{padding:10px 15px}
    .chat-messages{padding:12px 15px}
    .chat-input{padding:10px 15px}
    .message .msg-bubble{max-width:90%}
    .message .file-attachment img,.message .file-attachment video{max-width:150px;max-height:200px}
}
@media (max-width:480px){
    .sidebar{width:160px;min-width:160px;padding:8px 8px}
    .sidebar-header h2{font-size:16px}
    .sidebar-header .timer-box .time{font-size:14px}
    .chat-header .partner-name{font-size:14px}
    .chat-header .timer-badge{font-size:11px;padding:3px 10px}
    .chat-input .send-btn{padding:10px 18px;font-size:13px;height:42px}
    .chat-input textarea{font-size:13px;min-height:38px;padding:10px 14px}
    .chat-input .file-upload-btn{height:42px;min-width:42px;font-size:18px;padding:10px 12px}
}
</style>
</head>
<body>
<div class="chat-container" id="chatContainer">
    <div class="sidebar">
        <div class="sidebar-header">
            <span class="heart">💕</span>
            <h2>SoulChat</h2>
            <div class="user-name">👤 {{ current_user }}</div>
            <div class="timer-box">
                <div class="label">⏰ Auto-Logout in</div>
                <div class="time" id="timerDisplay">{{ '%02d:%02d' % (remaining//60, remaining%60) }}</div>
            </div>
        </div>
        <div class="user-list">
            {% for user in other_users %}
            <div class="user-item {% if user == chat_partner %}active{% endif %}" onclick="switchChat('{{ user }}')">
                <div class="user-avatar">{{ initials(user) }}</div>
                <div class="user-info">
                    <div class="name">{{ user }}</div>
                    <div class="status-text" id="status_{{ user }}">
                        <span class="status-dot offline"></span><span>Offline</span>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        <div class="sidebar-bottom">
            <button class="logout-btn" onclick="logout()">🚪 Logout</button>
            <a href="/admin" class="admin-link">⚙️ Admin Panel</a>
        </div>
    </div>

    <div class="chat-main">
        <div class="chat-header">
            <div class="partner-info">
                <div class="user-avatar" style="width:40px;height:40px;font-size:16px;">{{ initials(chat_partner) }}</div>
                <div>
                    <div class="partner-name">{{ chat_partner }}</div>
                    <div class="partner-status" id="partnerStatus">
                        <span class="status-dot offline"></span><span>Offline</span>
                    </div>
                </div>
            </div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <div class="last-seen-text">Last seen: <span id="lastSeen">Just now</span></div>
                <div class="timer-badge" id="headerTimer">⏰ <span id="headerTimerCount">{{ '%02d:%02d' % (remaining//60, remaining%60) }}</span></div>
                <button class="fullscreen-toggle" onclick="toggleFullscreen()" title="Fullscreen">⛶</button>
            </div>
        </div>

        <div class="chat-messages" id="chatMessages">
            <div class="empty-chat">
                <span class="big-heart">💕</span>
                <div>No messages yet</div>
                <div style="font-size:13px;margin-top:5px;opacity:.5">Start a conversation with {{ chat_partner }}</div>
            </div>
        </div>

        <div class="chat-input">
            <input type="file" id="fileInput" onchange="handleFileSelect(event)" accept="image/*,video/*">
            <div class="input-wrapper">
                <label for="fileInput" class="file-upload-btn" title="Send Photo/Video">📎</label>
                <textarea id="messageInput" rows="1" placeholder="Type a message... 💬" onkeypress="handleKeyPress(event)"></textarea>
                <button class="send-btn" id="sendBtn" onclick="sendMessage()">Send ❤️</button>
            </div>
            <div class="file-preview" id="filePreview">
                <div class="file-info">
                    <span class="name" id="fileName">file.jpg</span>
                    <span class="size" id="fileSize">10 MB</span>
                    <div class="upload-progress"><div class="fill" id="uploadProgress"></div></div>
                </div>
                <span class="progress-text" id="progressText">0%</span>
                <span class="remove-file" onclick="removeFile()">✕</span>
            </div>
        </div>
    </div>
</div>

<script>
const currentUser='{{ current_user }}';
const chatPartner='{{ chat_partner }}';
const autoLogoutTime={{ auto_logout_time }};
const maxPhotoSize={{ max_photo_size }};
const maxVideoSize={{ max_video_size }};
let selectedFile=null;
let messageInterval=null,statusInterval=null,timerInterval=null;
let remainingTime={{ remaining }};

document.getElementById('messageInput').addEventListener('input',function(){
    this.style.height='auto';
    this.style.height=Math.min(this.scrollHeight,100)+'px';
});
function handleKeyPress(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}}
function switchChat(u){window.location.href='/?chat_with='+u;}
function logout(){
    if(confirm('Are you sure you want to logout? 💔')){
        fetch('/?action=logout').then(()=>window.location.href='/');
    }
}
function toggleFullscreen(){
    if(!document.fullscreenElement){document.documentElement.requestFullscreen().catch(()=>{});}
    else if(document.exitFullscreen){document.exitFullscreen();}
}
function formatFileSize(b){
    if(b>=1073741824)return (b/1073741824).toFixed(2)+' GB';
    if(b>=1048576)return (b/1048576).toFixed(2)+' MB';
    if(b>=1024)return (b/1024).toFixed(2)+' KB';
    return b+' B';
}
function handleFileSelect(e){
    const file=e.target.files[0];if(!file)return;
    const isPhoto=file.type.startsWith('image/');
    const isVideo=file.type.startsWith('video/');
    if(!isPhoto&&!isVideo){alert('❌ Only images and videos are allowed!');e.target.value='';return;}
    if(isPhoto&&file.size>maxPhotoSize){alert('❌ Photo size exceeds '+formatFileSize(maxPhotoSize)+' limit!');e.target.value='';return;}
    if(isVideo&&file.size>maxVideoSize){alert('❌ Video size exceeds '+formatFileSize(maxVideoSize)+' limit!');e.target.value='';return;}
    selectedFile=file;
    document.getElementById('fileName').textContent=file.name;
    document.getElementById('fileSize').textContent=formatFileSize(file.size);
    document.getElementById('uploadProgress').style.width='0%';
    document.getElementById('progressText').textContent='0%';
    document.getElementById('filePreview').classList.add('show');
    e.target.value='';
}
function removeFile(){
    selectedFile=null;
    document.getElementById('filePreview').classList.remove('show');
    document.getElementById('uploadProgress').style.width='0%';
    document.getElementById('progressText').textContent='0%';
}
function sendMessage(){
    const input=document.getElementById('messageInput');
    const message=input.value.trim();
    if(!message&&!selectedFile){input.focus();return;}
    const fd=new FormData();
    if(message)fd.append('message',message);
    if(selectedFile)fd.append('file',selectedFile);
    fd.append('receiver',chatPartner);
    const btn=document.getElementById('sendBtn');
    btn.disabled=true;btn.textContent='⏳ Sending...';
    const xhr=new XMLHttpRequest();
    xhr.open('POST','/?action=send_message');
    xhr.upload.addEventListener('progress',e=>{
        if(e.lengthComputable){
            const pct=Math.round((e.loaded/e.total)*100);
            document.getElementById('uploadProgress').style.width=pct+'%';
            document.getElementById('progressText').textContent=pct+'%';
        }
    });
    xhr.onload=()=>{
        try{
            const d=JSON.parse(xhr.responseText);
            if(d.success){input.value='';input.style.height='auto';removeFile();loadMessages();}
            else alert('❌ '+(d.error||'Failed to send message!'));
        }catch(e){alert('❌ Error sending message!');}
        btn.disabled=false;btn.textContent='Send ❤️';input.focus();
    };
    xhr.onerror=()=>{alert('❌ Network error!');btn.disabled=false;btn.textContent='Send ❤️';};
    xhr.send(fd);
}
function loadMessages(){
    fetch('/?action=get_messages').then(r=>r.json()).then(messages=>{
        const c=document.getElementById('chatMessages');
        const filtered=messages.filter(m=>
            (m.sender===currentUser&&m.receiver===chatPartner)||
            (m.sender===chatPartner&&m.receiver===currentUser));
        if(filtered.length===0){
            c.innerHTML=`<div class="empty-chat"><span class="big-heart">💕</span><div>No messages yet</div><div style="font-size:13px;margin-top:5px;opacity:.5">Start a conversation with ${chatPartner}</div></div>`;
            return;
        }
        let html='';
        filtered.forEach(m=>{
            const sent=m.sender===currentUser;
            const time=new Date(m.time.replace(' ','T')).toLocaleTimeString('en-IN',{hour12:true,hour:'2-digit',minute:'2-digit'});
            let seen='';
            if(sent)seen=m.seen?'👁️ Seen':'✓ Delivered';
            html+=`<div class="message ${sent?'sent':'received'}"><div class="msg-bubble">`;
            if(m.type==='text'){html+=m.message;}
            else if(m.type==='photo'){
                html+=`<a href="/${m.file}" target="_blank" class="file-attachment"><img src="/${m.file}" alt="Photo" loading="lazy"><div class="file-name-text">📷 ${m.file_name}</div></a>`;
            } else if(m.type==='video'){
                html+=`<div class="file-attachment"><video controls preload="metadata" style="max-width:250px;max-height:300px;border-radius:12px;"><source src="/${m.file}" type="video/mp4">Your browser does not support video.</video><div class="file-name-text">🎬 ${m.file_name}</div></div>`;
            }
            html+=`<span class="msg-time">${time}`;
            if(sent)html+=` <span class="seen-status">${seen}</span>`;
            html+=`</span></div></div>`;
        });
        c.innerHTML=html;
        c.scrollTop=c.scrollHeight;
    });
}
function updateStatus(){
    fetch('/?action=get_status').then(r=>r.json()).then(status=>{
        Object.keys(status).forEach(u=>{
            const el=document.getElementById('status_'+u);
            if(el){
                const on=status[u].online;
                el.innerHTML=`<span class="status-dot ${on?'online':'offline'}"></span><span>${on?'🟢 Online':status[u].last_seen_ago}</span>`;
            }
        });
        if(status[chatPartner]){
            const on=status[chatPartner].online;
            document.getElementById('partnerStatus').innerHTML=`<span class="status-dot ${on?'online':'offline'}"></span><span>${on?'🟢 Online':status[chatPartner].last_seen_ago}</span>`;
            document.getElementById('lastSeen').textContent=on?'Just now':status[chatPartner].last_seen_ago;
        }
    });
}
function updateTimerDisplay(){
    const m=Math.floor(remainingTime/60),s=remainingTime%60;
    const t=`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    document.getElementById('timerDisplay').textContent=t;
    document.getElementById('headerTimerCount').textContent=t;
    document.getElementById('timerDisplay').classList.toggle('warning',remainingTime<60);
    document.getElementById('headerTimer').classList.toggle('warning',remainingTime<60);
}
function startTimer(){
    if(timerInterval)clearInterval(timerInterval);
    timerInterval=setInterval(()=>{
        remainingTime--;updateTimerDisplay();
        if(remainingTime<=0){
            clearInterval(timerInterval);clearInterval(messageInterval);clearInterval(statusInterval);
            fetch('/?action=logout').then(()=>window.location.href='/?auto_logout=1');
        }
    },1000);
}
function startPolling(){
    loadMessages();updateStatus();
    if(messageInterval)clearInterval(messageInterval);
    if(statusInterval)clearInterval(statusInterval);
    messageInterval=setInterval(loadMessages,3000);
    statusInterval=setInterval(updateStatus,5000);
    startTimer();
}
startPolling();
document.getElementById('messageInput').focus();
</script>
</body>
</html>
"""


# ==================================================================
if __name__ == '__main__':
    print("\n" + "="*55)
    print("  💕 SoulChat Server Starting...")
    print("="*55)
    print(f"  📁 Data folder: {BASE_DIR}")
    print(f"  👤 Users: SOUMIK / soumik123   |   SANAYA / sanaya123")
    print(f"  ⏰ Auto-Logout: {AUTO_LOGOUT_TIME//60} minutes")
    print("="*55 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
