"""
Database Service - Dual SQLite & MySQL support with schema auto-migration
"""
import os
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'students.db')

DEFAULT_DEMO_PASSWORD = "Rns@123"

def get_db_connection():
    use_mysql = os.environ.get('USE_MYSQL', 'false').lower() == 'true'
    if use_mysql:
        try:
            import mysql.connector
            conn = mysql.connector.connect(
                host=os.environ.get('MYSQL_HOST', 'localhost'),
                user=os.environ.get('MYSQL_USER', 'root'),
                password=os.environ.get('MYSQL_PASSWORD', ''),
                database=os.environ.get('MYSQL_DB', 'student_ai_db')
            )
            return conn
        except Exception as e:
            print(f"[DB Warning] MySQL connection failed: {e}. Falling back to SQLite.")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # allows concurrent reads + writes
    conn.execute("PRAGMA busy_timeout=10000") # wait up to 10s if locked
    return conn

def init_database():
    conn = get_db_connection()
    cur = conn.cursor()
    schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'schema.sql')
    
    if os.path.exists(schema_path):
        with open(schema_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
            
        if isinstance(conn, sqlite3.Connection):
            cur.executescript(sql_script)
        else:
            for statement in sql_script.split(';'):
                if statement.strip():
                    cur.execute(statement)
            conn.commit()

    # Migration check for existing SQLite tables if missing new columns
    if isinstance(conn, sqlite3.Connection):
        cur.execute("PRAGMA table_info(students)")
        existing_cols = [row['name'] for row in cur.fetchall()]
        
        new_cols = [
            ('usn', "VARCHAR(50) DEFAULT ''"),
            ('email', "VARCHAR(100) DEFAULT ''"),
            ('phone', "VARCHAR(20) DEFAULT ''"),
            ('password_hash', "VARCHAR(255) DEFAULT ''"),
            ('dob', "VARCHAR(20) DEFAULT ''"),
            ('gender', "VARCHAR(20) DEFAULT 'Male'"),
            ('admission_year', "VARCHAR(10) DEFAULT '2023'"),
            ('current_semester', "INTEGER DEFAULT 6"),
            ('previous_institution', "VARCHAR(150) DEFAULT ''"),
            ('father_education', "VARCHAR(100) DEFAULT 'Graduate'"),
            ('father_occupation', "VARCHAR(100) DEFAULT 'Service'"),
            ('mother_education', "VARCHAR(100) DEFAULT 'Graduate'"),
            ('mother_occupation', "VARCHAR(100) DEFAULT 'Homemaker'"),
            ('parent_annual_income', "REAL DEFAULT 500000.0"),
            ('own_study_room', "VARCHAR(10) DEFAULT 'Yes'"),
            ('daily_travel_time', "REAL DEFAULT 1.0"),
            ('prog_languages', "TEXT DEFAULT 'Python, Java'"),
            ('academic_projects', "INTEGER DEFAULT 2"),
            ('personal_projects', "INTEGER DEFAULT 1"),
            ('github_profile', "VARCHAR(255) DEFAULT ''"),
            ('linkedin_profile', "VARCHAR(255) DEFAULT ''"),
            ('online_platforms', "TEXT DEFAULT 'LeetCode'"),
            ('coding_contests', "VARCHAR(10) DEFAULT 'Yes'"),
            ('hackathons', "VARCHAR(10) DEFAULT 'Yes'"),
            ('active_backlogs', "INTEGER DEFAULT 0"),
            ('cleared_backlogs', "INTEGER DEFAULT 0"),
            ('total_backlog_history', "INTEGER DEFAULT 0"),
            ('teacher_remarks', "TEXT DEFAULT ''"),
            ('approval_status', "VARCHAR(20) DEFAULT 'Approved'"),
            ('subject3_marks', "REAL DEFAULT 70.0"),
            ('subject4_marks', "REAL DEFAULT 70.0"),
            # Per-IA-Test marks for each subject (0-50 each)
            ('ia1_sub1', "REAL DEFAULT NULL"),
            ('ia2_sub1', "REAL DEFAULT NULL"),
            ('ia3_sub1', "REAL DEFAULT NULL"),
            ('ia1_sub2', "REAL DEFAULT NULL"),
            ('ia2_sub2', "REAL DEFAULT NULL"),
            ('ia3_sub2', "REAL DEFAULT NULL"),
            ('ia1_sub3', "REAL DEFAULT NULL"),
            ('ia2_sub3', "REAL DEFAULT NULL"),
            ('ia3_sub3', "REAL DEFAULT NULL"),
            ('ia1_sub4', "REAL DEFAULT NULL"),
            ('ia2_sub4', "REAL DEFAULT NULL"),
            ('ia3_sub4', "REAL DEFAULT NULL")
        ]
        for col_name, col_def in new_cols:
            if col_name not in existing_cols:
                try:
                    cur.execute(f"ALTER TABLE students ADD COLUMN {col_name} {col_def}")
                except Exception as e:
                    print(f"Migration notice ({col_name}): {e}")

        # Migration check for semester_history table
        cur.execute("PRAGMA table_info(semester_history)")
        sem_existing_cols = [row['name'] for row in cur.fetchall()]
        sem_new_cols = [
            ('backlog_count', "INTEGER DEFAULT 0"),
            ('backlog_details_json', "TEXT DEFAULT '[]'"),
            ('backlog_status', "VARCHAR(20) DEFAULT 'None'")
        ]
        for col_name, col_def in sem_new_cols:
            if col_name not in sem_existing_cols:
                try:
                    cur.execute(f"ALTER TABLE semester_history ADD COLUMN {col_name} {col_def}")
                except Exception as e:
                    print(f"Sem History Migration notice ({col_name}): {e}")

        # Migration check for ranking_history table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ranking_history (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id              INTEGER NOT NULL,
                ranking_score           REAL NOT NULL,
                college_rank            INTEGER NOT NULL,
                department_rank         INTEGER NOT NULL,
                class_rank              INTEGER NOT NULL,
                evaluated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ranking_history_student ON ranking_history(student_id, evaluated_at)")

        # Create Doubts Discussion Tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS doubts (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id              INTEGER NOT NULL,
                title                   VARCHAR(255) NOT NULL,
                subject                 VARCHAR(100) NOT NULL,
                description             TEXT NOT NULL,
                code                    TEXT DEFAULT '',
                image_path              VARCHAR(255) DEFAULT '',
                status                  VARCHAR(20) DEFAULT 'Unanswered',
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_doubts_student ON doubts(student_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_doubts_subject ON doubts(subject)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_doubts_status ON doubts(status)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                doubt_id                INTEGER NOT NULL,
                student_id              INTEGER NOT NULL,
                answer_text             TEXT NOT NULL,
                is_accepted             INTEGER DEFAULT 0,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doubt_id) REFERENCES doubts(id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_answers_doubt ON answers(doubt_id)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS replies (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                answer_id               INTEGER NOT NULL,
                student_id              INTEGER NOT NULL,
                reply_text              TEXT NOT NULL,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_replies_answer ON replies(answer_id)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS doubt_likes (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                doubt_id                INTEGER NOT NULL,
                student_id              INTEGER NOT NULL,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(doubt_id, student_id),
                FOREIGN KEY (doubt_id) REFERENCES doubts(id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS answer_likes (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                answer_id               INTEGER NOT NULL,
                student_id              INTEGER NOT NULL,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(answer_id, student_id),
                FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)

        # Create Teacher-Student Communication Tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teacher_student_messages (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id              INTEGER NOT NULL,
                teacher_id              VARCHAR(50) NOT NULL,
                category                VARCHAR(100) NOT NULL,
                topic                   VARCHAR(255) NOT NULL,
                context_data            TEXT DEFAULT '{}',
                status                  VARCHAR(20) DEFAULT 'Open',
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ts_messages_student ON teacher_student_messages(student_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ts_messages_teacher ON teacher_student_messages(teacher_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ts_messages_status ON teacher_student_messages(status)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS teacher_student_replies (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id         INTEGER NOT NULL,
                sender_id               VARCHAR(50) NOT NULL,
                sender_role             VARCHAR(30) NOT NULL,
                sender_name             VARCHAR(100) NOT NULL,
                message                 TEXT NOT NULL,
                read_status             INTEGER DEFAULT 0,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES teacher_student_messages(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ts_replies_conversation ON teacher_student_replies(conversation_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ts_replies_read_status ON teacher_student_replies(read_status)")

        # Create Dynamic Subjects & Student IA Marks Tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_name            VARCHAR(100) NOT NULL,
                department              VARCHAR(50) NOT NULL,
                semester                INTEGER NOT NULL,
                section                 VARCHAR(5) NOT NULL,
                teacher_id              VARCHAR(50) DEFAULT '',
                display_order           INTEGER DEFAULT 1,
                active                  INTEGER DEFAULT 1,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subjects_class ON subjects(department, semester, section, active)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS student_ia_marks (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id              INTEGER NOT NULL,
                subject_id              INTEGER NOT NULL,
                ia1                     REAL DEFAULT NULL,
                ia2                     REAL DEFAULT NULL,
                ia3                     REAL DEFAULT NULL,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, subject_id),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_student_ia_marks_lookup ON student_ia_marks(student_id, subject_id)")

        # Migration: Ensure existing class scopes have default subjects Sub 1..4 and migrate existing IA marks
        try:
            cur.execute("SELECT DISTINCT department, current_semester, section FROM students WHERE department IS NOT NULL")
            scopes = cur.fetchall()
            scope_list = set()
            for r in scopes:
                d = r[0]
                sm = r[1]
                sc = r[2]
                if d:
                    scope_list.add((d, int(sm or 6), (sc or 'A').upper()))

            for dept, sem, sec in scope_list:
                cur.execute("SELECT COUNT(*) FROM subjects WHERE department=? AND semester=? AND section=? AND active=1", (dept, sem, sec))
                s_row = cur.fetchone()
                cnt = s_row[0]
                if cnt == 0:
                    default_subs = ["Sub 1", "Sub 2", "Sub 3", "Sub 4"]
                    for idx, sname in enumerate(default_subs, 1):
                        cur.execute("""
                            INSERT INTO subjects (subject_name, department, semester, section, display_order, active)
                            VALUES (?, ?, ?, ?, ?, 1)
                        """, (sname, dept, sem, sec, idx))


            # Migrate student marks from ia1_sub1..ia3_sub4 into student_ia_marks
            cur.execute("SELECT id, department, current_semester, section, ia1_sub1, ia2_sub1, ia3_sub1, ia1_sub2, ia2_sub2, ia3_sub2, ia1_sub3, ia2_sub3, ia3_sub3, ia1_sub4, ia2_sub4, ia3_sub4 FROM students")
            all_stus = cur.fetchall()
            for st in all_stus:
                st_id = st[0]
                s_dept = st[1] or 'CSE'
                s_sem = int(st[2] or 6)
                s_sec = (st[3] or 'A').upper()

                cur.execute("SELECT id FROM subjects WHERE department=? AND semester=? AND section=? AND active=1 ORDER BY display_order ASC, id ASC", (s_dept, s_sem, s_sec))
                sub_rows = cur.fetchall()
                sub_ids = [sr[0] for sr in sub_rows]

                col_triplets = [
                    (st[4], st[5], st[6]),
                    (st[7], st[8], st[9]),
                    (st[10], st[11], st[12]),
                    (st[13], st[14], st[15]),
                ]

                for idx, sub_id in enumerate(sub_ids):
                    if idx < len(col_triplets):
                        ia1, ia2, ia3 = col_triplets[idx]
                        if ia1 is not None or ia2 is not None or ia3 is not None:
                            cur.execute("SELECT id FROM student_ia_marks WHERE student_id=? AND subject_id=?", (st_id, sub_id))
                            ex = cur.fetchone()
                            if not ex:
                                cur.execute("INSERT INTO student_ia_marks (student_id, subject_id, ia1, ia2, ia3) VALUES (?, ?, ?, ?, ?)",
                                            (st_id, sub_id, ia1, ia2, ia3))
        except Exception as e:
            print(f"Dynamic Subject Migration notice: {e}")

        conn.commit()


    # Seed single default Admin user if missing
    try:
        cur.execute("SELECT COUNT(*) FROM users WHERE role='Admin'")
        admin_cnt = cur.fetchone()[0]
        demo_pwd_hash = generate_password_hash(DEFAULT_DEMO_PASSWORD)

        if admin_cnt == 0:
            # 1. Admin
            cur.execute("""
                INSERT INTO users (user_id, name, email, login_id, password_hash, temp_password, role, department, first_login)
                VALUES ('USR-001', 'System Administrator', 'admin@example.com', 'ADMIN001', ?, ?, 'Admin', 'ALL', 0)
            """, (demo_pwd_hash, DEFAULT_DEMO_PASSWORD))

            conn.commit()
    except Exception as e:
        print(f"User seed notice: {e}")

    conn.close()


def get_class_subjects(department, semester, section, active_only=True):
    """
    Returns list of subject records for a given class scope.
    """
    query = "SELECT * FROM subjects WHERE department=? AND semester=? AND section=?"
    params = [department, int(semester), (section or 'A').upper()]
    if active_only:
        query += " AND active=1"
    query += " ORDER BY display_order ASC, id ASC"
    return execute_query(query, tuple(params), fetchall=True) or []


def get_student_ia_marks(student_id):
    """
    Returns all IA marks joined with subject details for a student.
    """
    query = """
        SELECT sm.*, s.subject_name, s.department, s.semester, s.section, s.display_order, s.active
        FROM student_ia_marks sm
        JOIN subjects s ON sm.subject_id = s.id
        WHERE sm.student_id = ?
        ORDER BY s.display_order ASC, s.id ASC
    """
    return execute_query(query, (student_id,), fetchall=True) or []


def save_student_ia_mark(student_id, subject_id, ia1=None, ia2=None, ia3=None):
    """
    Inserts or updates IA marks for a specific student and subject.
    """
    existing = execute_query("SELECT id FROM student_ia_marks WHERE student_id=? AND subject_id=?", (student_id, subject_id), fetchone=True)
    if existing:
        execute_query("UPDATE student_ia_marks SET ia1=?, ia2=?, ia3=?, updated_at=CURRENT_TIMESTAMP WHERE student_id=? AND subject_id=?",
                      (ia1, ia2, ia3, student_id, subject_id), commit=True)
    else:
        execute_query("INSERT INTO student_ia_marks (student_id, subject_id, ia1, ia2, ia3) VALUES (?, ?, ?, ?, ?)",
                      (student_id, subject_id, ia1, ia2, ia3), commit=True)


def calculate_cgpa(student_id):
    """
    Calculate Average CGPA from all non-null previous SGPAs in semester_history.
    Formula: sum(SGPAs) / count(SGPAs), rounded to 2 decimal places.
    Returns None if no SGPA records exist.
    """
    rows = execute_query(
        "SELECT sgpa FROM semester_history WHERE student_id=? AND sgpa IS NOT NULL AND sgpa > 0",
        (student_id,), fetchall=True
    )
    if not rows:
        return None
    sgpa_values = [float(r['sgpa']) for r in rows if r.get('sgpa') is not None]
    if not sgpa_values:
        return None
    return round(sum(sgpa_values) / len(sgpa_values), 2)



def execute_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    
    result = None
    if fetchone:
        row = cur.fetchone()
        if row and isinstance(conn, sqlite3.Connection):
            result = dict(row)
        elif row:
            if hasattr(cur, 'column_names'):
                result = dict(zip(cur.column_names, row))
            else:
                result = row
    elif fetchall:
        rows = cur.fetchall()
        if rows and isinstance(conn, sqlite3.Connection):
            result = [dict(r) for r in rows]
        elif rows:
            if hasattr(cur, 'column_names'):
                result = [dict(zip(cur.column_names, r)) for r in rows]
            else:
                result = [dict(r) for r in rows]
        else:
            result = []

    if commit:
        conn.commit()
        if not result and hasattr(cur, 'lastrowid'):
            result = cur.lastrowid

    conn.close()
    return result
