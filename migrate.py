"""
migrate.py — Runs automatically on Render before the web server starts.
Safe to run multiple times — every operation checks before acting.

Handles:
  - Adding new columns to existing tables (ALTER TABLE ... ADD COLUMN IF NOT EXISTS)
  - Creating new tables (CREATE TABLE IF NOT EXISTS)
  - Pre-confirming existing users so they aren't locked out
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.getenv("DB_URI")

if not DB_URI:
    print("❌  DB_URI not set — skipping migration")
    sys.exit(0)

# SQLite doesn't need this script (handled inline in main.py)
if DB_URI.startswith("sqlite"):
    print("SQLite detected — skipping PostgreSQL migration")
    sys.exit(0)

print("🔄  Running database migration...")

try:
    conn = psycopg2.connect(DB_URI)
    conn.autocommit = True
    cur = conn.cursor()

    # ── blog_posts: new columns ───────────────────────────────────────────────
    cur.execute("""
        ALTER TABLE blog_posts
        ADD COLUMN IF NOT EXISTS views INTEGER DEFAULT 0
    """)
    print("  ✔  blog_posts.views")

    cur.execute("""
        ALTER TABLE blog_posts
        ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT TRUE
    """)
    # Make sure existing posts are published so nothing disappears
    cur.execute("""
        UPDATE blog_posts SET is_published = TRUE WHERE is_published IS NULL
    """)
    print("  ✔  blog_posts.is_published")

    # ── users: new columns ────────────────────────────────────────────────────
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS bio TEXT
    """)
    print("  ✔  users.bio")

    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_confirmed BOOLEAN DEFAULT FALSE
    """)
    # Pre-confirm ALL existing users so no one is locked out after the upgrade
    cur.execute("""
        UPDATE users SET is_confirmed = TRUE WHERE is_confirmed IS NULL OR is_confirmed = FALSE
    """)
    print("  ✔  users.is_confirmed  (all existing users pre-confirmed)")

    # ── comments: threaded replies ────────────────────────────────────────────
    cur.execute("""
        ALTER TABLE comments
        ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES comments(id)
    """)
    print("  ✔  comments.parent_id")

    # ── New tables ────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id   SERIAL PRIMARY KEY,
            name VARCHAR(50) NOT NULL UNIQUE
        )
    """)
    print("  ✔  tags table")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS post_tags (
            post_id INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
            tag_id  INTEGER NOT NULL REFERENCES tags(id)       ON DELETE CASCADE,
            PRIMARY KEY (post_id, tag_id)
        )
    """)
    print("  ✔  post_tags table")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id      SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id)      ON DELETE CASCADE,
            post_id INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE
        )
    """)
    print("  ✔  likes table")

    cur.close()
    conn.close()
    print("✅  Migration complete — database is up to date")

except Exception as e:
    print(f"❌  Migration failed: {e}")
    # Don't exit with error code — let the web server start anyway
    # so you can diagnose via Render logs
    sys.exit(0)
