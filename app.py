import os, sqlite3, uuid
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
try:
    import cloudinary
    import cloudinary.uploader
except ImportError:
    cloudinary = None

BASE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(BASE, 'data', 'csya.sqlite3')
LOCAL_UPLOAD = os.path.join(BASE, 'static', 'uploads')
os.makedirs(os.path.dirname(LOCAL_DB), exist_ok=True)
os.makedirs(LOCAL_UPLOAD, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'csya-dev-secret-change-me')
ADMIN_NAME = os.getenv('ADMIN_NAME', 'teamcsya')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'csya123')
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()

DEFAULT = {
    'tagline': 'Tradition in Our Hearts • Unity in Our Strength • Service in Our Spirit',
    'contact': '9440988097', 'whatsapp': '9440988097',
    'instagram': 'https://ig.me/j/AbZKptGF-2YTw4SS/', 'facebook': '', 'youtube': '', 'email': '',
    'about': 'Since 2000, our association has brought together youth, families and friends through devotion, unity, culture and community service in Kondapalkala.',
    'hero_title': '25+ Years of Unity, Devotion & Memories',
    'hero_sub': 'Celebrating our Ganesh traditions, our people and every beautiful chapter of our journey.'
}

CLOUDINARY_CONFIGURED = bool(os.getenv('CLOUDINARY_CLOUD_NAME') and os.getenv('CLOUDINARY_API_KEY') and os.getenv('CLOUDINARY_API_SECRET'))
if cloudinary and CLOUDINARY_CONFIGURED:
    cloudinary.config(
        cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
        api_key=os.getenv('CLOUDINARY_API_KEY'),
        api_secret=os.getenv('CLOUDINARY_API_SECRET'),
        secure=True,
    )


def db():
    if DATABASE_URL:
        if not psycopg:
            raise RuntimeError('DATABASE_URL is set but psycopg is not installed. Run pip install -r requirements.txt.')
        # Render may provide postgres://; psycopg expects postgresql://.
        dsn = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        return psycopg.connect(dsn, row_factory=dict_row)
    c = sqlite3.connect(LOCAL_DB)
    c.row_factory = sqlite3.Row
    return c


def execute(c, sql, params=()):
    return c.execute(sql, params)


def init():
    c = db()
    if DATABASE_URL:
        c.execute('''CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS members(id SERIAL PRIMARY KEY,name TEXT,role TEXT,year TEXT,bio TEXT,photo TEXT,sort_order INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS albums(id SERIAL PRIMARY KEY,title TEXT,year TEXT,category TEXT,description TEXT,cover TEXT,created_at TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS photos(id SERIAL PRIMARY KEY,album_id INTEGER,title TEXT,caption TEXT,file TEXT,created_at TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS events(id SERIAL PRIMARY KEY,title TEXT,date TEXT,location TEXT,description TEXT,photo TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS achievements(id SERIAL PRIMARY KEY,title TEXT,year TEXT,description TEXT,photo TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS videos(id SERIAL PRIMARY KEY,title TEXT,url TEXT,year TEXT,description TEXT,thumbnail TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS announcements(id SERIAL PRIMARY KEY,title TEXT,text TEXT,active INTEGER DEFAULT 1,created_at TEXT)''')
        for k, v in DEFAULT.items():
            c.execute('INSERT INTO settings(k,v) VALUES(%s,%s) ON CONFLICT(k) DO NOTHING', (k, v))
    else:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,role TEXT,year TEXT,bio TEXT,photo TEXT,sort_order INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS albums(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,year TEXT,category TEXT,description TEXT,cover TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS photos(id INTEGER PRIMARY KEY AUTOINCREMENT,album_id INTEGER,title TEXT,caption TEXT,file TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,date TEXT,location TEXT,description TEXT,photo TEXT);
        CREATE TABLE IF NOT EXISTS achievements(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,year TEXT,description TEXT,photo TEXT);
        CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,url TEXT,year TEXT,description TEXT,thumbnail TEXT);
        CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,text TEXT,active INTEGER DEFAULT 1,created_at TEXT);
        ''')
        for k, v in DEFAULT.items():
            c.execute('INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)', (k, v))
    c.commit(); c.close()


init()


def settings():
    c = db(); rows = execute(c, 'SELECT k,v FROM settings').fetchall(); c.close()
    return {r['k']: r['v'] for r in rows}


def admin(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get('admin'):
            return redirect(url_for('login', next=request.path))
        return f(*a, **kw)
    return w


def save_upload(field, folder='csya'):
    f = request.files.get(field)
    if not f or not f.filename:
        return ''
    ext = os.path.splitext(secure_filename(f.filename))[1].lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        return ''
    filename = secure_filename(f.filename)
    if CLOUDINARY_CONFIGURED and cloudinary:
        result = cloudinary.uploader.upload(f, folder=folder, resource_type='image')
        return result.get('public_id', '')
    name = f'{uuid.uuid4().hex}{ext}'
    f.save(os.path.join(LOCAL_UPLOAD, name))
    return name


def media_url(value):
    if not value:
        return ''
    if CLOUDINARY_CONFIGURED and cloudinary and (value.startswith('csya/') or '/' in value):
        return cloudinary.CloudinaryImage(value).build_url(secure=True, quality='auto', fetch_format='auto')
    return url_for('static', filename='uploads/' + value)


def del_file(name):
    if not name:
        return
    if CLOUDINARY_CONFIGURED and cloudinary and '/' in name:
        try:
            cloudinary.uploader.destroy(name, resource_type='image')
        except Exception:
            pass
    else:
        p = os.path.join(LOCAL_UPLOAD, name)
        if os.path.exists(p):
            os.remove(p)


@app.context_processor
def inject():
    return {'site': settings(), 'media_url': media_url, 'admin_name': ADMIN_NAME}


@app.route('/')
def home():
    c = db()
    members = execute(c, 'SELECT * FROM members ORDER BY sort_order,id DESC LIMIT 8').fetchall()
    albums = execute(c, 'SELECT * FROM albums ORDER BY year DESC,id DESC LIMIT 8').fetchall()
    events = execute(c, 'SELECT * FROM events ORDER BY date DESC,id DESC LIMIT 6').fetchall()
    ach = execute(c, 'SELECT * FROM achievements ORDER BY year DESC,id DESC LIMIT 6').fetchall()
    vids = execute(c, 'SELECT * FROM videos ORDER BY year DESC,id DESC LIMIT 4').fetchall()
    anns = execute(c, 'SELECT * FROM announcements WHERE active=1 ORDER BY id DESC LIMIT 3').fetchall()
    photos = execute(c, 'SELECT p.*,a.title album_title,a.year FROM photos p LEFT JOIN albums a ON a.id=p.album_id ORDER BY p.id DESC LIMIT 12').fetchall()
    c.close()
    return render_template('index.html', members=members, albums=albums, events=events, achievements=ach, videos=vids, announcements=anns, photos=photos)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('name', '').strip() == ADMIN_NAME and request.form.get('password', '') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(request.args.get('next') or url_for('admin_dash'))
        flash('Invalid admin name or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('home'))


@app.route('/admin')
@admin
def admin_dash():
    c = db()
    counts = {x: execute(c, f'SELECT COUNT(*) n FROM {x}').fetchone()['n'] for x in ['members','albums','photos','events','achievements','videos']}
    rows = {
        'members': execute(c, 'SELECT * FROM members ORDER BY sort_order,id DESC').fetchall(),
        'albums': execute(c, 'SELECT * FROM albums ORDER BY year DESC,id DESC').fetchall(),
        'events': execute(c, 'SELECT * FROM events ORDER BY date DESC,id DESC').fetchall(),
        'achievements': execute(c, 'SELECT * FROM achievements ORDER BY year DESC,id DESC').fetchall(),
        'videos': execute(c, 'SELECT * FROM videos ORDER BY year DESC,id DESC').fetchall(),
        'announcements': execute(c, 'SELECT * FROM announcements ORDER BY id DESC').fetchall()
    }
    c.close()
    return render_template('admin.html', counts=counts, **rows)


@app.post('/admin/settings')
@admin
def save_settings():
    allowed = set(DEFAULT) | {'site_title'}
    c = db()
    for k, v in request.form.items():
        if k in allowed:
            if DATABASE_URL:
                execute(c, 'INSERT INTO settings(k,v) VALUES(%s,%s) ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v', (k, v.strip()))
            else:
                execute(c, 'INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v', (k, v.strip()))
    c.commit(); c.close(); flash('Website settings updated.', 'ok'); return redirect(url_for('admin_dash') + '#settings')


@app.post('/admin/member')
@admin
def member_add():
    p = save_upload('photo', 'csya/members'); c = db()
    params = (request.form['name'], request.form.get('role',''), request.form.get('year',''), request.form.get('bio',''), p, int(request.form.get('sort_order',0) or 0))
    execute(c, 'INSERT INTO members(name,role,year,bio,photo,sort_order) VALUES(%s,%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO members(name,role,year,bio,photo,sort_order) VALUES(?,?,?,?,?,?)', params)
    c.commit(); c.close(); return redirect(url_for('admin_dash') + '#members')

@app.post('/admin/member/<int:id>/delete')
@admin
def member_del(id):
    c=db(); r=execute(c,'SELECT photo FROM members WHERE id=%s' if DATABASE_URL else 'SELECT photo FROM members WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM members WHERE id=%s' if DATABASE_URL else 'DELETE FROM members WHERE id=?',(id,)); c.commit(); c.close(); del_file(r['photo'] if r else ''); return redirect(url_for('admin_dash')+'#members')

@app.post('/admin/album')
@admin
def album_add():
    p=save_upload('cover','csya/albums'); c=db(); params=(request.form['title'],request.form.get('year',''),request.form.get('category','Memories'),request.form.get('description',''),p,datetime.now().isoformat(timespec='seconds'))
    execute(c,'INSERT INTO albums(title,year,category,description,cover,created_at) VALUES(%s,%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO albums(title,year,category,description,cover,created_at) VALUES(?,?,?,?,?,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#albums')

@app.post('/admin/album/<int:id>/photo')
@admin
def photo_add(id):
    p=save_upload('photo','csya/photos')
    if p:
        c=db(); params=(id,request.form.get('title',''),request.form.get('caption',''),p,datetime.now().isoformat(timespec='seconds'))
        execute(c,'INSERT INTO photos(album_id,title,caption,file,created_at) VALUES(%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO photos(album_id,title,caption,file,created_at) VALUES(?,?,?,?,?)',params); c.commit(); c.close()
    return redirect(url_for('admin_dash')+'#albums')

@app.post('/admin/album/<int:id>/delete')
@admin
def album_del(id):
    c=db(); ps=execute(c,'SELECT file FROM photos WHERE album_id=%s' if DATABASE_URL else 'SELECT file FROM photos WHERE album_id=?',(id,)).fetchall(); a=execute(c,'SELECT cover FROM albums WHERE id=%s' if DATABASE_URL else 'SELECT cover FROM albums WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM photos WHERE album_id=%s' if DATABASE_URL else 'DELETE FROM photos WHERE album_id=?',(id,)); execute(c,'DELETE FROM albums WHERE id=%s' if DATABASE_URL else 'DELETE FROM albums WHERE id=?',(id,)); c.commit(); c.close(); [del_file(x['file']) for x in ps]; del_file(a['cover'] if a else ''); return redirect(url_for('admin_dash')+'#albums')

@app.post('/admin/event')
@admin
def event_add():
    p=save_upload('photo','csya/events'); c=db(); params=(request.form['title'],request.form.get('date',''),request.form.get('location',''),request.form.get('description',''),p)
    execute(c,'INSERT INTO events(title,date,location,description,photo) VALUES(%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO events(title,date,location,description,photo) VALUES(?,?,?,?,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#events')

@app.post('/admin/event/<int:id>/delete')
@admin
def event_del(id):
    c=db(); r=execute(c,'SELECT photo FROM events WHERE id=%s' if DATABASE_URL else 'SELECT photo FROM events WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM events WHERE id=%s' if DATABASE_URL else 'DELETE FROM events WHERE id=?',(id,)); c.commit(); c.close(); del_file(r['photo'] if r else ''); return redirect(url_for('admin_dash')+'#events')

@app.post('/admin/achievement')
@admin
def ach_add():
    p=save_upload('photo','csya/achievements'); c=db(); params=(request.form['title'],request.form.get('year',''),request.form.get('description',''),p)
    execute(c,'INSERT INTO achievements(title,year,description,photo) VALUES(%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO achievements(title,year,description,photo) VALUES(?,?,?,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#achievements')

@app.post('/admin/achievement/<int:id>/delete')
@admin
def ach_del(id):
    c=db(); r=execute(c,'SELECT photo FROM achievements WHERE id=%s' if DATABASE_URL else 'SELECT photo FROM achievements WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM achievements WHERE id=%s' if DATABASE_URL else 'DELETE FROM achievements WHERE id=?',(id,)); c.commit(); c.close(); del_file(r['photo'] if r else ''); return redirect(url_for('admin_dash')+'#achievements')

@app.post('/admin/video')
@admin
def video_add():
    p=save_upload('thumbnail','csya/videos'); c=db(); params=(request.form['title'],request.form['url'],request.form.get('year',''),request.form.get('description',''),p)
    execute(c,'INSERT INTO videos(title,url,year,description,thumbnail) VALUES(%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO videos(title,url,year,description,thumbnail) VALUES(?,?,?,?,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#videos')

@app.post('/admin/video/<int:id>/delete')
@admin
def video_del(id):
    c=db(); r=execute(c,'SELECT thumbnail FROM videos WHERE id=%s' if DATABASE_URL else 'SELECT thumbnail FROM videos WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM videos WHERE id=%s' if DATABASE_URL else 'DELETE FROM videos WHERE id=?',(id,)); c.commit(); c.close(); del_file(r['thumbnail'] if r else ''); return redirect(url_for('admin_dash')+'#videos')

@app.post('/admin/announcement')
@admin
def ann_add():
    c=db(); params=(request.form['title'],request.form['text'],datetime.now().isoformat(timespec='seconds'))
    execute(c,'INSERT INTO announcements(title,text,active,created_at) VALUES(%s,%s,1,%s)' if DATABASE_URL else 'INSERT INTO announcements(title,text,active,created_at) VALUES(?,?,1,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#announcements')

@app.post('/admin/announcement/<int:id>/delete')
@admin
def ann_del(id):
    c=db(); execute(c,'DELETE FROM announcements WHERE id=%s' if DATABASE_URL else 'DELETE FROM announcements WHERE id=?',(id,)); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#announcements')

@app.route('/gallery/<int:album_id>')
def gallery(album_id):
    c=db(); album=execute(c,'SELECT * FROM albums WHERE id=%s' if DATABASE_URL else 'SELECT * FROM albums WHERE id=?',(album_id,)).fetchone(); photos=execute(c,'SELECT * FROM photos WHERE album_id=%s ORDER BY id DESC' if DATABASE_URL else 'SELECT * FROM photos WHERE album_id=? ORDER BY id DESC',(album_id,)).fetchall(); c.close()
    if not album: return redirect(url_for('home'))
    return render_template('gallery.html',album=album,photos=photos)

@app.route('/health')
def health(): return jsonify(ok=True, database='postgresql' if DATABASE_URL else 'sqlite', media='cloudinary' if CLOUDINARY_CONFIGURED else 'local')

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)),debug=True)
