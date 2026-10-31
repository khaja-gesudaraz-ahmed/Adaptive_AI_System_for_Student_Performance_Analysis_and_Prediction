# Student Performance Analyzer & Marks Prediction System
### Enterprise College Project | Explainable AI (SHAP) & Multi-Module Analytics

---

## 🌟 Overview & New Features

Student Performance Analyzer & Marks Prediction System has been extended into a comprehensive, enterprise-grade AI system for student performance prediction, explainability, placement counseling, and teacher analytics.

### 🚀 Key Integrated Modules

1. **Explainable AI (SHAP)**
   - Integrates SHAP (`TreeExplainer`) with Decision Tree ML models.
   - Computes prediction confidence percentages (e.g. *High Risk (84%)* or *Pass (92%)*).
   - Generates feature impact breakdown, directional indicators (↑/↓), waterfall bar chart, and plain English explanation text.

2. **AI Personalized Study Planner**
   - Dynamically constructs a weekly timetable (Monday–Sunday) tailored to student weak subjects, attendance, internal evaluation, study hours, semester, and predicted risk level.
   - Supports Gemini / OpenAI API integration with an intelligent rule-based fallback engine.

3. **Teacher Analytics Dashboard**
   - Includes 7 summary cards (Total Students, Avg CGPA, Avg Attendance, Pass Rate %, Fail Rate %, High Risk Count, Top Performers).
   - **8 Interactive Chart.js Visualizations & Tables**:
     1. Pass vs Fail Pie Chart
     2. Average Subject Marks Bar Chart
     3. Semester Performance Trend Line Chart
     4. Attendance Distribution Chart
     5. Risk Level Breakdown Chart
     6. Weak Subject Analysis Chart
     7. Top Performing Students Leaderboard
     8. High Risk Student Warning Alert List
   - **Dynamic Filter Bar**: Filter metrics and charts by Department (CSE, ECE, IT, EEE, Mechanical), Semester (Sem 1-8), Section (A, B, C), and Academic Year.

4. **Student Ranking System**
   - Weighted Performance Ranking Formula:
     `Overall Score = Attendance (20%) + CGPA (30%) + Internal Marks (20%) + Consistency (20%) + Improvement (10%)`
   - Computes Department Rank, Class Rank, Top 10 Leaderboard, Most Improved Student Award, and Best Attendance Award.

5. **Performance Timeline & Progression**
   - Tracks semester-wise metrics (`SGPA`, `CGPA`, `Attendance`, `Study Hours`, `Risk Level`).
   - Interactive trend graph, performance drop/improvement alert detection, and AI narrative summary.

6. **Placement Readiness Score**
   - Weighted Formula:
     `Programming (30%) + CGPA (20%) + Projects (20%) + Communication (10%) + Internship (10%) + Attendance (10%)`
   - Interactive Gauge Chart, corporate target company recommendations (*Infosys, TCS, Accenture, Capgemini, Cognizant, IBM, Wipro*), and actionable AI suggestions.

7. **Professional PDF Report Generator**
   - Built using `ReportLab`.
   - Generates downloadable, institutional PDF reports containing logo, student info, performance breakdown, SHAP explanations, weekly study plan, placement score, teacher remarks, and timestamp.

---

## 📁 System Architecture

```
student-ai-system/
├── app.py                      # Main Flask application & Blueprint registration
├── requirements.txt            # Extended Python dependencies (shap, reportlab, mysql-connector-python)
│
├── blueprints/                 # Flask Blueprints
│   ├── student.py              # Student predictions, SHAP, study planner, rankings
│   ├── teacher.py              # Teacher login, analytics dashboard & filter API
│   └── report.py               # PDF Report streaming
│
├── services/                   # Business & Analytics Logic Layer
│   ├── db_service.py           # Dual SQLite & MySQL database driver with auto-migration
│   ├── shap_service.py         # SHAP TreeExplainer & feature impact engine
│   ├── planner_service.py      # Weekly study schedule generator
│   ├── ranking_service.py      # Weighted student ranking & awards engine
│   ├── timeline_service.py     # Semester trend history & drop detector
│   ├── placement_service.py    # Placement readiness index & company matcher
│   └── pdf_service.py          # Professional ReportLab PDF builder
│
├── ml/                         # Machine Learning Models
│   ├── sample_data.csv         # Training dataset
│   ├── train_model.py          # Model training script
│   ├── model_result.pkl        # Saved Pass/Fail Decision Tree model
│   ├── model_risk.pkl          # Saved Risk Level Decision Tree model
│   └── encoders.pkl            # Label Encoders
│
├── database/
│   ├── schema.sql              # MySQL/SQLite DDL for all 7 tables
│   └── students.db             # Local SQLite database
│
├── templates/
│   ├── base.html               # Bootstrap 5 layout with Dark Mode toggle
│   ├── index.html              # Student Portal & Multi-tab AI Analyzer
│   ├── teacher_login.html      # Teacher Login Portal
│   └── teacher_dashboard.html  # Teacher Analytics & Filter Dashboard
│
└── static/
    ├── css/style.css           # Custom styling system
    └── js/
        ├── app.js              # Student Portal JS (Predict, SHAP, Gauge, Timeline)
        └── teacher.js          # Teacher Dashboard JS (Filters, 8 Charts)
```

---

## ⚡ Quick Setup & Running

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. (Optional) Train ML Models
```bash
python ml/train_model.py
```

### 3. Run the Application
```bash
python app.py
```

### 4. Access Ports & Portals
- **Student Portal**: `http://localhost:5000`
- **Teacher Dashboard**: `http://localhost:5000/teacher/dashboard`
- **Teacher Login**: `http://localhost:5000/teacher/login` *(Default Login: `teacher@example.com` / `admin123`)*

---

## 🗄️ Database Integration (MySQL / SQLite Dual Support)

By default, the application runs on **SQLite** with zero configuration.

To switch to **MySQL**:
Set environment variables:
```bash
export USE_MYSQL=true
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
export MYSQL_DB=student_ai_db
```
Or execute `database/schema.sql` directly into your MySQL server.

## VTU SEE Forecasts in Reports (No UI Changes)

The report generator now includes subject-wise SEE forecasts in both the individual student PDF and class PDF. The existing dashboard/interface templates are unchanged. Forecast rows include the current CIE estimate (best two IA marks), minimum SEE mark needed, estimated SEE mark, projected total, and a likely-pass/borderline/at-risk label.

The forecast is an explainable rule-based baseline, not a trained or validated ML probability. It estimates SEE as 70% of current subject IA performance plus 30% of previous-semester percentage converted to a /50 scale, when prior-semester percentage is available; otherwise it uses the IA estimate alone.

Configured thresholds for this project are CIE >= 20/50, SEE >= 20/50, and combined CIE + SEE >= 40/100. The 20/50 SEE threshold is configured to follow the requested project rule that 18/50 should be treated as failing. VTU regulations can vary by scheme and subject type, so confirm the exact applicable scheme before using predictions for official decisions.
