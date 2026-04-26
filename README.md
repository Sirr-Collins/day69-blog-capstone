# 📝 Sir Collins Blog

A full-featured personal blog built with **Flask** and **Python**, deployed on **Render** with **PostgreSQL** and **Cloudinary** image hosting.

🌐 **Live site:** [sir-collins.onrender.com](https://sir-collins.onrender.com)

---

## ✨ Features

### Content
- Rich text blog posts powered by **CKEditor**
- Post **thumbnails** on the homepage index
- **Reading time** estimate per post
- **View counter** on every post
- **Tags** (comma-separated, filterable)
- **Search** posts by title or content
- **Pagination** — 5 posts per page
- **RSS feed** at `/feed.xml`

### Users & Auth
- User **registration** with **email confirmation** (itsdangerous timed tokens)
- Secure **login / logout** (Flask-Login)
- **Forgot password** flow with 30-minute reset link
- **Gravatar** profile images from email hash
- **User profile pages** with bio and post history
- **Brute-force protection** — login and register are rate-limited (flask-limiter)
- Passwords hashed with **PBKDF2-SHA256** (Werkzeug)

### Social
- **Like / unlike** posts (one like per user)
- **Threaded comments** with one level of replies
- **Comment deletion** by author or admin

### Admin
- First registered user (id=1) is automatically the **admin**
- **Admin-only** decorator protects create / edit / delete routes
- **Admin dashboard** — stats: total users, posts, comments, likes
- **Top posts** by view count
- **Drafts manager** — save posts without publishing
- **Direct image upload** via Cloudinary (persistent, survives redeploys)

### UI & UX
- **Dark mode** toggle — persisted in localStorage, no flash on load
- **SEO meta tags** + **Open Graph** tags on every post (controls social media previews)
- Responsive — works on mobile and desktop
- **Scroll-to-top** button
- **Flash messages** for all user actions

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask 2.3 |
| Database (production) | PostgreSQL (Render managed) |
| Database (local dev) | SQLite |
| ORM | SQLAlchemy 2.0 |
| Auth | Flask-Login, Werkzeug |
| Forms | Flask-WTF, WTForms |
| Email | Flask-Mail, itsdangerous |
| Image hosting | Cloudinary |
| Caching | flask-caching |
| Rate limiting | flask-limiter |
| Rich text | Flask-CKEditor |
| RSS | feedgen |
| Frontend | Bootstrap 5, Jinja2, custom CSS |
| Server | Gunicorn |
| Deployment | Render |

---

## 🚀 Running Locally

### 1. Clone the repo

```bash
git clone https://github.com/Sirr-Collins/day69-blog-capstone.git
cd day69-blog-capstone
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create a `.env` file

Create a file called `.env` in the project root:

```env
SECRET_KEY=your-long-random-secret-key
DB_URI=sqlite:///posts.db
MAIL_ADDRESS=your-gmail@gmail.com
PASSWORD_KEY=your-gmail-app-password
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```

> **Tip:** Generate a secure `SECRET_KEY` with:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

> **Note:** For local development without email, leave `MAIL_ADDRESS` blank — the app will auto-confirm registrations and show a flash message instead of crashing.

### 5. Run the app

```bash
python main.py
```

Visit [http://127.0.0.1:5001](http://127.0.0.1:5001)

The first user to register becomes the **admin** (user id=1).

---

## 🗄️ Database

### Local (SQLite)
SQLite is used automatically for local development. The database file is created at `instance/posts.db` on first run. Schema migrations are applied automatically at startup.

### Production (PostgreSQL)
Set `DB_URI` to your PostgreSQL connection string. The `migrate.py` script runs automatically before Gunicorn starts (via the `Procfile`) and applies all schema changes safely using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

---

## 🖼️ Image Uploads

Images uploaded through the admin post editor are stored on **Cloudinary** — a cloud CDN — and are permanent. They survive server restarts and redeployments.

To enable image uploads:
1. Create a free account at [cloudinary.com](https://cloudinary.com)
2. Copy your **Cloud Name**, **API Key**, and **API Secret** from the dashboard
3. Add them to your `.env` file (or Render environment variables)

Without Cloudinary configured, the image URL field still works — paste any public image URL.

---

## ☁️ Deploying to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New Web Service** → connect your repo
3. Set **Start Command** to: `python migrate.py; gunicorn main:app`
4. Create a **PostgreSQL** database on Render and copy the **Internal Database URL**
5. Set all environment variables in the Render **Environment** tab:

| Variable | Value |
|---|---|
| `SECRET_KEY` | Your generated secret key |
| `DB_URI` | Render PostgreSQL Internal URL |
| `MAIL_ADDRESS` | Your Gmail address |
| `PASSWORD_KEY` | Gmail App Password |
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `587` |
| `CLOUDINARY_CLOUD_NAME` | From Cloudinary dashboard |
| `CLOUDINARY_API_KEY` | From Cloudinary dashboard |
| `CLOUDINARY_API_SECRET` | From Cloudinary dashboard |

6. Deploy — the migration script runs automatically and the site goes live

---

## 📁 Project Structure

```
day69-blog-capstone/
├── main.py               # App factory, models, all routes
├── forms.py              # WTForms form classes
├── migrate.py            # PostgreSQL schema migration script
├── Procfile              # Render start command
├── requirements.txt      # Python dependencies
├── static/
│   ├── css/
│   │   ├── styles.css        # Base theme (Start Bootstrap Clean Blog)
│   │   └── blog-upgrades.css # Custom design layer (dark mode, cards, etc.)
│   ├── js/
│   │   └── scripts.js        # Navbar scroll behaviour
│   └── assets/
│       └── img/              # Static background images
└── templates/
    ├── header.html           # Nav, meta tags, dark mode init
    ├── footer.html           # Footer, scroll-to-top, dark mode JS
    ├── index.html            # Homepage — post list with search & pagination
    ├── post.html             # Single post — comments, likes, tags
    ├── make-post.html        # Create / edit post form
    ├── login.html            # Login form
    ├── register.html         # Registration form
    ├── forgot_password.html  # Password reset request
    ├── reset_password.html   # New password form
    ├── profile.html          # Public user profile
    ├── edit_profile.html     # Edit bio
    ├── admin_dashboard.html  # Admin stats and management
    ├── about.html            # About page
    ├── contact.html          # Contact form
    └── footer.html           # Footer partial
```

---

## 🔒 Security

- Passwords hashed with **PBKDF2-SHA256** — never stored in plain text
- **CSRF protection** on all forms via Flask-WTF
- **Rate limiting** on `/login` and `/register` — 10 requests/minute per IP
- **Email confirmation** required before login
- **Timed tokens** for email confirmation (1 hour) and password reset (30 minutes)
- Admin routes protected by custom `@admin_only` decorator
- Cloudinary API secret kept in environment variables — never in code
- `.env` file excluded from Git via `.gitignore`

---

## 📄 License

This project was built as a capstone project for the **100 Days of Code — Python Bootcamp**.  
Feel free to fork, study, and build on it.

---

*Built with Flask · Deployed on Render · Images on Cloudinary*
