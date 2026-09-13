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
    'hero_sub': 'Celebrating our Ganesh traditions, our people and every beautiful chapter of our journey.',
    'hero_image': '', 'ganesh_image': '',
    'ganesh_eyebrow': 'OUR GANESH • OUR FAITH',
    'ganesh_title': 'Every year,\na new memory.',
    'ganesh_text': 'From the first decoration to the final visarjan, every celebration carries the spirit of our people. This space keeps those moments alive for generations.',
    'location': 'Kondapalkala\nManakondur Mandal\nKarimnagar District',
    'site_title': 'CHATRAPATI SHIVAJI YOUTH ASSOCIATION',
    'footer_text': '© 2000–2026 CSYA • Built for our memories, our people & our future.'
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


def save_setting(k, v):
    c = db()
    if DATABASE_URL:
        execute(c, 'INSERT INTO settings(k,v) VALUES(%s,%s) ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v', (k, v))
    else:
        execute(c, 'INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v', (k, v))
    c.commit(); c.close()


def row_by(table, id):
    c = db()
    row = execute(c, f'SELECT * FROM {table} WHERE id=%s' if DATABASE_URL else f'SELECT * FROM {table} WHERE id=?', (id,)).fetchone()
    c.close(); return row


def delete_row(table, id):
    c = db(); execute(c, f'DELETE FROM {table} WHERE id=%s' if DATABASE_URL else f'DELETE FROM {table} WHERE id=?', (id,)); c.commit(); c.close()


@app.context_processor
def inject():
    return {'site': settings(), 'media_url': media_url, 'admin_name': ADMIN_NAME}


@app.route('/')
def home():
    c = db()
    members = execute(c, 'SELECT * FROM members ORDER BY sort_order,id DESC').fetchall()
    albums = execute(c, 'SELECT * FROM albums ORDER BY year DESC,id DESC').fetchall()
    events = execute(c, 'SELECT * FROM events ORDER BY date DESC,id DESC').fetchall()
    ach = execute(c, 'SELECT * FROM achievements ORDER BY year DESC,id DESC').fetchall()
    vids = execute(c, 'SELECT * FROM videos ORDER BY year DESC,id DESC').fetchall()
    anns = execute(c, 'SELECT * FROM announcements WHERE active=1 ORDER BY id DESC').fetchall()
    photos = execute(c, 'SELECT p.*,a.title album_title,a.year FROM photos p LEFT JOIN albums a ON a.id=p.album_id ORDER BY p.id DESC').fetchall()
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
        'announcements': execute(c, 'SELECT * FROM announcements ORDER BY id DESC').fetchall(),
        'photos': execute(c, 'SELECT p.*,a.title album_title,a.year FROM photos p LEFT JOIN albums a ON a.id=p.album_id ORDER BY p.id DESC').fetchall()
    }
    c.close()
    return render_template('admin.html', counts=counts, **rows)


@app.post('/admin/settings')
@admin
def save_settings():
    allowed = set(DEFAULT) | {'site_title'}
    old = settings()
    c = db()
    for k in allowed:
        if k in request.form:
            v = request.form.get(k, '').strip()
            if DATABASE_URL:
                execute(c, 'INSERT INTO settings(k,v) VALUES(%s,%s) ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v', (k, v))
            else:
                execute(c, 'INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v', (k, v))
    c.commit(); c.close()
    for field, key, folder in [('hero_image','hero_image','csya/site'), ('ganesh_image','ganesh_image','csya/site')]:
        uploaded = save_upload(field, folder)
        if uploaded:
            save_setting(key, uploaded)
            if old.get(key): del_file(old.get(key))
    flash('Website settings updated.', 'ok')
    return redirect(url_for('admin_dash') + '#settings')


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

@app.post('/admin/member/<int:id>/edit')
@admin
def member_edit(id):
    old=row_by('members', id); p=save_upload('photo','csya/members') or (old['photo'] if old else '')
    c=db(); params=(request.form['name'],request.form.get('role',''),request.form.get('year',''),request.form.get('bio',''),p,int(request.form.get('sort_order',0) or 0),id)
    execute(c,'UPDATE members SET name=%s,role=%s,year=%s,bio=%s,photo=%s,sort_order=%s WHERE id=%s' if DATABASE_URL else 'UPDATE members SET name=?,role=?,year=?,bio=?,photo=?,sort_order=? WHERE id=?',params); c.commit(); c.close()
    if old and p != old['photo'] and old['photo']: del_file(old['photo'])
    flash('Member updated.', 'ok'); return redirect(url_for('admin_dash')+'#members')

@app.post('/admin/album')
@admin
def album_add():
    p=save_upload('cover','csya/albums'); c=db(); params=(request.form['title'],request.form.get('year',''),request.form.get('category','Memories'),request.form.get('description',''),p,datetime.now().isoformat(timespec='seconds'))
    execute(c,'INSERT INTO albums(title,year,category,description,cover,created_at) VALUES(%s,%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO albums(title,year,category,description,cover,created_at) VALUES(?,?,?,?,?,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#albums')

@app.post('/admin/album/<int:id>/edit')
@admin
def album_edit(id):
    old=row_by('albums', id); p=save_upload('cover','csya/albums') or (old['cover'] if old else '')
    c=db(); params=(request.form['title'],request.form.get('year',''),request.form.get('category','Memories'),request.form.get('description',''),p,id)
    execute(c,'UPDATE albums SET title=%s,year=%s,category=%s,description=%s,cover=%s WHERE id=%s' if DATABASE_URL else 'UPDATE albums SET title=?,year=?,category=?,description=?,cover=? WHERE id=?',params); c.commit(); c.close()
    if old and p != old['cover'] and old['cover']: del_file(old['cover'])
    flash('Album updated.', 'ok'); return redirect(url_for('admin_dash')+'#albums')

@app.post('/admin/album/<int:id>/photo')
@admin
def photo_add(id):
    p=save_upload('photo','csya/photos')
    if p:
        c=db(); params=(id,request.form.get('title',''),request.form.get('caption',''),p,datetime.now().isoformat(timespec='seconds'))
        execute(c,'INSERT INTO photos(album_id,title,caption,file,created_at) VALUES(%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO photos(album_id,title,caption,file,created_at) VALUES(?,?,?,?,?)',params); c.commit(); c.close()
    return redirect(url_for('admin_dash')+'#albums')

@app.post('/admin/photo/<int:id>/edit')
@admin
def photo_edit(id):
    old=row_by('photos', id); p=save_upload('photo','csya/photos') or (old['file'] if old else '')
    c=db(); params=(request.form.get('title',''),request.form.get('caption',''),p,id)
    execute(c,'UPDATE photos SET title=%s,caption=%s,file=%s WHERE id=%s' if DATABASE_URL else 'UPDATE photos SET title=?,caption=?,file=? WHERE id=?',params); c.commit(); c.close()
    if old and p != old['file'] and old['file']: del_file(old['file'])
    flash('Photo updated.', 'ok'); return redirect(url_for('admin_dash')+'#photos')

@app.post('/admin/photo/<int:id>/delete')
@admin
def photo_del(id):
    old=row_by('photos', id); delete_row('photos', id)
    if old and old['file']: del_file(old['file'])
    flash('Photo deleted.', 'ok'); return redirect(url_for('admin_dash')+'#photos')

@app.post('/admin/album/<int:id>/delete')
@admin
def album_del(id):
    c=db(); ps=execute(c,'SELECT file FROM photos WHERE album_id=%s' if DATABASE_URL else 'SELECT file FROM photos WHERE album_id=?',(id,)).fetchall(); a=execute(c,'SELECT cover FROM albums WHERE id=%s' if DATABASE_URL else 'SELECT cover FROM albums WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM photos WHERE album_id=%s' if DATABASE_URL else 'DELETE FROM photos WHERE album_id=?',(id,)); execute(c,'DELETE FROM albums WHERE id=%s' if DATABASE_URL else 'DELETE FROM albums WHERE id=?',(id,)); c.commit(); c.close(); [del_file(x['file']) for x in ps]; del_file(a['cover'] if a else ''); return redirect(url_for('admin_dash')+'#albums')

@app.post('/admin/event')
@admin
def event_add():
    p=save_upload('photo','csya/events'); c=db(); params=(request.form['title'],request.form.get('date',''),request.form.get('location',''),request.form.get('description',''),p)
    execute(c,'INSERT INTO events(title,date,location,description,photo) VALUES(%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO events(title,date,location,description,photo) VALUES(?,?,?,?,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#events')

@app.post('/admin/event/<int:id>/edit')
@admin
def event_edit(id):
    old=row_by('events', id); p=save_upload('photo','csya/events') or (old['photo'] if old else '')
    c=db(); params=(request.form['title'],request.form.get('date',''),request.form.get('location',''),request.form.get('description',''),p,id)
    execute(c,'UPDATE events SET title=%s,date=%s,location=%s,description=%s,photo=%s WHERE id=%s' if DATABASE_URL else 'UPDATE events SET title=?,date=?,location=?,description=?,photo=? WHERE id=?',params); c.commit(); c.close()
    if old and p != old['photo'] and old['photo']: del_file(old['photo'])
    flash('Event updated.', 'ok'); return redirect(url_for('admin_dash')+'#events')

@app.post('/admin/event/<int:id>/delete')
@admin
def event_del(id):
    c=db(); r=execute(c,'SELECT photo FROM events WHERE id=%s' if DATABASE_URL else 'SELECT photo FROM events WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM events WHERE id=%s' if DATABASE_URL else 'DELETE FROM events WHERE id=?',(id,)); c.commit(); c.close(); del_file(r['photo'] if r else ''); return redirect(url_for('admin_dash')+'#events')

@app.post('/admin/achievement')
@admin
def ach_add():
    p=save_upload('photo','csya/achievements'); c=db(); params=(request.form['title'],request.form.get('year',''),request.form.get('description',''),p)
    execute(c,'INSERT INTO achievements(title,year,description,photo) VALUES(%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO achievements(title,year,description,photo) VALUES(?,?,?,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#achievements')

@app.post('/admin/achievement/<int:id>/edit')
@admin
def ach_edit(id):
    old=row_by('achievements', id); p=save_upload('photo','csya/achievements') or (old['photo'] if old else '')
    c=db(); params=(request.form['title'],request.form.get('year',''),request.form.get('description',''),p,id)
    execute(c,'UPDATE achievements SET title=%s,year=%s,description=%s,photo=%s WHERE id=%s' if DATABASE_URL else 'UPDATE achievements SET title=?,year=?,description=?,photo=? WHERE id=?',params); c.commit(); c.close()
    if old and p != old['photo'] and old['photo']: del_file(old['photo'])
    flash('Achievement updated.', 'ok'); return redirect(url_for('admin_dash')+'#achievements')

@app.post('/admin/achievement/<int:id>/delete')
@admin
def ach_del(id):
    c=db(); r=execute(c,'SELECT photo FROM achievements WHERE id=%s' if DATABASE_URL else 'SELECT photo FROM achievements WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM achievements WHERE id=%s' if DATABASE_URL else 'DELETE FROM achievements WHERE id=?',(id,)); c.commit(); c.close(); del_file(r['photo'] if r else ''); return redirect(url_for('admin_dash')+'#achievements')

@app.post('/admin/video')
@admin
def video_add():
    p=save_upload('thumbnail','csya/videos'); c=db(); params=(request.form['title'],request.form['url'],request.form.get('year',''),request.form.get('description',''),p)
    execute(c,'INSERT INTO videos(title,url,year,description,thumbnail) VALUES(%s,%s,%s,%s,%s)' if DATABASE_URL else 'INSERT INTO videos(title,url,year,description,thumbnail) VALUES(?,?,?,?,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#videos')

@app.post('/admin/video/<int:id>/edit')
@admin
def video_edit(id):
    old=row_by('videos', id); p=save_upload('thumbnail','csya/videos') or (old['thumbnail'] if old else '')
    c=db(); params=(request.form['title'],request.form['url'],request.form.get('year',''),request.form.get('description',''),p,id)
    execute(c,'UPDATE videos SET title=%s,url=%s,year=%s,description=%s,thumbnail=%s WHERE id=%s' if DATABASE_URL else 'UPDATE videos SET title=?,url=?,year=?,description=?,thumbnail=? WHERE id=?',params); c.commit(); c.close()
    if old and p != old['thumbnail'] and old['thumbnail']: del_file(old['thumbnail'])
    flash('Video updated.', 'ok'); return redirect(url_for('admin_dash')+'#videos')

@app.post('/admin/video/<int:id>/delete')
@admin
def video_del(id):
    c=db(); r=execute(c,'SELECT thumbnail FROM videos WHERE id=%s' if DATABASE_URL else 'SELECT thumbnail FROM videos WHERE id=?',(id,)).fetchone(); execute(c,'DELETE FROM videos WHERE id=%s' if DATABASE_URL else 'DELETE FROM videos WHERE id=?',(id,)); c.commit(); c.close(); del_file(r['thumbnail'] if r else ''); return redirect(url_for('admin_dash')+'#videos')

@app.post('/admin/announcement')
@admin
def ann_add():
    c=db(); params=(request.form['title'],request.form['text'],datetime.now().isoformat(timespec='seconds'))
    execute(c,'INSERT INTO announcements(title,text,active,created_at) VALUES(%s,%s,1,%s)' if DATABASE_URL else 'INSERT INTO announcements(title,text,active,created_at) VALUES(?,?,1,?)',params); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#announcements')

@app.post('/admin/announcement/<int:id>/edit')
@admin
def ann_edit(id):
    c=db(); params=(request.form['title'],request.form['text'],int(request.form.get('active',1) or 0),id)
    execute(c,'UPDATE announcements SET title=%s,text=%s,active=%s WHERE id=%s' if DATABASE_URL else 'UPDATE announcements SET title=?,text=?,active=? WHERE id=?',params); c.commit(); c.close()
    flash('Announcement updated.', 'ok'); return redirect(url_for('admin_dash')+'#announcements')

@app.post('/admin/announcement/<int:id>/delete')
@admin
def ann_del(id):
    c=db(); execute(c,'DELETE FROM announcements WHERE id=%s' if DATABASE_URL else 'DELETE FROM announcements WHERE id=?',(id,)); c.commit(); c.close(); return redirect(url_for('admin_dash')+'#announcements')

@app.route('/members')
def members_page():
    c=db(); members=execute(c,'SELECT * FROM members ORDER BY sort_order,id DESC').fetchall(); c.close()
    return render_template('collection.html', kind='members', title='Our Committee', eyebrow='THE PEOPLE BEHIND THE MEMORIES', intro='Every member, every role, every chapter — all in one place.', items=members)

@app.route('/memories')
def memories_page():
    c=db(); albums=execute(c,'SELECT * FROM albums ORDER BY year DESC,id DESC').fetchall(); years=sorted({str(a['year']) for a in albums if a['year']}, reverse=True); c.close()
    return render_template('memories.html', albums=albums, years=years)

@app.route('/events')
def events_page():
    c=db(); events=execute(c,'SELECT * FROM events ORDER BY date DESC,id DESC').fetchall(); c.close()
    return render_template('collection.html', kind='events', title='Our Events', eyebrow='CELEBRATIONS & ACTIVITIES', intro='Every celebration and activity, preserved as part of our journey.', items=events)

@app.route('/achievements')
def achievements_page():
    c=db(); items=execute(c,'SELECT * FROM achievements ORDER BY year DESC,id DESC').fetchall(); c.close()
    return render_template('collection.html', kind='achievements', title='Our Achievements', eyebrow='PRIDE & PURPOSE', intro='Milestones that made our association stronger and our village prouder.', items=items)

@app.route('/videos')
def videos_page():
    c=db(); items=execute(c,'SELECT * FROM videos ORDER BY year DESC,id DESC').fetchall(); c.close()
    return render_template('collection.html', kind='videos', title='Our Videos', eyebrow='WATCH & REMEMBER', intro='Watch the moments that deserve to be remembered again and again.', items=items)

@app.route('/gallery/<int:album_id>')
def gallery(album_id):
    c=db(); album=execute(c,'SELECT * FROM albums WHERE id=%s' if DATABASE_URL else 'SELECT * FROM albums WHERE id=?',(album_id,)).fetchone(); photos=execute(c,'SELECT * FROM photos WHERE album_id=%s ORDER BY id DESC' if DATABASE_URL else 'SELECT * FROM photos WHERE album_id=? ORDER BY id DESC',(album_id,)).fetchall(); c.close()
    if not album: return redirect(url_for('home'))
    return render_template('gallery.html',album=album,photos=photos)

@app.route('/health')
def health(): return jsonify(ok=True, database='postgresql' if DATABASE_URL else 'sqlite', media='cloudinary' if CLOUDINARY_CONFIGURED else 'local')

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)),debug=True)
