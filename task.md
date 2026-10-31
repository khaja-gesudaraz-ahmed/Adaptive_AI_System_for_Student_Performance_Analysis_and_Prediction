# Fix Tasks

- [x] 1. db_service.py — Add migrations for 12 IA mark columns (ia1_sub1..ia3_sub4) + calculate_cgpa() helper
- [x] 2. schema.sql — Add IA columns to DDL
- [x] 3. teacher.py — Fix upload-excel to store per-IA-test columns (0-50), UPSERT by USN, recalculate CGPA; add attendance management routes
- [x] 4. student.py — Fix /details API to read actual IA columns from DB; fix CGPA from semester_history; fix registration CGPA
- [x] 5. teacher_dashboard.html — Add Attendance Management button
- [x] 6. templates/attendance_management.html — New attendance entry page
- [x] 7. app.js — Fix placement/shap/study_plan field mismatches; fix CGPA display; add visibility-change refresh
- [x] 8. requirements.txt — Add openpyxl
