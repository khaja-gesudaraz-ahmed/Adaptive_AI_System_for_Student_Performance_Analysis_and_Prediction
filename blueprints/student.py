"""
Student Blueprint - Handles Student Authentication, Extended 5-Section Registration,
Automatic Academic History Generation, and Student Analytics Dashboard.
"""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
import os
import pickle
import json
import uuid
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from services.db_service import execute_query, calculate_cgpa, get_class_subjects, get_student_ia_marks
from services.shap_service import compute_shap_explanation
from services.planner_service import generate_study_plan
from services.ranking_service import compute_rankings
from services.timeline_service import generate_semester_timeline
from services.placement_service import calculate_placement_readiness
from services.risk_service import assess_student_risk

student_bp = Blueprint('student', __name__)

ML_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml')

def load_ml_assets():
    with open(os.path.join(ML_DIR, 'model_result.pkl'), 'rb') as f:
        model_result = pickle.load(f)
    with open(os.path.join(ML_DIR, 'model_risk.pkl'), 'rb') as f:
        model_risk = pickle.load(f)
    with open(os.path.join(ML_DIR, 'encoders.pkl'), 'rb') as f:
        encoders = pickle.load(f)
    return model_result, model_risk, encoders

model_result, model_risk, encoders = load_ml_assets()

def compute_best_two_ia_avg(ia1, ia2, ia3):
    """Return the average of the best two IA marks, with AB/missing treated as 0.

    Internals are out of 50. Examples: 35,42,46 -> 44; 38,44,AB -> 41;
    40,AB,AB -> 20; AB,AB,AB -> 0.
    """
    marks = []
    for value in (ia1, ia2, ia3):
        if value is None or str(value).strip().upper() in ('AB', 'ABSENT', '-', '—', ''):
            marks.append(0.0)
            continue
        try:
            mark = float(value)
        except (ValueError, TypeError):
            marks.append(0.0)
            continue
        marks.append(max(0.0, min(50.0, mark)))
    return round(sum(sorted(marks, reverse=True)[:2]) / 2.0, 1)

def detect_weak_subjects(student_id_or_dbms, java_marks=None, internal_marks=None, threshold=30):
    weak = []
    if isinstance(student_id_or_dbms, int):
        st_marks = get_student_ia_marks(student_id_or_dbms)
        for sm in st_marks:
            if sm.get('active', 1) == 1:
                ia1 = sm.get('ia1')
                ia2 = sm.get('ia2')
                ia3 = sm.get('ia3')
                avg_val = compute_best_two_ia_avg(ia1, ia2, ia3)
                if isinstance(avg_val, (int, float)) and avg_val < threshold:
                    weak.append({"subject_id": sm['subject_id'], "subject": sm['subject_name'], "marks": avg_val})
        return weak

    # Legacy numeric arguments fallback
    d_marks = float(student_id_or_dbms or 70)
    j_marks = float(java_marks or 70)
    i_marks = float(internal_marks or 70)
    if d_marks < 50:
        weak.append({"subject": "Subject 1", "marks": d_marks})
    if j_marks < 50:
        weak.append({"subject": "Subject 2", "marks": j_marks})
    if i_marks < 50:
        weak.append({"subject": "Internal Exam", "marks": i_marks})
    return weak

def detect_anomaly(prev_sem_percentage, internal_marks, dbms_marks, java_marks):
    avg_current = (internal_marks + dbms_marks + java_marks) / 3
    if prev_sem_percentage >= 75 and avg_current < 45:
        return True, f"Sudden performance drop detected - Prev sem: {prev_sem_percentage}%, Current avg: {avg_current:.1f}%"
    return False, ""

def adaptive_risk_logic(risk_predicted, internal_marks, medical_leave, prev_sem_percentage):
    if medical_leave == 1 or internal_marks == 0:
        if prev_sem_percentage >= 65:
            if risk_predicted == "High":
                return "Medium", "Risk adjusted to Medium (Medical leave / missing internals considered)"
        return risk_predicted, "Previous semester marks used due to medical leave or missing internals"
    return risk_predicted, ""

def generate_suggestions(result, risk, weak_subjects, anomaly, attendance, study_hours):
    suggestions = []
    if result == "Fail":
        suggestions.append("Schedule immediate one-on-one counselling session.")
    if risk == "High":
        suggestions.append("Place student on academic watch list.")
    if risk == "Medium":
        suggestions.append("Monitor student progress bi-weekly.")
    for ws in weak_subjects:
        suggestions.append(f"Arrange extra coaching for {ws['subject']} (scored {ws['marks']}/100).")
    if anomaly:
        suggestions.append("Investigate sudden performance drop - possible personal/health issues.")
    if attendance < 60:
        suggestions.append("Send attendance warning letter to student and parents.")
    if study_hours < 3:
        suggestions.append("Encourage structured daily study plan (minimum 4-5 hours).")
    if not suggestions:
        suggestions.append("Student is performing well. Keep motivating!")
    return suggestions

# ─── Student Authentication & Registration Routes ────────────────────────────

@student_bp.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        data = request.get_json() or {}
        
        usn = data.get('usn', '').strip().upper()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        name = data.get('name', '').strip()

        if not usn or not email or not password or not name:
            return jsonify({"success": False, "error": "USN, Name, Email, and Password are required."}), 400

        if password != confirm_password:
            return jsonify({"success": False, "error": "Passwords do not match."}), 400

        # Check USN / Email uniqueness
        existing_usn = execute_query("SELECT id FROM students WHERE usn=?", (usn,), fetchone=True)
        if existing_usn:
            return jsonify({"success": False, "error": f"USN '{usn}' is already registered."}), 400

        existing_email = execute_query("SELECT id FROM students WHERE email=?", (email,), fetchone=True)
        if existing_email:
            return jsonify({"success": False, "error": f"Email '{email}' is already registered."}), 400

        hashed_pwd = generate_password_hash(password)

        # Form fields
        phone = data.get('phone', '')
        dob = data.get('dob', '')
        gender = data.get('gender', 'Male')
        department = data.get('department', 'CSE')
        section = data.get('section', 'A')
        admission_year = data.get('admission_year', '2023')
        curr_sem = int(data.get('current_semester', 6))

        tenth_percentage = float(data.get('tenth_percentage', 85.0))
        twelfth_percentage = float(data.get('twelfth_percentage', 82.0))
        previous_institution = data.get('previous_institution', '')

        father_education = data.get('father_education', 'Graduate')
        father_occupation = data.get('father_occupation', 'Service')
        mother_education = data.get('mother_education', 'Graduate')
        mother_occupation = data.get('mother_occupation', 'Homemaker')
        parent_income = float(data.get('parent_annual_income', 500000.0) or 500000.0)

        own_study_room = data.get('own_study_room', 'Yes')
        internet = data.get('internet', 'Yes')
        own_laptop = data.get('own_laptop', 'Yes')
        smartphone = data.get('smartphone', 'Yes')
        study_hours = float(data.get('study_hours', 4.0))
        travel_time = float(data.get('daily_travel_time', 1.0))

        laptop_years = float(data.get('laptop_years', 2.0))
        programming_exp = float(data.get('programming_experience', 1.0))
        prog_languages = data.get('prog_languages', 'Python, Java')
        academic_projects = int(data.get('academic_projects', 2))
        personal_projects = int(data.get('personal_projects', 1))
        internships_cnt = int(data.get('internships_count', 1))
        certifications_cnt = int(data.get('certifications_count', 2))
        github_profile = data.get('github_profile', '')
        linkedin_profile = data.get('linkedin_profile', '')
        online_platforms = data.get('online_platforms', 'LeetCode, HackerRank')
        coding_contests = data.get('coding_contests', 'Yes')
        hackathons = data.get('hackathons', 'Yes')

        attendance = float(data.get('attendance', 78.0))
        s1 = float(data.get('subject1_marks', 72.0))
        s2 = float(data.get('subject2_marks', 68.0))
        s3 = float(data.get('subject3_marks', 75.0))
        s4 = float(data.get('subject4_marks', 70.0))
        avg_marks = (s1 + s2 + s3 + s4) / 4.0

        # Process Previous Semesters Academic History payload
        semesters_data = data.get('semesters_data', [])
        
        calculated_cgpa = 7.5
        active_backlogs = 0
        cleared_backlogs = 0
        total_backlog_history = 0

        if semesters_data and len(semesters_data) > 0:
            total_sgpa = 0.0
            for sem_item in semesters_data:
                sgpa_val = float(sem_item.get('sgpa', 7.5))
                total_sgpa += sgpa_val
                backlogs_list = sem_item.get('backlogs', [])
                total_backlog_history += len(backlogs_list)
                for bl in backlogs_list:
                    status = bl.get('status', 'Active')
                    if status == 'Active':
                        active_backlogs += 1
                    else:
                        cleared_backlogs += 1

            calculated_cgpa = round(total_sgpa / len(semesters_data), 2)
        else:
            # No semester data provided — default
            calculated_cgpa = 0.0

        # Run ML predictions
        try:
            med_enc = encoders['le_medical'].transform(['No'])[0]
            tb_enc = encoders['le_tenth_board'].transform(['CBSE'])[0]
            twb_enc = encoders['le_twelfth_board'].transform(['CBSE'])[0]
            st_enc = encoders['le_school_type'].transform(['Private'])[0]
            sl_enc = encoders['le_school_location'].transform(['Urban'])[0]
            ol_enc = encoders['le_own_laptop'].transform([own_laptop])[0]
            sp_enc = encoders['le_smartphone'].transform([smartphone])[0]
            int_enc = encoders['le_internet'].transform([internet])[0]

            feature_vals = {
                'attendance': attendance,
                'internal_marks': avg_marks,
                'study_hours': study_hours,
                'dbms_marks': s1,
                'java_marks': s2,
                'prev_sem_percentage': avg_marks,
                'medical_leave_enc': med_enc,
                'tenth_board_enc': tb_enc,
                'tenth_percentage': tenth_percentage,
                'twelfth_board_enc': twb_enc,
                'twelfth_percentage': twelfth_percentage,
                'school_type_enc': st_enc,
                'school_location_enc': sl_enc,
                'own_laptop_enc': ol_enc,
                'laptop_years': laptop_years,
                'smartphone_enc': sp_enc,
                'internet_enc': int_enc,
                'programming_experience': programming_exp
            }
            feat_cols = encoders.get('feature_names', [])
            features_df = pd.DataFrame([[feature_vals[c] for c in feat_cols]], columns=feat_cols)
            res_enc = model_result.predict(features_df)[0]
            risk_enc = model_risk.predict(features_df)[0]
            pred_result = encoders['le_result'].inverse_transform([res_enc])[0]
            risk_level = encoders['le_risk'].inverse_transform([risk_enc])[0]
        except Exception as e:
            pred_result = 'Pass'
            risk_level = 'Low'

        # Insert Student Record into DB
        insert_query = """
            INSERT INTO students (
                usn, name, email, phone, password_hash, dob, gender, department, section, admission_year, current_semester,
                tenth_percentage, twelfth_percentage, previous_institution, father_education, father_occupation,
                mother_education, mother_occupation, parent_annual_income, own_study_room, internet, own_laptop,
                smartphone, study_hours, daily_travel_time, laptop_years, programming_experience, prog_languages,
                academic_projects, personal_projects, internships_count, certifications_count, github_profile,
                linkedin_profile, online_platforms, coding_contests, hackathons, attendance, internal_marks,
                dbms_marks, java_marks, subject3_marks, subject4_marks, prev_sem_percentage, cgpa,
                active_backlogs, cleared_backlogs, total_backlog_history, predicted_result,
                risk_level, approval_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
        """
        student_id = execute_query(insert_query, (
            usn, name, email, phone, hashed_pwd, dob, gender, department, section, admission_year, curr_sem,
            tenth_percentage, twelfth_percentage, previous_institution, father_education, father_occupation,
            mother_education, mother_occupation, parent_income, own_study_room, internet, own_laptop,
            smartphone, study_hours, travel_time, laptop_years, programming_exp, prog_languages,
            academic_projects, personal_projects, internships_cnt, certifications_cnt, github_profile,
            linkedin_profile, online_platforms, coding_contests, hackathons, attendance, avg_marks,
            s1, s2, s3, s4, avg_marks, calculated_cgpa,
            active_backlogs, cleared_backlogs, total_backlog_history, pred_result, risk_level
        ), commit=True)

        # After saving semester history, recalculate CGPA from actual SGPA records
        cgpa_from_sgpa = calculate_cgpa(student_id)
        if cgpa_from_sgpa is not None:
            execute_query("UPDATE students SET cgpa=? WHERE id=?", (cgpa_from_sgpa, student_id), commit=True)

        if semesters_data and len(semesters_data) > 0:
            for sem_item in semesters_data:
                sem_num = int(sem_item.get('semester', 1))
                sgpa_val = float(sem_item.get('sgpa', 7.5))
                backlog_count = int(sem_item.get('backlog_count', 0))
                backlogs_list = sem_item.get('backlogs', [])
                backlog_json = json.dumps(backlogs_list)

                has_active = any(b.get('status') == 'Active' for b in backlogs_list)
                has_cleared = any(b.get('status') == 'Cleared' for b in backlogs_list)
                sem_backlog_status = 'Active' if has_active else ('Cleared' if has_cleared else 'None')

                execute_query("""
                    INSERT INTO semester_history (student_id, semester, sgpa, backlog_count, backlog_details_json, backlog_status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (student_id, sem_num, sgpa_val, backlog_count, backlog_json, sem_backlog_status), commit=True)

                subject_names = ", ".join([b.get('subject_name', '') for b in backlogs_list if b.get('subject_name')])
                execute_query("""
                    INSERT INTO student_semesters (student_id, semester, sgpa, backlog_subjects, backlog_status)
                    VALUES (?, ?, ?, ?, ?)
                """, (student_id, sem_num, sgpa_val, subject_names, sem_backlog_status), commit=True)

        elif curr_sem > 1:
            for sem in range(1, curr_sem):
                factor = (sem - 1) * 0.15
                sgpa_val = round(max(5.5, min(10.0, 7.0 + factor)), 2)
                execute_query("""
                    INSERT INTO semester_history (student_id, semester, sgpa, backlog_count, backlog_details_json, backlog_status)
                    VALUES (?, ?, ?, 0, '[]', 'None')
                """, (student_id, sem, sgpa_val), commit=True)

                execute_query("""
                    INSERT INTO student_semesters (student_id, semester, sgpa, backlog_subjects, backlog_status)
                    VALUES (?, ?, ?, '', 'None')
                """, (student_id, sem, sgpa_val), commit=True)

        return jsonify({
            "success": True,
            "message": "Registration successful! Your academic history has been recorded. Account is pending teacher approval.",
            "redirect_url": url_for('student.student_login')
        })

    return render_template('student_register.html')

@student_bp.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        data = request.get_json() or {}
        login_id = data.get('login_id', '').strip()
        password = data.get('password', '')

        if not login_id or not password:
            return jsonify({"success": False, "error": "USN/Email and Password are required."}), 400

        student = execute_query("SELECT * FROM students WHERE usn=? OR email=?", (login_id.upper(), login_id.lower()), fetchone=True)
        if not student:
            return jsonify({"success": False, "error": "Invalid USN/Email or Password."}), 401

        if not check_password_hash(student['password_hash'], password):
            return jsonify({"success": False, "error": "Invalid USN/Email or Password."}), 401

        status = student.get('approval_status', 'Pending')
        if status == 'Pending':
            return jsonify({"success": False, "error": "Your account is pending teacher approval. Please wait for authorization."}), 403
        elif status == 'Rejected':
            return jsonify({"success": False, "error": "Your registration was rejected. Please contact your department coordinator."}), 403

        # Approved student session login
        session['student_id'] = student['id']
        session['student_name'] = student['name']
        return jsonify({"success": True, "redirect_url": "/student/dashboard"})

    return render_template('student_login.html')

@student_bp.route('/student/logout', methods=['GET'])
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    return redirect(url_for('student.student_login'))

@student_bp.route('/student/dashboard', methods=['GET'])
def student_dashboard():
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('student.student_login'))

    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return redirect(url_for('student.student_login'))

    return render_template('student_dashboard.html', student=student, student_id=student_id)

@student_bp.route('/student/<int:student_id>/dashboard', methods=['GET'])
def student_dashboard_direct(student_id):
    session_st_id = session.get('student_id')
    if session_st_id and session_st_id != student_id and not session.get('teacher_logged_in'):
        student_id = session_st_id

    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return redirect(url_for('student.student_login'))

    return render_template('student_dashboard.html', student=student, student_id=student_id)

@student_bp.route('/student/new', methods=['GET'])
def new_student_redirect():
    return redirect(url_for('student.student_register'))

@student_bp.route('/students', methods=['GET'])
def all_students_page():
    return render_template('records.html')

@student_bp.route('/predict', methods=['POST'])
def legacy_predict():
    data = request.get_json() or {}
    usn = data.get('usn') or f"140{data.get('name', 'X')[:2].upper()}"
    email = data.get('email') or f"test_{usn.lower()}@example.com"
    data['usn'] = usn
    data['email'] = email
    data['password'] = 'Pass123!'
    data['confirm_password'] = 'Pass123!'
    
    st = execute_query("SELECT id FROM students WHERE usn=? OR email=?", (usn, email), fetchone=True)
    if st:
        student_id = st['id']
    else:
        hashed_pwd = generate_password_hash('Pass123!')
        name = data.get('name', 'Student')
        curr_sem = int(data.get('semester', 6))
        s1 = float(data.get('subject1_marks') or data.get('dbms_marks') or 70)
        s2 = float(data.get('subject2_marks') or data.get('java_marks') or 70)
        s3 = float(data.get('subject3_marks', 70))
        s4 = float(data.get('subject4_marks', 70))
        avg_m = (s1 + s2 + s3 + s4) / 4.0
        
        insert_query = """
            INSERT INTO students (usn, name, email, password_hash, current_semester, attendance, dbms_marks, java_marks, subject3_marks, subject4_marks, internal_marks, prev_sem_percentage, cgpa, predicted_result, risk_level, approval_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pass', 'Low', 'Approved')
        """
        student_id = execute_query(insert_query, (usn, name, email, hashed_pwd, curr_sem, float(data.get('attendance', 75)), s1, s2, s3, s4, avg_m, avg_m, round(avg_m/10, 2)), commit=True)
        
        if curr_sem > 1:
            for sem in range(1, curr_sem):
                execute_query("INSERT INTO semester_history (student_id, semester, sgpa) VALUES (?, ?, ?)", (student_id, sem, round(7.0 + sem*0.1, 2)), commit=True)
                execute_query("INSERT INTO student_semesters (student_id, semester, sgpa) VALUES (?, ?, ?)", (student_id, sem, round(7.0 + sem*0.1, 2)), commit=True)

    return jsonify({"success": True, "student_id": student_id, "redirect_url": f"/student/{student_id}/dashboard"})

@student_bp.route('/student/<int:student_id>/details', methods=['GET'])
def get_student_details(student_id):
    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student not found"}), 404
    current_risk = assess_student_risk(student)
    student.update({k: current_risk[k] for k in ('risk_level', 'risk_reasons', 'risk_subjects_high', 'risk_subjects_medium', 'risk_subjects_assessed', 'see_predictions')})

    if session.get('teacher_logged_in'):
        t_dept = session.get('teacher_dept')
        if t_dept and t_dept != 'None' and student.get('department') != t_dept:
            return jsonify({"success": False, "error": f"Access Denied: Student belongs to {student.get('department')} department, outside your assigned {t_dept} scope."}), 403

    if session.get('hod_logged_in'):
        h_dept = session.get('hod_dept')
        if h_dept and h_dept != 'None' and student.get('department') != h_dept:
            return jsonify({"success": False, "error": f"Access Denied: Student belongs to {student.get('department')} department, outside your assigned HOD scope ({h_dept})."}), 403

    active_subs = get_class_subjects(student.get('department', 'CSE'), student.get('current_semester', 6), student.get('section', 'A'), active_only=True)
    st_marks = get_student_ia_marks(student_id)
    marks_map = {m['subject_id']: m for m in st_marks}

    weak_subjects = detect_weak_subjects(student_id, student)
    study_plan = generate_study_plan(student, weak_subjects, student.get('risk_level', 'Low'))
    timeline = generate_semester_timeline(student_id, student)
    placement = calculate_placement_readiness(student)
    
    all_students = execute_query("SELECT * FROM students", fetchall=True)
    rankings = compute_rankings(all_students)
    current_rank = next((s for s in rankings['ranked_students'] if s.get('id') == student_id), None)

    def db_ia(val):
        """Convert DB value: None → '—', float → float, keep string as-is."""
        if val is None or val == '' or val == '-' or val == '—':
            return '—'
        return val

    att_val = float(student.get('attendance') or 0)

    subject_performance = []
    for sub in active_subs:
        m_rec = marks_map.get(sub['id'])
        ia1_v = db_ia(m_rec['ia1']) if m_rec else '—'
        ia2_v = db_ia(m_rec['ia2']) if m_rec else '—'
        ia3_v = db_ia(m_rec['ia3']) if m_rec else '—'
        b_avg = compute_best_two_ia_avg(ia1_v, ia2_v, ia3_v)

        subject_performance.append({
            "subject_id": sub['id'],
            "code": f"SUB{sub['id']}",
            "name": sub['subject_name'],
            "full_name": sub['subject_name'],
            "ia1": ia1_v,
            "ia2": ia2_v,
            "ia3": ia3_v,
            "best_two_avg": b_avg,
            "attendance": f"{att_val:.0f}%"
        })

    notifications = [
        {"title": "Attendance Updated", "desc": f"Your current overall attendance is {student.get('attendance', 78)}%", "time": "Today"},
        {"title": "Internal Marks Published", "desc": "Mid-semester IA-1 & IA-2 evaluation marks have been published", "time": "Yesterday"},
        {"title": "Teacher Added Remarks", "desc": student.get('teacher_remarks') or "Improve your attendance and spend more time on DBMS and Computer Networks.", "time": "2 days ago"},
        {"title": "Study Plan Updated", "desc": "Weekly AI study schedule generated based on weak subjects", "time": "3 days ago"}
    ]

    try:
        med_enc = encoders['le_medical'].transform(['No'])[0]
        tb_enc = encoders['le_tenth_board'].transform(['CBSE'])[0]
        twb_enc = encoders['le_twelfth_board'].transform(['CBSE'])[0]
        st_enc = encoders['le_school_type'].transform(['Private'])[0]
        sl_enc = encoders['le_school_location'].transform(['Urban'])[0]
        ol_enc = encoders['le_own_laptop'].transform([student.get('own_laptop', 'Yes')])[0]
        sp_enc = encoders['le_smartphone'].transform([student.get('smartphone', 'Yes')])[0]
        int_enc = encoders['le_internet'].transform([student.get('internet', 'Yes')])[0]

        feature_vals = {
            'attendance': float(student.get('attendance', 75)),
            'internal_marks': float(student.get('internal_marks', 70)),
            'study_hours': float(student.get('study_hours', 4)),
            'dbms_marks': float(student.get('dbms_marks', 70)),
            'java_marks': float(student.get('java_marks', 70)),
            'prev_sem_percentage': float(student.get('prev_sem_percentage', 75)),
            'medical_leave_enc': med_enc,
            'tenth_board_enc': tb_enc,
            'tenth_percentage': float(student.get('tenth_percentage', 85)),
            'twelfth_board_enc': twb_enc,
            'twelfth_percentage': float(student.get('twelfth_percentage', 82)),
            'school_type_enc': st_enc,
            'school_location_enc': sl_enc,
            'own_laptop_enc': ol_enc,
            'laptop_years': float(student.get('laptop_years', 2)),
            'smartphone_enc': sp_enc,
            'internet_enc': int_enc,
            'programming_experience': float(student.get('programming_experience', 1))
        }

        feat_cols = encoders.get('feature_names', [])
        features_df = pd.DataFrame([[feature_vals[c] for c in feat_cols]], columns=feat_cols)
        shap_explanation = compute_shap_explanation(model_result, model_risk, encoders, features_df)
    except Exception as e:
        shap_explanation = None

    anomaly, anomaly_msg = detect_anomaly(student.get('prev_sem_percentage', 75), student.get('internal_marks', 70), student.get('dbms_marks', 70), student.get('java_marks', 70))
    suggestions = generate_suggestions(student.get('predicted_result'), student.get('risk_level'), weak_subjects, anomaly, student.get('attendance', 75), student.get('study_hours', 4))

    return jsonify({
        "success": True,
        "student": student,
        "subject_performance": subject_performance,
        "notifications": notifications,
        "shap": shap_explanation,
        "study_plan": study_plan,
        "timeline": timeline,
        "placement": placement,
        "ranking": current_rank,
        "weak_subjects": weak_subjects,
        "anomaly_detected": anomaly,
        "anomaly_message": anomaly_msg,
        "suggestions": suggestions
    })

@student_bp.route('/student/<int:student_id>/ranking', methods=['GET'])
def get_student_ranking_api(student_id):
    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student not found"}), 404
    current_risk = assess_student_risk(student)
    student.update({k: current_risk[k] for k in ('risk_level', 'risk_reasons', 'risk_subjects_high', 'risk_subjects_medium', 'risk_subjects_assessed', 'see_predictions')})
    all_students = execute_query("SELECT * FROM students WHERE approval_status='Approved' OR approval_status IS NULL", fetchall=True) or []
    rankings = compute_rankings(all_students)
    student_rank = next((s for s in rankings['ranked_students'] if s.get('id') == student_id), None)
    return jsonify({
        "success": True,
        "ranking": student_rank,
        "college_rank": student_rank.get('college_rank') if student_rank else None,
        "department_rank": student_rank.get('department_rank') if student_rank else None,
        "class_rank": student_rank.get('class_rank') if student_rank else None,
        "ranking_score": student_rank.get('overall_score') if student_rank else None,
        "rank_change": student_rank.get('rank_change') if student_rank else 'New',
        "factors": student_rank.get('factors') if student_rank else None,
        "insights": {
            "top_3": rankings.get('top_3', []),
            "most_improved": rankings.get('most_improved'),
            "best_attendance": rankings.get('best_attendance'),
            "most_consistent": rankings.get('most_consistent')
        }
    })

@student_bp.route('/student/<int:student_id>/placement', methods=['GET'])
def get_student_placement_api(student_id):
    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student not found"}), 404
    current_risk = assess_student_risk(student)
    student.update({k: current_risk[k] for k in ('risk_level', 'risk_reasons', 'risk_subjects_high', 'risk_subjects_medium', 'risk_subjects_assessed', 'see_predictions')})
    placement = calculate_placement_readiness(student)
    return jsonify({
        "success": True,
        "student_id": student_id,
        "placement": placement
    })

@student_bp.route('/rankings', methods=['GET'])
def get_all_rankings():
    all_students = execute_query("SELECT * FROM students WHERE approval_status='Approved' OR approval_status IS NULL", fetchall=True)
    rankings = compute_rankings(all_students)
    return jsonify({
        "success": True,
        "rankings": rankings['ranked_students'],
        "top_10": rankings['top_10'],
        "top_3": rankings.get('top_3', []),
        "most_improved": rankings['most_improved'],
        "best_attendance": rankings['best_attendance'],
        "most_consistent": rankings.get('most_consistent')
    })


# ─── Student Doubt Discussion Community API Routes ─────────────────────────

UPLOAD_DOUBT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads', 'doubts')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

@student_bp.route('/student/api/doubts/create', methods=['POST'])
def create_doubt_api():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized. Please log in as a student."}), 401

    title = request.form.get('title', '').strip()
    subject = request.form.get('subject', 'Other').strip()
    description = request.form.get('description', '').strip()
    code = request.form.get('code', '').strip()

    if not title or len(title) < 3:
        return jsonify({"success": False, "error": "Question title must be at least 3 characters long."}), 400
    if not description or len(description) < 5:
        return jsonify({"success": False, "error": "Question description must be at least 5 characters long."}), 400

    image_url = ''
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '':
            if not allowed_file(file.filename):
                return jsonify({"success": False, "error": "Invalid image format. Allowed formats: PNG, JPG, JPEG, GIF, WEBP."}), 400
            
            # 5MB file size check
            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            file.seek(0)
            if file_length > 5 * 1024 * 1024:
                return jsonify({"success": False, "error": "Image file size exceeds limit (Max 5MB)."}), 400

            os.makedirs(UPLOAD_DOUBT_FOLDER, exist_ok=True)
            ext = file.filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            save_path = os.path.join(UPLOAD_DOUBT_FOLDER, unique_filename)
            file.save(save_path)
            image_url = f"/static/uploads/doubts/{unique_filename}"

    doubt_id = execute_query("""
        INSERT INTO doubts (student_id, title, subject, description, code, image_path, status)
        VALUES (?, ?, ?, ?, ?, ?, 'Unanswered')
    """, (student_id, title, subject, description, code, image_url), commit=True)

    return jsonify({
        "success": True,
        "message": "Your doubt has been posted successfully!",
        "doubt_id": doubt_id
    })

@student_bp.route('/student/api/doubts', methods=['GET'])
def get_doubts_api():
    student_id = session.get('student_id')
    query = request.args.get('q', '').strip()
    subject_filter = request.args.get('subject', 'All').strip()
    status_filter = request.args.get('filter', 'All').strip()

    sql = """
        SELECT d.*, 
               s.name AS student_name, 
               s.department AS student_dept, 
               s.current_semester AS student_sem,
               s.section AS student_section,
               (SELECT COUNT(*) FROM answers a WHERE a.doubt_id = d.id) AS answer_count,
               (SELECT COUNT(*) FROM doubt_likes dl WHERE dl.doubt_id = d.id) AS like_count,
               (SELECT COUNT(*) FROM doubt_likes dl WHERE dl.doubt_id = d.id AND dl.student_id = ?) AS user_liked
        FROM doubts d
        JOIN students s ON d.student_id = s.id
        WHERE 1=1
    """
    params = [student_id or 0]

    if query:
        sql += " AND (d.title LIKE ? OR d.description LIKE ? OR d.subject LIKE ? OR d.code LIKE ?)"
        pattern = f"%{query}%"
        params.extend([pattern, pattern, pattern, pattern])

    if subject_filter and subject_filter != 'All':
        sql += " AND d.subject = ?"
        params.append(subject_filter)

    if status_filter == 'Unanswered':
        sql += " AND (SELECT COUNT(*) FROM answers a WHERE a.doubt_id = d.id) = 0"
    elif status_filter == 'Answered':
        sql += " AND d.status = 'Answered'"
    elif status_filter == 'Solved':
        sql += " AND d.status = 'Solved'"
    elif status_filter == 'My Doubts':
        if not student_id:
            return jsonify({"success": False, "error": "Please log in to view your doubts."}), 401
        sql += " AND d.student_id = ?"
        params.append(student_id)

    sql += " ORDER BY d.created_at DESC"

    doubts = execute_query(sql, tuple(params), fetchall=True) or []
    return jsonify({
        "success": True,
        "doubts": doubts
    })

@student_bp.route('/student/api/doubts/<int:doubt_id>', methods=['GET'])
def get_doubt_detail_api(doubt_id):
    student_id = session.get('student_id')

    sql_doubt = """
        SELECT d.*, 
               s.name AS student_name, 
               s.department AS student_dept, 
               s.current_semester AS student_sem,
               s.section AS student_section,
               (SELECT COUNT(*) FROM doubt_likes dl WHERE dl.doubt_id = d.id) AS like_count,
               (SELECT COUNT(*) FROM doubt_likes dl WHERE dl.doubt_id = d.id AND dl.student_id = ?) AS user_liked
        FROM doubts d
        JOIN students s ON d.student_id = s.id
        WHERE d.id = ?
    """
    doubt = execute_query(sql_doubt, (student_id or 0, doubt_id), fetchone=True)
    if not doubt:
        return jsonify({"success": False, "error": "Doubt not found."}), 404

    sql_answers = """
        SELECT a.*, 
               s.name AS student_name, 
               s.department AS student_dept, 
               s.current_semester AS student_sem,
               (SELECT COUNT(*) FROM answer_likes al WHERE al.answer_id = a.id) AS like_count,
               (SELECT COUNT(*) FROM answer_likes al WHERE al.answer_id = a.id AND al.student_id = ?) AS user_liked
        FROM answers a
        JOIN students s ON a.student_id = s.id
        WHERE a.doubt_id = ?
        ORDER BY a.is_accepted DESC, a.created_at ASC
    """
    answers = execute_query(sql_answers, (student_id or 0, doubt_id), fetchall=True) or []

    for ans in answers:
        sql_replies = """
            SELECT r.*, 
                   s.name AS student_name, 
                   s.department AS student_dept, 
                   s.current_semester AS student_sem
            FROM replies r
            JOIN students s ON r.student_id = s.id
            WHERE r.answer_id = ?
            ORDER BY r.created_at ASC
        """
        ans['replies'] = execute_query(sql_replies, (ans['id'],), fetchall=True) or []

    is_owner = (student_id is not None and student_id == doubt['student_id'])

    return jsonify({
        "success": True,
        "doubt": doubt,
        "answers": answers,
        "is_owner": is_owner
    })

@student_bp.route('/student/api/doubts/<int:doubt_id>/answer', methods=['POST'])
def post_answer_api(doubt_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized. Please log in as a student."}), 401

    data = request.get_json() or {}
    answer_text = data.get('answer_text', '').strip()
    if not answer_text or len(answer_text) < 2:
        return jsonify({"success": False, "error": "Answer cannot be empty."}), 400

    doubt = execute_query("SELECT * FROM doubts WHERE id=?", (doubt_id,), fetchone=True)
    if not doubt:
        return jsonify({"success": False, "error": "Doubt not found."}), 404

    answer_id = execute_query("""
        INSERT INTO answers (doubt_id, student_id, answer_text)
        VALUES (?, ?, ?)
    """, (doubt_id, student_id, answer_text), commit=True)

    if doubt['status'] == 'Unanswered':
        execute_query("UPDATE doubts SET status='Answered', updated_at=CURRENT_TIMESTAMP WHERE id=?", (doubt_id,), commit=True)

    return jsonify({
        "success": True,
        "message": "Answer posted successfully!",
        "answer_id": answer_id
    })

@student_bp.route('/student/api/answers/<int:answer_id>/reply', methods=['POST'])
def post_reply_api(answer_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized. Please log in as a student."}), 401

    data = request.get_json() or {}
    reply_text = data.get('reply_text', '').strip()
    if not reply_text:
        return jsonify({"success": False, "error": "Reply text cannot be empty."}), 400

    answer = execute_query("SELECT * FROM answers WHERE id=?", (answer_id,), fetchone=True)
    if not answer:
        return jsonify({"success": False, "error": "Answer not found."}), 404

    reply_id = execute_query("""
        INSERT INTO replies (answer_id, student_id, reply_text)
        VALUES (?, ?, ?)
    """, (answer_id, student_id, reply_text), commit=True)

    return jsonify({
        "success": True,
        "message": "Reply posted successfully!",
        "reply_id": reply_id
    })

@student_bp.route('/student/api/doubts/<int:doubt_id>/like', methods=['POST'])
def like_doubt_api(doubt_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized. Please log in as a student."}), 401

    existing = execute_query("SELECT * FROM doubt_likes WHERE doubt_id=? AND student_id=?", (doubt_id, student_id), fetchone=True)
    if existing:
        execute_query("DELETE FROM doubt_likes WHERE doubt_id=? AND student_id=?", (doubt_id, student_id), commit=True)
        liked = False
    else:
        execute_query("INSERT INTO doubt_likes (doubt_id, student_id) VALUES (?, ?)", (doubt_id, student_id), commit=True)
        liked = True

    like_count = execute_query("SELECT COUNT(*) AS cnt FROM doubt_likes WHERE doubt_id=?", (doubt_id,), fetchone=True)['cnt']
    return jsonify({
        "success": True,
        "liked": liked,
        "like_count": like_count
    })

@student_bp.route('/student/api/answers/<int:answer_id>/like', methods=['POST'])
def like_answer_api(answer_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized. Please log in as a student."}), 401

    existing = execute_query("SELECT * FROM answer_likes WHERE answer_id=? AND student_id=?", (answer_id, student_id), fetchone=True)
    if existing:
        execute_query("DELETE FROM answer_likes WHERE answer_id=? AND student_id=?", (answer_id, student_id), commit=True)
        liked = False
    else:
        execute_query("INSERT INTO answer_likes (answer_id, student_id) VALUES (?, ?)", (answer_id, student_id), commit=True)
        liked = True

    like_count = execute_query("SELECT COUNT(*) AS cnt FROM answer_likes WHERE answer_id=?", (answer_id,), fetchone=True)['cnt']
    return jsonify({
        "success": True,
        "liked": liked,
        "like_count": like_count
    })

@student_bp.route('/student/api/answers/<int:answer_id>/accept', methods=['POST'])
def accept_answer_api(answer_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized. Please log in as a student."}), 401

    answer = execute_query("SELECT * FROM answers WHERE id=?", (answer_id,), fetchone=True)
    if not answer:
        return jsonify({"success": False, "error": "Answer not found."}), 404

    doubt = execute_query("SELECT * FROM doubts WHERE id=?", (answer['doubt_id'],), fetchone=True)
    if not doubt:
        return jsonify({"success": False, "error": "Associated doubt not found."}), 404

    if doubt['student_id'] != student_id:
        return jsonify({"success": False, "error": "Security Error: Only the student who asked this doubt can mark an answer as accepted."}), 403

    # Reset all accepted answers for this doubt
    execute_query("UPDATE answers SET is_accepted=0 WHERE doubt_id=?", (doubt['id'],), commit=True)
    
    # Mark target answer as accepted
    execute_query("UPDATE answers SET is_accepted=1 WHERE id=?", (answer_id,), commit=True)
    
    # Update doubt status to Solved
    execute_query("UPDATE doubts SET status='Solved', updated_at=CURRENT_TIMESTAMP WHERE id=?", (doubt['id'],), commit=True)

    return jsonify({
        "success": True,
        "message": "Answer marked as accepted solution!"
    })

@student_bp.route('/student/api/doubts/<int:doubt_id>', methods=['DELETE'])
def delete_doubt_api(doubt_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized."}), 401

    doubt = execute_query("SELECT * FROM doubts WHERE id=?", (doubt_id,), fetchone=True)
    if not doubt:
        return jsonify({"success": False, "error": "Doubt not found."}), 404

    if doubt['student_id'] != student_id:
        return jsonify({"success": False, "error": "Forbidden: You can only delete your own questions."}), 403

    execute_query("DELETE FROM doubts WHERE id=?", (doubt_id,), commit=True)
    return jsonify({"success": True, "message": "Question deleted successfully."})

@student_bp.route('/student/api/answers/<int:answer_id>', methods=['DELETE'])
def delete_answer_api(answer_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized."}), 401

    answer = execute_query("SELECT * FROM answers WHERE id=?", (answer_id,), fetchone=True)
    if not answer:
        return jsonify({"success": False, "error": "Answer not found."}), 404

    if answer['student_id'] != student_id:
        return jsonify({"success": False, "error": "Forbidden: You can only delete your own answers."}), 403

    execute_query("DELETE FROM answers WHERE id=?", (answer_id,), commit=True)
    return jsonify({"success": True, "message": "Answer deleted successfully."})


# ─── TEACHER-STUDENT PRIVATE COMMUNICATION ENDPOINTS ───────────────────────

VALID_MESSAGE_CATEGORIES = [
    "IA Marks",
    "Subject Marks",
    "Attendance",
    "CGPA / Academic Performance",
    "Risk Level",
    "Performance Prediction",
    "Placement Readiness",
    "Teacher Remark",
    "Other"
]

def get_assigned_teacher_for_student(student):
    """
    Find assigned Class Teacher for a student based on department, semester, and section.
    """
    dept = student.get('department') or 'CSE'
    sem = student.get('current_semester') or student.get('semester') or 6
    sec = student.get('section') or 'A'

    teacher = execute_query(
        "SELECT login_id, name, department, semester, section FROM users WHERE role='Class Teacher' AND department=? AND semester=? AND section=? AND account_status='Active'",
        (dept, sem, sec), fetchone=True
    )
    if not teacher:
        teacher = execute_query(
            "SELECT login_id, name, department, semester, section FROM users WHERE role='Class Teacher' AND department=? AND semester=? AND account_status='Active'",
            (dept, sem), fetchone=True
        )
    if not teacher:
        teacher = execute_query(
            "SELECT login_id, name, department, semester, section FROM users WHERE role IN ('Class Teacher', 'Teacher') AND department=? AND account_status='Active'",
            (dept,), fetchone=True
        )
    if not teacher:
        t_rec = execute_query("SELECT teacher_id as login_id, name, department FROM teachers WHERE department=?", (dept,), fetchone=True)
        if t_rec:
            teacher = t_rec

    if teacher:
        return {
            "teacher_id": teacher['login_id'],
            "name": teacher['name']
        }
    
    return {
        "teacher_id": f"{dept}{sem}{sec}01",
        "name": f"Class Teacher ({dept} Sem {sem}{sec})"
    }


@student_bp.route('/student/api/conversations/create', methods=['POST'])
def create_student_conversation():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized. Please log in as student."}), 401

    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student account not found."}), 404

    data = request.get_json() or {}
    topic = data.get('topic', '').strip()
    category = data.get('category', '').strip()
    message = data.get('message', '').strip()
    context_data = data.get('context_data', {})

    if not topic or not category or not message:
        return jsonify({"success": False, "error": "Topic, Category, and Message are required."}), 400

    if category not in VALID_MESSAGE_CATEGORIES:
        return jsonify({"success": False, "error": f"Invalid category. Allowed: {', '.join(VALID_MESSAGE_CATEGORIES)}"}), 400

    if len(topic) > 255:
        return jsonify({"success": False, "error": "Topic cannot exceed 255 characters."}), 400

    if len(message) > 5000:
        return jsonify({"success": False, "error": "Message cannot exceed 5000 characters."}), 400

    teacher_info = get_assigned_teacher_for_student(student)
    teacher_id = teacher_info['teacher_id']
    context_json = json.dumps(context_data) if isinstance(context_data, (dict, list)) else str(context_data)

    conv_id = execute_query("""
        INSERT INTO teacher_student_messages (student_id, teacher_id, category, topic, context_data, status)
        VALUES (?, ?, ?, ?, ?, 'Open')
    """, (student_id, teacher_id, category, topic, context_json), commit=True)

    execute_query("""
        INSERT INTO teacher_student_replies (conversation_id, sender_id, sender_role, sender_name, message, read_status)
        VALUES (?, ?, 'Student', ?, ?, 0)
    """, (conv_id, str(student_id), student['name'], message), commit=True)

    return jsonify({
        "success": True,
        "conversation_id": conv_id,
        "assigned_teacher": teacher_info['name'],
        "message": f"Message sent to your assigned Class Teacher ({teacher_info['name']})!"
    })


@student_bp.route('/student/api/conversations', methods=['GET'])
def get_student_conversations():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized. Please log in."}), 401

    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student not found."}), 404

    teacher_info = get_assigned_teacher_for_student(student)

    rows = execute_query("""
        SELECT * FROM teacher_student_messages
        WHERE student_id=?
        ORDER BY updated_at DESC
    """, (student_id,), fetchall=True) or []

    conversations = []
    unread_total = 0

    for r in rows:
        conv_id = r['id']

        # Get unread teacher replies count
        unread_row = execute_query("""
            SELECT COUNT(*) as cnt FROM teacher_student_replies
            WHERE conversation_id=? AND sender_role='Teacher' AND read_status=0
        """, (conv_id,), fetchone=True)
        unread_cnt = unread_row['cnt'] if unread_row else 0
        unread_total += unread_cnt

        # Get latest message snippet
        last_reply = execute_query("""
            SELECT sender_role, sender_name, message, created_at FROM teacher_student_replies
            WHERE conversation_id=?
            ORDER BY id DESC LIMIT 1
        """, (conv_id,), fetchone=True)

        context_obj = {}
        try:
            if r.get('context_data'):
                context_obj = json.loads(r['context_data'])
        except Exception:
            context_obj = {}

        conversations.append({
            "id": r['id'],
            "student_id": r['student_id'],
            "teacher_id": r['teacher_id'],
            "teacher_name": teacher_info['name'],
            "category": r['category'],
            "topic": r['topic'],
            "context_data": context_obj,
            "status": r['status'],
            "unread_count": unread_cnt,
            "created_at": r['created_at'],
            "updated_at": r['updated_at'],
            "last_message": last_reply['message'] if last_reply else '',
            "last_sender": last_reply['sender_name'] if last_reply else '',
            "last_sender_role": last_reply['sender_role'] if last_reply else ''
        })

    return jsonify({
        "success": True,
        "assigned_teacher": teacher_info['name'],
        "unread_total": unread_total,
        "conversations": conversations
    })


@student_bp.route('/student/api/conversations/<int:conv_id>', methods=['GET'])
def get_student_conversation_detail(conv_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized."}), 401

    conv = execute_query("SELECT * FROM teacher_student_messages WHERE id=? AND student_id=?", (conv_id, student_id), fetchone=True)
    if not conv:
        return jsonify({"success": False, "error": "Conversation not found or access denied."}), 404

    # Mark teacher replies as read
    execute_query("""
        UPDATE teacher_student_replies
        SET read_status=1
        WHERE conversation_id=? AND sender_role='Teacher'
    """, (conv_id,), commit=True)

    replies = execute_query("""
        SELECT * FROM teacher_student_replies
        WHERE conversation_id=?
        ORDER BY id ASC
    """, (conv_id,), fetchall=True) or []

    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    teacher_info = get_assigned_teacher_for_student(student) if student else {"name": "Class Teacher"}

    context_obj = {}
    try:
        if conv.get('context_data'):
            context_obj = json.loads(conv['context_data'])
    except Exception:
        context_obj = {}

    return jsonify({
        "success": True,
        "conversation": {
            "id": conv['id'],
            "category": conv['category'],
            "topic": conv['topic'],
            "status": conv['status'],
            "teacher_name": teacher_info['name'],
            "context_data": context_obj,
            "created_at": conv['created_at'],
            "updated_at": conv['updated_at']
        },
        "replies": replies
    })


@student_bp.route('/student/api/conversations/<int:conv_id>/reply', methods=['POST'])
def send_student_reply(conv_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized."}), 401

    conv = execute_query("SELECT * FROM teacher_student_messages WHERE id=? AND student_id=?", (conv_id, student_id), fetchone=True)
    if not conv:
        return jsonify({"success": False, "error": "Conversation not found or access denied."}), 404

    student = execute_query("SELECT name FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student account not found."}), 404

    data = request.get_json() or {}
    message = data.get('message', '').strip()

    if not message:
        return jsonify({"success": False, "error": "Reply message cannot be empty."}), 400

    if len(message) > 5000:
        return jsonify({"success": False, "error": "Reply cannot exceed 5000 characters."}), 400

    execute_query("""
        INSERT INTO teacher_student_replies (conversation_id, sender_id, sender_role, sender_name, message, read_status)
        VALUES (?, ?, 'Student', ?, ?, 0)
    """, (conv_id, str(student_id), student['name'], message), commit=True)

    new_status = 'Open' if conv['status'] == 'Resolved' else conv['status']
    execute_query("""
        UPDATE teacher_student_messages
        SET status=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (new_status, conv_id), commit=True)

    return jsonify({"success": True, "message": "Reply sent successfully."})


@student_bp.route('/student/api/conversations/<int:conv_id>/resolve', methods=['POST'])
def resolve_student_conversation(conv_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized."}), 401

    conv = execute_query("SELECT id FROM teacher_student_messages WHERE id=? AND student_id=?", (conv_id, student_id), fetchone=True)
    if not conv:
        return jsonify({"success": False, "error": "Conversation not found or access denied."}), 404

    execute_query("""
        UPDATE teacher_student_messages
        SET status='Resolved', updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (conv_id,), commit=True)

    return jsonify({"success": True, "message": "Conversation marked as resolved."})


@student_bp.route('/student/api/conversations/<int:conv_id>/reopen', methods=['POST'])
def reopen_student_conversation(conv_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"success": False, "error": "Unauthorized."}), 401

    conv = execute_query("SELECT id FROM teacher_student_messages WHERE id=? AND student_id=?", (conv_id, student_id), fetchone=True)
    if not conv:
        return jsonify({"success": False, "error": "Conversation not found or access denied."}), 404

    execute_query("""
        UPDATE teacher_student_messages
        SET status='Open', updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (conv_id,), commit=True)

    return jsonify({"success": True, "message": "Conversation reopened."})


