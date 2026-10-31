"""Reset the local SQLite database to a clean state with exactly one admin.

Run from any directory: python scratch/reset_database.py
This permanently deletes student, teacher, subject, marks, and related activity data.
"""
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "database" / "students.db"

# Child/activity tables are cleared before parent records. Foreign keys are also
# temporarily disabled to safely handle schemas that differ between versions.
DATA_TABLES = [
    "answers", "replies", "doubt_likes", "answer_likes", "doubts",
    "teacher_student_replies", "teacher_student_messages", "student_ia_marks",
    "study_plans", "semester_history", "student_semesters", "placement_scores",
    "student_rankings", "ranking_history", "prediction_history",
    "students", "teachers", "subjects",
]

def main():
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    # Preserve one existing admin account, preferring ADMIN001.
    admin = cur.execute(
        "SELECT * FROM users WHERE UPPER(login_id)='ADMIN001' OR role='Admin' "
        "ORDER BY CASE WHEN UPPER(login_id)='ADMIN001' THEN 0 ELSE 1 END, id LIMIT 1"
    ).fetchone()

    for table in DATA_TABLES:
        exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if exists:
            cur.execute(f'DELETE FROM "{table}"')

    if admin:
        # Remove all accounts other than the chosen administrator, then normalize role.
        cur.execute("DELETE FROM users WHERE id != ?", (admin["id"],))
        cur.execute("UPDATE users SET role='Admin', login_id='ADMIN001' WHERE id=?", (admin["id"],))
    else:
        # Create the standard admin if the database has no admin account.
        from werkzeug.security import generate_password_hash
        cols = {r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
        required = ["user_id", "name", "email", "login_id", "password_hash", "role"]
        if not all(c in cols for c in required):
            raise RuntimeError("The users table does not have the expected columns.")
        cur.execute(
            "INSERT INTO users (user_id,name,email,login_id,password_hash,role,department) "
            "VALUES (?,?,?,?,?,?,?)",
            ("USR-001", "System Administrator", "admin@example.com", "ADMIN001",
             generate_password_hash("Rns@123"), "Admin", "ALL")
        )

    # Reset counters for cleared tables where supported.
    try:
        placeholders = ",".join("?" for _ in DATA_TABLES)
        cur.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})", DATA_TABLES)
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")

    admin_count = cur.execute("SELECT COUNT(*) FROM users WHERE role='Admin'").fetchone()[0]
    users_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    students_count = cur.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    teachers_count = cur.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
    conn.close()

    print(f"Database reset complete: {DB_PATH}")
    print(f"Admin accounts: {admin_count}; total user accounts: {users_count}")
    print(f"Student records: {students_count}; teacher records: {teachers_count}")
    if (admin_count, users_count, students_count, teachers_count) != (1, 1, 0, 0):
        raise SystemExit("Reset verification failed.")

if __name__ == "__main__":
    main()
