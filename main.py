import os
import re
import math
import smtplib
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, abort, render_template, redirect, url_for,
                   flash, request, Response)
from flask_bootstrap import Bootstrap5
from flask_caching import Cache
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from feedgen.feed import FeedGenerator
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from sqlalchemy import Integer, String, Text, Boolean, Table, Column, ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
from forms import (CreatePostForm, RegisterForm, LoginForm,
                   CommentForm, UserProfileForm, ResetRequestForm, ResetPasswordForm)

# ─── App Setup ────────────────────────────────────────────────────────────────

load_dotenv()
app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev-only-insecure-key")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DB_URI", "sqlite:///blog.db")

# Flask-Mail — for email confirmation and password reset
app.config['MAIL_SERVER']   = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config['MAIL_PORT']     = int(os.getenv("MAIL_PORT", 587))
app.config['MAIL_USE_TLS']  = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_ADDRESS")
app.config['MAIL_PASSWORD'] = os.getenv("PASSWORD_KEY")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_ADDRESS")

# Cloudinary config — images stored permanently in the cloud
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB limit
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure     = True
)

# Flask extensions
ckeditor = CKEditor(app)
Bootstrap5(app)

# Rate limiter — brute-force protection on auth routes
limiter = Limiter(get_remote_address, app=app, default_limits=[])
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Cache — homepage post list cached for 60 seconds
if Cache:
    cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 60})
else:
    # Stub cache object so cache.clear() calls don't crash
    class _NoCache:
        def clear(self): pass
        def get(self, k): return None
        def set(self, k, v, timeout=None): pass
    cache = _NoCache()

MAIL_ADDRESS = os.getenv("MAIL_ADDRESS")
MAIL_APP_PW  = os.getenv("PASSWORD_KEY")

# ─── Database ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Many-to-many association table: BlogPost ↔ Tag
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("blog_posts.id"), primary_key=True),
    Column("tag_id",  Integer, ForeignKey("tags.id"),       primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id:       Mapped[int] = mapped_column(Integer, primary_key=True)
    name:     Mapped[str] = mapped_column(String(100), nullable=False)
    email:    Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(256))
    # NEW: optional bio shown on user profile page
    bio:           Mapped[str]  = mapped_column(Text,    nullable=True)
    is_confirmed:  Mapped[bool] = mapped_column(Boolean, default=False)  # email confirmation

    posts    = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment",  back_populates="comment_author")
    likes    = relationship("Like",     back_populates="user")


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id:        Mapped[int]  = mapped_column(Integer,      primary_key=True)
    author_id: Mapped[int]  = mapped_column(Integer,      db.ForeignKey("users.id"))
    title:     Mapped[str]  = mapped_column(String(250),  unique=True,  nullable=False)
    subtitle:  Mapped[str]  = mapped_column(String(250),                nullable=False)
    date:      Mapped[str]  = mapped_column(String(250),                nullable=False)
    body:      Mapped[str]  = mapped_column(Text,                       nullable=False)
    img_url:   Mapped[str]  = mapped_column(String(500),                nullable=False)
    views:     Mapped[int]  = mapped_column(Integer,      default=0)          # NEW: view counter
    is_published: Mapped[bool] = mapped_column(Boolean,   default=True)       # NEW: draft toggle

    author   = relationship("User",    back_populates="posts")
    comments = relationship("Comment", back_populates="parent_post",
                            cascade="all, delete-orphan")
    tags     = relationship("Tag",     secondary=post_tags, back_populates="posts")  # NEW
    likes    = relationship("Like",    back_populates="post",
                            cascade="all, delete-orphan")                     # NEW

    @property
    def reading_time(self):
        """Estimate reading time: strip HTML tags, count words, assume 200 wpm."""
        plain = re.sub(r'<[^>]+>', '', self.body)
        word_count = len(plain.split())
        minutes = max(1, math.ceil(word_count / 200))
        return minutes


class Tag(db.Model):
    """NEW: Tags with many-to-many relationship to BlogPost."""
    __tablename__ = "tags"
    id:   Mapped[int] = mapped_column(Integer,     primary_key=True)
    name: Mapped[str] = mapped_column(String(50),  unique=True, nullable=False)

    posts = relationship("BlogPost", secondary=post_tags, back_populates="tags")


class Comment(db.Model):
    __tablename__ = "comments"
    id:        Mapped[int] = mapped_column(Integer, primary_key=True)
    text:      Mapped[str] = mapped_column(Text,    nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    post_id:   Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    # NEW: self-referential FK for threaded replies
    parent_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("comments.id"),
                                           nullable=True)

    comment_author = relationship("User",    back_populates="comments")
    parent_post    = relationship("BlogPost", back_populates="comments")
    replies        = relationship("Comment", backref=db.backref("parent", remote_side=[id]),
                                  cascade="all, delete-orphan")   # NEW: nested replies


class Like(db.Model):
    """NEW: Tracks which user liked which post (one like per user per post)."""
    __tablename__ = "likes"
    id:      Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))

    user = relationship("User",     back_populates="likes")
    post = relationship("BlogPost", back_populates="likes")


# ─── Gravatar ─────────────────────────────────────────────────────────────────

gravatar = Gravatar(app, size=100, rating='g', default='retro',
                    force_default=False, force_lower=False,
                    use_ssl=False, base_url=None)

# ─── Create tables ────────────────────────────────────────────────────────────

def _get_sqlite_path():
    """
    Resolve the absolute path to the SQLite file regardless of OS or
    working directory.  Flask always puts instance-relative SQLite files
    inside  <project>/instance/  so we derive the path the same way.
    """
    import os as _os
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if not uri.startswith('sqlite'):
        return None          # PostgreSQL / MySQL — no migration needed here
    # Strip the scheme.  sqlite:///foo.db  →  foo.db  (relative to instance/)
    #                    sqlite:////abs/path  →  /abs/path  (absolute)
    path = uri[len('sqlite:///'):]
    if not _os.path.isabs(path):
        # Relative path — Flask places it in the instance folder
        path = _os.path.join(app.instance_path, path)
    return _os.path.normpath(path)


with app.app_context():
    # Ensure the instance folder exists before db.create_all() writes to it
    import os as _os
    _os.makedirs(app.instance_path, exist_ok=True)
    db.create_all()

    # Inline migration — safely add new columns to existing databases
    import sqlite3 as _sqlite3
    _db_path = _get_sqlite_path()
    if _db_path:
        try:
            _conn = _sqlite3.connect(_db_path)
            _cur  = _conn.cursor()
            def _col_exists(table, col):
                _cur.execute(f"PRAGMA table_info({table})")
                return any(r[1] == col for r in _cur.fetchall())
            if not _col_exists("blog_posts", "views"):
                _cur.execute("ALTER TABLE blog_posts ADD COLUMN views INTEGER DEFAULT 0")
            if not _col_exists("blog_posts", "is_published"):
                _cur.execute("ALTER TABLE blog_posts ADD COLUMN is_published BOOLEAN DEFAULT 1")
                _cur.execute("UPDATE blog_posts SET is_published = 1 WHERE is_published IS NULL")
            if not _col_exists("users", "bio"):
                _cur.execute("ALTER TABLE users ADD COLUMN bio TEXT")
            if not _col_exists("comments", "parent_id"):
                _cur.execute("ALTER TABLE comments ADD COLUMN parent_id INTEGER REFERENCES comments(id)")
            if not _col_exists("users", "is_confirmed"):
                _cur.execute("ALTER TABLE users ADD COLUMN is_confirmed BOOLEAN DEFAULT 0")
                _cur.execute("UPDATE users SET is_confirmed = 1 WHERE id = 1")
            _conn.commit()
            _conn.close()
        except Exception as _e:
            import logging
            logging.warning(f"DB migration: {_e}")

    # Print the exact file path so you can confirm the right DB is being used
    if _db_path:
        print(f"[DB] {_db_path}")

# ─── Auth ─────────────────────────────────────────────────────────────────────

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)  # Returns None if not found (safe); get_or_404 was aborting 404


# Make csrf_token available in ALL templates automatically
# Needed for raw HTML forms that don't use {{ form.hidden_tag() }}
from flask_wtf.csrf import generate_csrf

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)


def admin_only(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return abort(401)
        if current_user.id != 1:
            return abort(403)
        return function(*args, **kwargs)
    return decorated_function


# ─── Helpers ──────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file):
    """Upload a file to Cloudinary and return the secure URL."""
    # Check credentials are configured before attempting upload
    if not os.getenv("CLOUDINARY_CLOUD_NAME"):
        print("[Cloudinary] ERROR: CLOUDINARY_CLOUD_NAME not set in environment")
        return None
    try:
        result = cloudinary.uploader.upload(
            file,
            folder="blog_posts",
            transformation=[{"quality": "auto", "fetch_format": "auto"}]
        )
        url = result.get("secure_url")
        print(f"[Cloudinary] Upload successful: {url}")
        return url
    except Exception as e:
        print(f"[Cloudinary] Upload FAILED: {e}")
        return None


def _parse_tags(tag_string):
    """Turn 'python, flask, web' into a list of Tag objects, creating missing ones."""
    tags = []
    for name in {t.strip().lower() for t in tag_string.split(',') if t.strip()}:
        tag = db.session.execute(db.select(Tag).where(Tag.name == name)).scalar()
        if not tag:
            tag = Tag(name=name)
            db.session.add(tag)
        tags.append(tag)
    return tags


# ─── Routes: Auth ─────────────────────────────────────────────────────────────

@app.route('/register', methods=["GET", "POST"])
@limiter.limit("10 per minute")
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        result = db.session.execute(db.select(User).where(User.email == form.email.data))
        if result.scalar():
            flash("You've already signed up with that email. Please login.")
            return redirect(url_for('login'))
        new_user = User(
            name=form.name.data,
            email=form.email.data,
            password=generate_password_hash(form.password.data,
                                            method='pbkdf2:sha256', salt_length=8)
        )
        db.session.add(new_user)
        db.session.commit()
        # Send email confirmation before logging in
        try:
            _send_confirmation_email(new_user)
            flash("Account created! Please check your email to confirm your address before logging in.")
        except Exception:
            # Email failed (e.g. MAIL_ADDRESS not configured) — still allow login
            # Mark as confirmed so the user isn't locked out during development
            new_user.is_confirmed = True
            db.session.commit()
            flash("Account created! (Email confirmation skipped — check MAIL_ADDRESS in .env)")
        return redirect(url_for('login'))
    return render_template("register.html", form=form, current_user=current_user)


@app.route('/login', methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        user = db.session.execute(
            db.select(User).where(User.email == login_form.email.data)
        ).scalar()
        if not user:
            flash("Email not found.")
            return redirect(url_for('register'))
        if not check_password_hash(user.password, login_form.password.data):
            flash("Incorrect email or password.")
            return redirect(url_for('login'))
        if not user.is_confirmed:
            flash("Please confirm your email address before logging in. Check your inbox.")
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('get_all_posts'))
    return render_template("login.html", login_form=login_form, current_user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))



# ─── Routes: Email Confirmation & Password Reset ──────────────────────────────

def _send_confirmation_email(user):
    token = serializer.dumps(user.email, salt="email-confirm")
    link  = url_for("confirm_email", token=token, _external=True)
    msg   = Message("Confirm your email — Collins's Blog", recipients=[user.email])
    msg.body = (
        f"Hi {user.name},\n\n"
        f"Thanks for registering! Please confirm your email address by clicking the link below:\n\n"
        f"{link}\n\n"
        f"This link expires in 1 hour.\n\n"
        f"If you did not register, you can safely ignore this email."
    )
    mail.send(msg)


@app.route("/confirm/<token>")
def confirm_email(token):
    try:
        email = serializer.loads(token, salt="email-confirm", max_age=3600)
    except SignatureExpired:
        flash("Confirmation link has expired. Please register again.")
        return redirect(url_for("register"))
    except BadSignature:
        flash("Invalid confirmation link.")
        return redirect(url_for("register"))
    user = db.session.execute(db.select(User).where(User.email == email)).scalar()
    if not user:
        flash("User not found.")
        return redirect(url_for("register"))
    if user.is_confirmed:
        flash("Account already confirmed. Please log in.")
    else:
        user.is_confirmed = True
        db.session.commit()
        flash("Email confirmed! You can now log in.")
    return redirect(url_for("login"))


@app.route("/resend-confirmation")
@login_required
def resend_confirmation():
    if current_user.is_confirmed:
        flash("Your account is already confirmed.")
        return redirect(url_for("get_all_posts"))
    _send_confirmation_email(current_user)
    flash("A new confirmation email has been sent. Please check your inbox.")
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    form = ResetRequestForm()
    if form.validate_on_submit():
        user = db.session.execute(
            db.select(User).where(User.email == form.email.data)
        ).scalar()
        # Always show success message — don't reveal whether email exists (security)
        if user:
            try:
                token = serializer.dumps(user.email, salt="password-reset")
                link  = url_for("reset_password", token=token, _external=True)
                msg   = Message("Reset your password — Collins's Blog", recipients=[user.email])
                msg.body = (
                    f"Hi {user.name},\n\n"
                    f"Click the link below to reset your password:\n\n"
                    f"{link}\n\n"
                    f"This link expires in 30 minutes.\n\n"
                    f"If you did not request this, ignore this email."
                )
                mail.send(msg)
            except Exception:
                pass  # Always show the same message regardless
        flash("If that email is registered, a reset link has been sent.")
        return redirect(url_for("login"))
    return render_template("forgot_password.html", form=form, current_user=current_user)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = serializer.loads(token, salt="password-reset", max_age=1800)
    except SignatureExpired:
        flash("Reset link has expired. Please request a new one.")
        return redirect(url_for("forgot_password"))
    except BadSignature:
        flash("Invalid reset link.")
        return redirect(url_for("forgot_password"))
    user = db.session.execute(db.select(User).where(User.email == email)).scalar()
    if not user:
        flash("User not found.")
        return redirect(url_for("forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data,
                                               method="pbkdf2:sha256", salt_length=8)
        db.session.commit()
        flash("Password reset successful! You can now log in.")
        return redirect(url_for("login"))
    return render_template("reset_password.html", form=form,
                           current_user=current_user, token=token)


# ─── Routes: Posts ────────────────────────────────────────────────────────────

@app.route('/')
def get_all_posts():
    page     = request.args.get('page', 1, type=int)
    search_q = request.args.get('q', '').strip()
    per_page = 5

    # Only show published posts on the public homepage
    query = db.select(BlogPost).where(BlogPost.is_published == True).order_by(BlogPost.id.desc())

    # NEW: Search by title or body content
    if search_q:
        like = f"%{search_q}%"
        query = query.where(
            db.or_(BlogPost.title.ilike(like), BlogPost.body.ilike(like))
        )

    # NEW: Filter by tag
    tag_filter = request.args.get('tag', '').strip()
    if tag_filter:
        query = query.join(BlogPost.tags).where(Tag.name == tag_filter.lower())

    # (already ordered above)
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

    # Top 8 tags by number of published posts — keeps the cloud focused
    from sqlalchemy import func as _func
    all_tags = db.session.execute(
        db.select(Tag)
        .join(Tag.posts)
        .where(BlogPost.is_published == True)
        .group_by(Tag.id)
        .order_by(_func.count(BlogPost.id).desc())
        .limit(8)
    ).scalars().all()
    return render_template("index.html",
                           all_posts=pagination.items,
                           pagination=pagination,
                           search_q=search_q,
                           tag_filter=tag_filter,
                           all_tags=all_tags,
                           current_user=current_user)


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)

    # NEW: Increment view counter on every visit
    requested_post.views += 1
    db.session.commit()

    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.")
            return redirect(url_for('login'))

        parent_id = request.form.get('parent_id', type=int)  # NEW: reply support
        new_comment = Comment(
            text=comment_form.comment_text.data,
            comment_author=current_user,
            parent_post=requested_post,
            parent_id=parent_id,
        )
        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for('show_post', post_id=post_id))

    # Only top-level comments (parent_id IS NULL) shown at root; replies nested inside
    top_comments = db.session.execute(
        db.select(Comment)
        .where(Comment.post_id == post_id, Comment.parent_id == None)
    ).scalars().all()

    # NEW: check if current user has already liked this post
    user_liked = False
    if current_user.is_authenticated:
        user_liked = db.session.execute(
            db.select(Like).where(Like.user_id == current_user.id,
                                  Like.post_id == post_id)
        ).scalar() is not None

    return render_template("post.html",
                           post=requested_post,
                           current_user=current_user,
                           comment_form=comment_form,
                           top_comments=top_comments,
                           user_liked=user_liked)


# NEW: Like / unlike a post
@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    existing = db.session.execute(
        db.select(Like).where(Like.user_id == current_user.id,
                              Like.post_id == post_id)
    ).scalar()
    if existing:
        db.session.delete(existing)   # toggle off
    else:
        db.session.add(Like(user_id=current_user.id, post_id=post_id))
    db.session.commit()
    return redirect(url_for('show_post', post_id=post_id))


# NEW: Delete a comment (author or admin)
@app.route("/delete-comment/<int:comment_id>", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    post_id = comment.post_id
    if current_user.id != comment.author_id and current_user.id != 1:
        abort(403)
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for('show_post', post_id=post_id))


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    cache.clear()  # clear cached pages when content changes
    form = CreatePostForm()
    if form.validate_on_submit():
        # Handle image upload OR URL
        img_url = form.img_url.data or ''
        file = request.files.get('img_file')
        if file and file.filename and allowed_file(file.filename):
            # Upload to Cloudinary — persists across deploys
            cloudinary_url = upload_to_cloudinary(file)
            if cloudinary_url:
                img_url = cloudinary_url
            else:
                flash("Image upload failed — please try a URL instead.")

        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=img_url,
            author=current_user,
            date=date.today().strftime("%B %d, %Y"),
            is_published=form.is_published.data,   # NEW: draft toggle
            tags=_parse_tags(form.tags.data),       # NEW: tags
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    cache.clear()  # clear all cached pages
    post = db.get_or_404(BlogPost, post_id)
    # Use data dict so BooleanField pre-populates correctly on GET
    # (passing kwargs directly to WTForms doesn't reliably work for BooleanField)
    edit_form = CreatePostForm(
        data={
            'title':        post.title,
            'subtitle':     post.subtitle,
            'img_url':      post.img_url,
            'body':         post.body,
            'is_published': post.is_published,
            'tags':         ', '.join(t.name for t in post.tags),
        }
    )
    if edit_form.validate_on_submit():
        file = request.files.get('img_file')
        if file and file.filename and allowed_file(file.filename):
            # Upload to Cloudinary — persists across deploys
            cloudinary_url = upload_to_cloudinary(file)
            if cloudinary_url:
                post.img_url = cloudinary_url
            else:
                flash("Image upload failed — existing image kept.")
        else:
            post.img_url = edit_form.img_url.data

        post.title        = edit_form.title.data
        post.subtitle     = edit_form.subtitle.data
        post.body         = edit_form.body.data
        post.author       = current_user
        post.is_published = edit_form.is_published.data
        post.tags         = _parse_tags(edit_form.tags.data)
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    cache.clear()  # clear all cached pages
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


# ─── Routes: User Profiles ────────────────────────────────────────────────────

@app.route("/user/<int:user_id>")
def user_profile(user_id):
    """NEW: Public profile showing user's posts and bio."""
    user  = db.get_or_404(User, user_id)
    posts = db.session.execute(
        db.select(BlogPost)
        .where(BlogPost.author_id == user_id, BlogPost.is_published == True)
        .order_by(BlogPost.id.desc())
    ).scalars().all()
    return render_template("profile.html", profile_user=user,
                           posts=posts, current_user=current_user)


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    """NEW: Let any logged-in user edit their own bio."""
    form = UserProfileForm(bio=current_user.bio)
    if form.validate_on_submit():
        current_user.bio = form.bio.data
        db.session.commit()
        flash("Profile updated!")
        return redirect(url_for('user_profile', user_id=current_user.id))
    return render_template("edit_profile.html", form=form, current_user=current_user)


# ─── Routes: Admin Dashboard ──────────────────────────────────────────────────

@app.route("/admin/dashboard")
@admin_only
def admin_dashboard():
    """NEW: Admin overview — users, posts, comments, drafts."""
    total_users    = db.session.execute(db.select(db.func.count(User.id))).scalar()
    total_posts    = db.session.execute(db.select(db.func.count(BlogPost.id))).scalar()
    total_comments = db.session.execute(db.select(db.func.count(Comment.id))).scalar()
    total_likes    = db.session.execute(db.select(db.func.count(Like.id))).scalar()
    drafts = db.session.execute(
        db.select(BlogPost).where(BlogPost.is_published == False)
    ).scalars().all()
    recent_users = db.session.execute(
        db.select(User).order_by(User.id.desc()).limit(10)
    ).scalars().all()
    top_posts = db.session.execute(
        db.select(BlogPost).where(BlogPost.is_published == True)
        .order_by(BlogPost.views.desc()).limit(5)
    ).scalars().all()
    return render_template("admin_dashboard.html",
                           total_users=total_users,
                           total_posts=total_posts,
                           total_comments=total_comments,
                           total_likes=total_likes,
                           drafts=drafts,
                           recent_users=recent_users,
                           top_posts=top_posts,
                           current_user=current_user)


# ─── Routes: RSS Feed ─────────────────────────────────────────────────────────

@app.route("/feed.xml")
def rss_feed():
    """NEW: RSS feed of the 20 most recent published posts."""
    if not FeedGenerator:
        return Response("RSS feed unavailable. Install feedgen: pip install feedgen",
                        mimetype="text/plain", status=503)
    fg = FeedGenerator()
    fg.id(request.url_root)
    fg.title("Collins's Blog")
    fg.link(href=request.url_root, rel='alternate')
    fg.link(href=request.host_url.rstrip('/') + url_for('rss_feed'), rel='self')
    fg.language('en')
    fg.description("A collection of random musings.")

    posts = db.session.execute(
        db.select(BlogPost)
        .where(BlogPost.is_published == True)
        .order_by(BlogPost.id.desc()).limit(20)
    ).scalars().all()

    for post in posts:
        fe = fg.add_entry()
        fe.id(url_for('show_post', post_id=post.id, _external=True))
        fe.title(post.title)
        fe.summary(post.subtitle)
        fe.link(href=url_for('show_post', post_id=post.id, _external=True))
        fe.author({'name': post.author.name})

    return Response(fg.rss_str(pretty=True), mimetype='application/rss+xml')


# ─── Routes: Static Pages ─────────────────────────────────────────────────────

@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        data = request.form
        send_email(data["name"], data["email"], data["phone"], data["message"])
        return render_template("contact.html", msg_sent=True, current_user=current_user)
    return render_template("contact.html", msg_sent=False, current_user=current_user)


def send_email(name, email, phone, message):
    email_message = (f"Subject:New Message\n\n"
                     f"Name: {name}\nEmail: {email}\nPhone: {phone}\nMessage: {message}")
    with smtplib.SMTP("smtp.gmail.com", port=587) as connection:
        connection.starttls()
        connection.login(MAIL_ADDRESS, MAIL_APP_PW)
        connection.sendmail(from_addr=MAIL_ADDRESS, to_addrs=MAIL_ADDRESS, msg=email_message)


# ─── Run ──────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    app.run(debug=True, port=5001)
