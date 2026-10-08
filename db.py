import os
import sqlite3

from flask import g
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get('REFUNDS_DB') or os.path.join(os.path.dirname(__file__), 'refunds.db')

SCHOOL_NAME = 'СОУ „Таки Даскало“ - Битола'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
    return db


def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('PRAGMA foreign_keys = ON')
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY,
                username        TEXT UNIQUE NOT NULL,
                password_hash   TEXT NOT NULL,
                role            TEXT NOT NULL DEFAULT 'user',
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS students (
                id              INTEGER PRIMARY KEY,
                last_name       TEXT NOT NULL,
                first_name      TEXT NOT NULL,
                parent_name     TEXT NOT NULL,
                class_name      TEXT,
                parent_embg     TEXT,
                bank_account    TEXT,
                notes           TEXT,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bills (
                id              INTEGER PRIMARY KEY,
                student_id      INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                bill_date       TEXT NOT NULL,
                amount          REAL NOT NULL,
                note            TEXT,
                year            INTEGER NOT NULL,
                month           INTEGER NOT NULL,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS month_payments (
                id                  INTEGER PRIMARY KEY,
                year                INTEGER NOT NULL,
                month               INTEGER NOT NULL,
                paid_at             TEXT NOT NULL,
                paid_by             TEXT NOT NULL,
                amount_at_payment   REAL NOT NULL,
                student_count       INTEGER NOT NULL,
                bill_count          INTEGER NOT NULL,
                UNIQUE (year, month)
            );

            CREATE INDEX IF NOT EXISTS idx_bills_student ON bills(student_id);
            CREATE INDEX IF NOT EXISTS idx_bills_period ON bills(year, month);
        ''')
        _relax_students(conn)
        _add_column(conn, 'students', 'class_name', 'TEXT')
        count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if count == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                ('admin', generate_password_hash('admin123'))
            )
            print('  Default admin created — username: admin  password: admin123')
            print('  Change the password after first login.')
        conn.commit()


def _column_required(conn, table, column):
    for row in conn.execute(f'PRAGMA table_info({table})'):
        if row[1] == column:
            return bool(row[3])
    return False


def _relax_students(conn):
    """Make EMBG and bank account optional without deleting any saved row."""
    if not _column_required(conn, 'students', 'parent_embg') and not _column_required(conn, 'students', 'bank_account'):
        return
    students_before = conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    bills_before = conn.execute('SELECT COUNT(*) FROM bills').fetchone()[0]
    conn.execute('PRAGMA foreign_keys = OFF')
    conn.execute('BEGIN')
    conn.execute('''
        CREATE TABLE students_new (
            id              INTEGER PRIMARY KEY,
            last_name       TEXT NOT NULL,
            first_name      TEXT NOT NULL,
            parent_name     TEXT NOT NULL,
            parent_embg     TEXT,
            bank_account    TEXT,
            notes           TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        INSERT INTO students_new
            (id, last_name, first_name, parent_name, parent_embg, bank_account, notes, created_at)
        SELECT id, last_name, first_name, parent_name, parent_embg, bank_account, notes, created_at
        FROM students
    ''')
    copied = conn.execute('SELECT COUNT(*) FROM students_new').fetchone()[0]
    if copied != students_before:
        conn.execute('ROLLBACK')
        conn.execute('DROP TABLE IF EXISTS students_new')
        conn.execute('PRAGMA foreign_keys = ON')
        raise RuntimeError('Student copy failed. Nothing was deleted.')
    conn.execute('DROP TABLE students')
    conn.execute('ALTER TABLE students_new RENAME TO students')
    bills_after = conn.execute('SELECT COUNT(*) FROM bills').fetchone()[0]
    students_after = conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    if bills_after != bills_before or students_after != students_before:
        conn.execute('ROLLBACK')
        conn.execute('PRAGMA foreign_keys = ON')
        raise RuntimeError('Saved rows changed during the update. Nothing was committed.')
    conn.execute('COMMIT')
    conn.execute('PRAGMA foreign_keys = ON')


def _add_column(conn, table, column, definition):
    cols = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
    if column not in cols:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
