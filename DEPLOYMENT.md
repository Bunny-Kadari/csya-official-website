# CSYA production deployment

## Local

Leave `DATABASE_URL` and Cloudinary variables blank. The app uses SQLite + local uploads for development.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 app.py
```

Open `http://127.0.0.1:5000`.

Admin: `/login` — name `teamcsya`, password `csya123`.

## Render production

Use one Render Web Service + one Render PostgreSQL database.

Web Service:
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

Environment variables:
- `SECRET_KEY` = a long random value
- `ADMIN_NAME` = your admin name
- `ADMIN_PASSWORD` = your admin password
- `DATABASE_URL` = Render PostgreSQL connection string
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

For real production use, Cloudinary is recommended for uploaded images because the web service filesystem should not be treated as permanent storage.

The app automatically creates the PostgreSQL tables on first startup. Admin changes are stored in PostgreSQL, and uploaded images go to Cloudinary when its credentials are configured.
