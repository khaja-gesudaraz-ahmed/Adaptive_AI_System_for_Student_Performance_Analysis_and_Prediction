-- ═══════════════════════════════════════════════════════
-- Student Performance Analyzer & Marks Prediction System Database Schema
-- Compatible with SQLite and MySQL
-- ═══════════════════════════════════════════════════════

-- ─── 1. Users Table (Admin, HOD, Class Teacher) ─────────
CREATE TABLE IF NOT EXISTS users (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 VARCHAR(50) UNIQUE NOT NULL,
    name                    VARCHAR(100) NOT NULL,
    email                   VARCHAR(100) UNIQUE NOT NULL,
    login_id                VARCHAR(50) UNIQUE NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    temp_password           VARCHAR(100) DEFAULT '',
    role                    VARCHAR(30) NOT NULL, -- 'Admin', 'HOD', 'Class Teacher'
    department              VARCHAR(50) DEFAULT 'CSE',
    semester                INTEGER DEFAULT 6,
    section                 VARCHAR(5) DEFAULT 'A',
    academic_year           VARCHAR(20) DEFAULT '2024-25',
    account_status          VARCHAR(20) DEFAULT 'Active', -- 'Active', 'Disabled'
    first_login             INTEGER DEFAULT 1, -- 1: Force password change
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── 2. Students Table ──────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    usn                     VARCHAR(50) NOT NULL UNIQUE,
    name                    VARCHAR(100) NOT NULL,
    email                   VARCHAR(100) NOT NULL UNIQUE,
    phone                   VARCHAR(20),
    password_hash           VARCHAR(255) NOT NULL,
    dob                     VARCHAR(20),
    gender                  VARCHAR(20) DEFAULT 'Male',
    department              VARCHAR(50) DEFAULT 'CSE',
    section                 VARCHAR(5) DEFAULT 'A',
    admission_year          VARCHAR(10) DEFAULT '2023',
    current_semester        INTEGER DEFAULT 6,

    -- Academic Background
    tenth_percentage        REAL DEFAULT 85.0,
    twelfth_percentage      REAL DEFAULT 82.0,
    previous_institution    VARCHAR(150),
    
    -- Family Background
    father_education        VARCHAR(100) DEFAULT 'Graduate',
    father_occupation       VARCHAR(100) DEFAULT 'Service',
    mother_education        VARCHAR(100) DEFAULT 'Graduate',
    mother_occupation       VARCHAR(100) DEFAULT 'Homemaker',
    parent_annual_income    REAL DEFAULT 500000.0,
    
    -- Home Study Environment
    own_study_room          VARCHAR(10) DEFAULT 'Yes',
    internet                VARCHAR(10) DEFAULT 'Yes',
    own_laptop              VARCHAR(10) DEFAULT 'Yes',
    smartphone              VARCHAR(10) DEFAULT 'Yes',
    study_hours             REAL DEFAULT 4.0,
    daily_travel_time       REAL DEFAULT 1.0,
    
    -- Technology Access & Skills
    laptop_years            REAL DEFAULT 2.0,
    programming_experience  REAL DEFAULT 1.0,
    prog_languages          TEXT DEFAULT 'Python, Java, C++',
    academic_projects       INTEGER DEFAULT 2,
    personal_projects       INTEGER DEFAULT 1,
    internships_count       INTEGER DEFAULT 1,
    certifications_count    INTEGER DEFAULT 2,
    github_profile          VARCHAR(255),
    linkedin_profile        VARCHAR(255),
    online_platforms        TEXT DEFAULT 'LeetCode, HackerRank',
    coding_contests         VARCHAR(10) DEFAULT 'Yes',
    hackathons              VARCHAR(10) DEFAULT 'Yes',

    -- Auto Academic History & Calculated Metrics
    cgpa                    REAL DEFAULT 7.8,
    active_backlogs         INTEGER DEFAULT 0,
    cleared_backlogs        INTEGER DEFAULT 0,
    total_backlog_history   INTEGER DEFAULT 0,
    
    -- Evaluation & ML Inputs
    attendance              REAL DEFAULT 78.0,
    internal_marks          REAL DEFAULT 70.0,
    dbms_marks              REAL DEFAULT 72.0,
    java_marks              REAL DEFAULT 68.0,
    subject3_marks          REAL DEFAULT 75.0,
    subject4_marks          REAL DEFAULT 70.0,
    prev_sem_percentage     REAL DEFAULT 75.0,
    medical_leave           VARCHAR(10) DEFAULT 'No',

    -- Educational background options
    tenth_board             VARCHAR(50) DEFAULT 'CBSE',
    twelfth_board           VARCHAR(50) DEFAULT 'CBSE',
    school_type             VARCHAR(50) DEFAULT 'Private',
    school_location         VARCHAR(50) DEFAULT 'Urban',
    coding_score            REAL DEFAULT 70.0,
    communication_score     REAL DEFAULT 75.0,
    academic_year           VARCHAR(20) DEFAULT '2024-25',
    
    -- Per-IA-Test marks for each subject (0-50 each; NULL = not yet entered)
    ia1_sub1                REAL DEFAULT NULL,   -- IA-1 Subject 1 (DBMS)
    ia2_sub1                REAL DEFAULT NULL,   -- IA-2 Subject 1
    ia3_sub1                REAL DEFAULT NULL,   -- IA-3 Subject 1
    ia1_sub2                REAL DEFAULT NULL,   -- IA-1 Subject 2 (Java)
    ia2_sub2                REAL DEFAULT NULL,
    ia3_sub2                REAL DEFAULT NULL,
    ia1_sub3                REAL DEFAULT NULL,   -- IA-1 Subject 3 (CN)
    ia2_sub3                REAL DEFAULT NULL,
    ia3_sub3                REAL DEFAULT NULL,
    ia1_sub4                REAL DEFAULT NULL,   -- IA-1 Subject 4 (SE)
    ia2_sub4                REAL DEFAULT NULL,
    ia3_sub4                REAL DEFAULT NULL,

    -- ML Output & Workflow Status
    predicted_result        VARCHAR(20) DEFAULT 'Pass',
    risk_level              VARCHAR(20) DEFAULT 'Low',
    anomaly_detected        INTEGER DEFAULT 0,
    approval_status         VARCHAR(20) DEFAULT 'Pending', -- Pending / Approved / Rejected
    teacher_remarks         TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── 3. Automatic Student Semester History ─────────────
CREATE TABLE IF NOT EXISTS semester_history (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id              INTEGER NOT NULL,
    semester                INTEGER NOT NULL,
    sgpa                    REAL NOT NULL DEFAULT 0.0,
    backlog_count           INTEGER DEFAULT 0,
    backlog_details_json    TEXT DEFAULT '[]',
    backlog_status          VARCHAR(20) DEFAULT 'None', -- Active / Cleared / None
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS student_semesters (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id              INTEGER NOT NULL,
    semester                INTEGER NOT NULL,
    sgpa                    REAL NOT NULL DEFAULT 7.5,
    backlog_subjects        TEXT DEFAULT '',
    backlog_status          VARCHAR(20) DEFAULT 'None',
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

-- ─── 4. Teachers Table ──────────────────────────────────
CREATE TABLE IF NOT EXISTS teachers (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id              VARCHAR(50) UNIQUE DEFAULT 'T1001',
    name                    VARCHAR(100) NOT NULL,
    email                   VARCHAR(100) NOT NULL UNIQUE,
    password_hash           VARCHAR(255) NOT NULL,
    department              VARCHAR(50) DEFAULT 'CSE',
    role                    VARCHAR(50) DEFAULT 'Class Coordinator',
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ─── 5. Study Plans Table ───────────────────────────────
CREATE TABLE IF NOT EXISTS study_plans (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id              INTEGER NOT NULL,
    plan_json               TEXT NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

-- ─── 6. Ranking History Table ───────────────────────────
CREATE TABLE IF NOT EXISTS ranking_history (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id              INTEGER NOT NULL,
    ranking_score           REAL NOT NULL,
    college_rank            INTEGER NOT NULL,
    department_rank         INTEGER NOT NULL,
    class_rank              INTEGER NOT NULL,
    evaluated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ranking_history_student ON ranking_history(student_id, evaluated_at);

-- ─── 7. Doubts Discussion System Tables ─────────────────
CREATE TABLE IF NOT EXISTS doubts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id              INTEGER NOT NULL,
    title                   VARCHAR(255) NOT NULL,
    subject                 VARCHAR(100) NOT NULL,
    description             TEXT NOT NULL,
    code                    TEXT DEFAULT '',
    image_path              VARCHAR(255) DEFAULT '',
    status                  VARCHAR(20) DEFAULT 'Unanswered', -- 'Unanswered', 'Answered', 'Solved'
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_doubts_student ON doubts(student_id);
CREATE INDEX IF NOT EXISTS idx_doubts_subject ON doubts(subject);
CREATE INDEX IF NOT EXISTS idx_doubts_status ON doubts(status);

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
);
CREATE INDEX IF NOT EXISTS idx_answers_doubt ON answers(doubt_id);
CREATE INDEX IF NOT EXISTS idx_answers_student ON answers(student_id);

CREATE TABLE IF NOT EXISTS replies (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id               INTEGER NOT NULL,
    student_id              INTEGER NOT NULL,
    reply_text              TEXT NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_replies_answer ON replies(answer_id);
CREATE INDEX IF NOT EXISTS idx_replies_student ON replies(student_id);

CREATE TABLE IF NOT EXISTS doubt_likes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    doubt_id                INTEGER NOT NULL,
    student_id              INTEGER NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(doubt_id, student_id),
    FOREIGN KEY (doubt_id) REFERENCES doubts(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_doubt_likes_doubt ON doubt_likes(doubt_id);

CREATE TABLE IF NOT EXISTS answer_likes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id               INTEGER NOT NULL,
    student_id              INTEGER NOT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(answer_id, student_id),
    FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_answer_likes_answer ON answer_likes(answer_id);

-- ─── 8. Teacher-Student Communication Tables ─────────
CREATE TABLE IF NOT EXISTS teacher_student_messages (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id              INTEGER NOT NULL,
    teacher_id              VARCHAR(50) NOT NULL,
    category                VARCHAR(100) NOT NULL,
    topic                   VARCHAR(255) NOT NULL,
    context_data            TEXT DEFAULT '{}',
    status                  VARCHAR(20) DEFAULT 'Open', -- 'Open', 'Replied', 'Resolved'
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ts_messages_student ON teacher_student_messages(student_id);
CREATE INDEX IF NOT EXISTS idx_ts_messages_teacher ON teacher_student_messages(teacher_id);
CREATE INDEX IF NOT EXISTS idx_ts_messages_status ON teacher_student_messages(status);

CREATE TABLE IF NOT EXISTS teacher_student_replies (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id         INTEGER NOT NULL,
    sender_id               VARCHAR(50) NOT NULL,
    sender_role             VARCHAR(30) NOT NULL, -- 'Student' or 'Teacher'
    sender_name             VARCHAR(100) NOT NULL,
    message                 TEXT NOT NULL,
    read_status             INTEGER DEFAULT 0, -- 0: Unread, 1: Read
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES teacher_student_messages(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ts_replies_conversation ON teacher_student_replies(conversation_id);
CREATE INDEX IF NOT EXISTS idx_ts_replies_read_status ON teacher_student_replies(read_status);

-- ─── 9. Dynamic Subjects & Dynamic Student IA Marks Tables ─
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
);
CREATE INDEX IF NOT EXISTS idx_subjects_class ON subjects(department, semester, section, active);

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
);
CREATE INDEX IF NOT EXISTS idx_student_ia_marks_lookup ON student_ia_marks(student_id, subject_id);



