"""Database layer for RealityCheck AI (SQLite, no ORM, parameterized SQL only)."""
import os
import sqlite3
from pathlib import Path

from flask import g

BASE_DIR = Path(__file__).resolve().parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_text      TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    verdict         TEXT NOT NULL DEFAULT 'Pending',
    confidence      REAL,
    explanation     TEXT,
    retrieval_mode  TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL UNIQUE,
    name   TEXT NOT NULL,
    tier   INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
    notes  TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id         INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    source_name      TEXT NOT NULL,
    url              TEXT NOT NULL,
    domain           TEXT NOT NULL,
    snippet          TEXT NOT NULL,
    stance           TEXT NOT NULL CHECK (stance IN ('SUPPORTS', 'REFUTES', 'NEUTRAL')),
    reason           TEXT,
    credibility_tier INTEGER NOT NULL,
    published_date   TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id   INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    helpful    INTEGER NOT NULL CHECK (helpful IN (0, 1)),
    comment    TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_claims_verdict ON claims(verdict);
"""

# (domain, display name, tier, notes)
# Tier 1 = official body or major fact-checking organisation
# Tier 2 = reputable news, encyclopaedia, university or science publisher
# Tier 3 = any other site (default for unknown domains)
SEED_SOURCES = [
    ("nasa.gov", "NASA", 1, "US space agency"),
    ("esa.int", "European Space Agency", 1, "Space agency"),
    ("who.int", "World Health Organization", 1, "UN health agency"),
    ("noaa.gov", "NOAA", 1, "US weather and ocean agency"),
    ("nih.gov", "US National Institutes of Health", 1, "Medical research agency"),
    ("un.org", "United Nations", 1, "Intergovernmental organisation"),
    ("snopes.com", "Snopes", 1, "Long-running fact-checking site"),
    ("politifact.com", "PolitiFact", 1, "IFCN-signatory fact-checker"),
    ("factcheck.org", "FactCheck.org", 1, "Non-partisan fact-checker"),
    ("science.feedback.org", "Science Feedback", 1, "Science-claim fact-checker"),
    ("reuters.com", "Reuters", 2, "News agency"),
    ("apnews.com", "Associated Press", 2, "News agency"),
    ("bbc.com", "BBC", 2, "Public broadcaster"),
    ("britannica.com", "Encyclopaedia Britannica", 2, "Editor-reviewed encyclopaedia"),
    ("wikipedia.org", "Wikipedia", 2, "Open encyclopaedia; check cited references"),
    ("scientificamerican.com", "Scientific American", 2, "Science magazine"),
    ("nature.com", "Nature", 2, "Peer-reviewed journals"),
    ("nationalgeographic.com", "National Geographic", 2, "Science and geography publisher"),
    ("education.nationalgeographic.org", "National Geographic Education", 2, "Educational resource"),
    ("physicstoday.aip.org", "Physics Today", 2, "American Institute of Physics magazine"),
    ("smithsonianmag.com", "Smithsonian Magazine", 2, "Museum-backed magazine"),
    ("askanexpert.asu.edu", "Arizona State University", 2, "University outreach"),
    ("livescience.com", "Live Science", 3, "Popular science site"),
    ("popsci.com", "Popular Science", 3, "Popular science magazine"),
    ("sciencefocus.com", "BBC Science Focus", 3, "Popular science magazine"),
    ("psychologytoday.com", "Psychology Today", 3, "Popular psychology site"),
    ("mentalfloss.com", "Mental Floss", 3, "General-interest site"),
    ("starwalk.space", "Star Walk", 3, "Astronomy app blog"),
    ("spacecentre.nz", "Space Place (NZ)", 3, "Science centre FAQ"),
    ("guinnessworldrecords.com", "Guinness World Records", 3, "Records organisation"),
]


def db_path():
    return os.environ.get("RC_DB", str(BASE_DIR / "data" / "realitycheck.db"))


def connect():
    path = db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """One connection per request, stored on flask.g."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    """Create tables and seed the trusted-source list (idempotent)."""
    conn = connect()
    conn.executescript(SCHEMA)
    for domain, name, tier, notes in SEED_SOURCES:
        conn.execute(
            "INSERT OR IGNORE INTO sources(domain, name, tier, notes) VALUES (?,?,?,?)",
            (domain, name, tier, notes),
        )
    conn.commit()
    conn.close()
