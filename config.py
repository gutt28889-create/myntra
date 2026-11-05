import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Auto logout (seconds) — 5 minutes
AUTO_LOGOUT_TIME = 5 * 60

# File upload limits
MAX_PHOTO_SIZE = 10 * 1024 * 1024      # 10 MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024      # 50 MB
MAX_MUSIC_SIZE = 20 * 1024 * 1024      # 20 MB

ALLOWED_PHOTO_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'
}
ALLOWED_VIDEO_TYPES = {
    'video/mp4', 'video/webm', 'video/ogg', 'video/quicktime', 'video/x-msvideo'
}
ALLOWED_MUSIC_EXT = {'mp3', 'wav', 'ogg', 'm4a'}

# Paths
USERS_FILE    = os.path.join(BASE_DIR, 'users.json')
MESSAGES_FILE = os.path.join(BASE_DIR, 'messages.json')
MUSIC_JSON    = os.path.join(BASE_DIR, 'music', 'music.json')
UPLOAD_PHOTOS = os.path.join(BASE_DIR, 'uploads', 'photos')
UPLOAD_VIDEOS = os.path.join(BASE_DIR, 'uploads', 'videos')
MUSIC_DIR     = os.path.join(BASE_DIR, 'music')

ADMIN_USERS = ['SOUMIK', 'SANAYA']

SECRET_KEY = 'change-this-to-a-random-secret-key-please'

def ensure_dirs():
    for d in [UPLOAD_PHOTOS, UPLOAD_VIDEOS, MUSIC_DIR]:
        os.makedirs(d, exist_ok=True)

def format_file_size(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"
