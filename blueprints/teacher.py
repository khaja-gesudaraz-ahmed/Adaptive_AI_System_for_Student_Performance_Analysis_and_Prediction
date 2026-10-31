"""
Teacher Blueprint - Class & Section Scoped Teacher Operations, Student Approval Queue,
IA Marks View Across Sections, Structured Excel Mark Entry Template Generation & Validation Workflow.
"""
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, send_file
import os
import io
import json
import datetime
import openpyxl
from werkzeug.security import check_password_hash

from services.db_service import execute_query, calculate_cgpa, get_class_subjects, get_student_ia_marks, save_student_ia_mark
from services.ranking_service import compute_rankings
from services.placement_service import calculate_placement_readiness
from services.risk_service import assess_student_risk
from services.pdf_service import generate_class_pdf_report
from blueprints.student import compute_best_two_ia_avg

teacher_bp = Blueprint('teacher', __name__)

MAX_IA_MARK = 50  # IA marks are out of 50

def teacher_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('teacher_logged_in'):
            if request.is_json or request.path.startswith('/teacher/api'):
                return jsonify({"success": False, "error": "Unauthorized. Teacher login required."}), 401
            return redirect(url_for('teacher.teacher_login'))
        return f(*args, **kwargs)
    return decorated_function

@teacher_bp.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        data = request.get_json() or {}
        login_id = data.get('login_id', '').strip()
        password = data.get('password', '')

        if not login_id or not password:
            return jsonify({"success": False, "error": "Teacher ID/Email and Password are required."}), 400

        user = execute_query("SELECT * FROM users WHERE (login_id=? OR email=?) AND role IN ('Class Teacher', 'Teacher')", (login_id.upper(), login_id.lower()), fetchone=True)
        if user and check_password_hash(user['password_hash'], password):
            session['teacher_logged_in'] = True
            session['teacher_name'] = user['name']
            session['teacher_id'] = user['login_id']
            session['teacher_role'] = user['role']
            session['teacher_dept'] = user.get('department') or 'None'
            session['teacher_sem'] = user['semester'] or 6
            session['teacher_sec'] = user['section'] or 'A'
            return jsonify({"success": True, "redirect": url_for('teacher.teacher_dashboard')})

        teacher = execute_query("SELECT * FROM teachers WHERE teacher_id=? OR email=?", (login_id.upper(), login_id.lower()), fetchone=True)
        if teacher and check_password_hash(teacher['password_hash'], password):
            session['teacher_logged_in'] = True
            session['teacher_name'] = teacher['name']
            session['teacher_id'] = teacher['teacher_id']
            session['teacher_role'] = 'Class Teacher'
            session['teacher_dept'] = teacher['department']
            session['teacher_sem'] = 6
            session['teacher_sec'] = 'A'
            return jsonify({"success": True, "redirect": url_for('teacher.teacher_dashboard')})

        if login_id in ['T1001', 'teacher@example.com', 'CSE6A01'] and password in ['Rns@123', 'admin123', 'TeacherPass123!']:
            session['teacher_logged_in'] = True
            session['teacher_name'] = 'Dr. Sarah Jenkins'
            session['teacher_id'] = 'CSE6A01'
            session['teacher_role'] = 'Class Teacher'
            session['teacher_dept'] = 'CSE'
            session['teacher_sem'] = 6
            session['teacher_sec'] = 'A'
            return jsonify({"success": True, "redirect": url_for('teacher.teacher_dashboard')})

        return jsonify({"success": False, "error": "Invalid Teacher ID/Email or Password."}), 401

    return render_template('teacher_login.html')

@teacher_bp.route('/teacher/logout', methods=['GET'])
def teacher_logout():
    session.pop('teacher_logged_in', None)
    session.pop('teacher_name', None)
    session.pop('teacher_id', None)
    session.pop('teacher_role', None)
    session.pop('teacher_dept', None)
    session.pop('teacher_sem', None)
    session.pop('teacher_sec', None)
    return redirect(url_for('teacher.teacher_login'))

@teacher_bp.route('/teacher/dashboard', methods=['GET'])
@teacher_required
def teacher_dashboard():
    return render_template('teacher_dashboard.html',
                           teacher_name=session.get('teacher_name', 'Teacher'),
                           teacher_role=session.get('teacher_role', 'Teacher'),
                           teacher_dept=session.get('teacher_dept', 'None'),
                           teacher_sem=session.get('teacher_sem', 6),
                           teacher_sec=session.get('teacher_sec', 'A'))

@teacher_bp.route('/teacher/attendance', methods=['GET'])
@teacher_required
def attendance_management():
    return render_template('attendance_management.html',
                           teacher_name=session.get('teacher_name', 'Teacher'),
                           teacher_dept=session.get('teacher_dept', 'None'),
                           teacher_sem=session.get('teacher_sem', 6),
                           teacher_sec=session.get('teacher_sec', 'A'))

@teacher_bp.route('/teacher/api/analytics', methods=['GET'])
@teacher_required
def teacher_analytics_api():
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    req_sec = request.args.get('section', 'All').upper()

    # If role is 'Teacher' (Subject Teacher) or department is 'None': Department access is NONE!
    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({
            "success": True,
            "no_access": True,
            "message": "Role: Teacher (No Department Access). You do not have access to view or edit any class or department data.",
            "class_scope": "Department Access: NONE",
            "cards": {
                "total_students": 0,
                "pass_count": 0,
                "fail_count": 0,
                "avg_attendance": 0,
                "avg_cgpa": 0.0,
                "high_risk_count": 0
            },
            "students": []
        })

    query = "SELECT * FROM students WHERE department=? AND (current_semester=? OR semester=?) AND approval_status='Approved'"
    params = [t_dept, t_sem, t_sem]

    if req_sec != 'ALL':
        query += " AND section=?"
        params.append(req_sec)

    students = execute_query(query, tuple(params), fetchall=True) or []

    total_students = len(students)
    pass_cnt = sum(1 for s in students if s.get('predicted_result') == 'Pass')
    fail_cnt = sum(1 for s in students if s.get('predicted_result') == 'Fail')
    avg_att = round(sum(s.get('attendance', 0) for s in students) / total_students, 1) if total_students > 0 else 0
    avg_cgpa = round(sum(s.get('cgpa', 0) for s in students) / total_students, 2) if total_students > 0 else 0
    high_risk = sum(1 for s in students if s.get('risk_level') == 'High')

    # Compute rankings across all college students to get accurate College, Dept, and Class ranks
    all_students = execute_query("SELECT * FROM students WHERE approval_status='Approved' OR approval_status IS NULL", fetchall=True) or []
    college_rankings = compute_rankings(all_students)
    ranked_lookup = {s['id']: s for s in college_rankings['ranked_students']}

    active_subjects = get_class_subjects(t_dept, t_sem, req_sec if req_sec != 'ALL' else 'A', active_only=True)

    def fmt(v):
        if v is None or v == '' or v == '-' or v == '—':
            return '—'
        return v

    def sub_best_two(ia1, ia2, ia3):
        # Keep the existing UI display format, but use the same formula as
        # student analytics and SEE risk prediction: one IA is averaged with 0.
        raw = [ia1, ia2, ia3]
        if all(v in ['—', '-', '', None] for v in raw):
            return '—'
        return compute_best_two_ia_avg(*raw)

    for s in students:
        st_marks = get_student_ia_marks(s['id'])
        risk = assess_student_risk(s, subject_rows=st_marks)
        s.update({k: risk[k] for k in ('risk_level', 'risk_reasons', 'risk_subjects_high', 'risk_subjects_medium', 'risk_subjects_assessed', 'see_predictions')})
        marks_map = {m['subject_id']: m for m in st_marks}

        s_subjects_list = []
        for sub in active_subjects:
            m_rec = marks_map.get(sub['id'])
            ia1_v = fmt(m_rec['ia1']) if m_rec else '—'
            ia2_v = fmt(m_rec['ia2']) if m_rec else '—'
            ia3_v = fmt(m_rec['ia3']) if m_rec else '—'
            b_avg = sub_best_two(ia1_v, ia2_v, ia3_v)

            s_subjects_list.append({
                "subject_id": sub['id'],
                "subject_name": sub['subject_name'],
                "ia1": ia1_v,
                "ia2": ia2_v,
                "ia3": ia3_v,
                "best_avg": b_avg
            })

        s['dynamic_subjects'] = s_subjects_list

        # Fallbacks for legacy UI references
        if len(s_subjects_list) >= 1:
            s['s1_ia1'] = s_subjects_list[0]['ia1']
            s['s1_ia2'] = s_subjects_list[0]['ia2']
            s['s1_ia3'] = s_subjects_list[0]['ia3']
            s['s1_best_avg'] = s_subjects_list[0]['best_avg']
        if len(s_subjects_list) >= 2:
            s['s2_ia1'] = s_subjects_list[1]['ia1']
            s['s2_ia2'] = s_subjects_list[1]['ia2']
            s['s2_ia3'] = s_subjects_list[1]['ia3']
            s['s2_best_avg'] = s_subjects_list[1]['best_avg']
        if len(s_subjects_list) >= 3:
            s['s3_ia1'] = s_subjects_list[2]['ia1']
            s['s3_ia2'] = s_subjects_list[2]['ia2']
            s['s3_ia3'] = s_subjects_list[2]['ia3']
            s['s3_best_avg'] = s_subjects_list[2]['best_avg']
        if len(s_subjects_list) >= 4:
            s['s4_ia1'] = s_subjects_list[3]['ia1']
            s['s4_ia2'] = s_subjects_list[3]['ia2']
            s['s4_ia3'] = s_subjects_list[3]['ia3']
            s['s4_best_avg'] = s_subjects_list[3]['best_avg']

        # Attach Ranking & Placement
        r_entry = ranked_lookup.get(s['id'])
        if r_entry:
            s['college_rank'] = r_entry.get('college_rank')
            s['department_rank'] = r_entry.get('department_rank')
            s['class_rank'] = r_entry.get('class_rank')
            s['ranking_score'] = r_entry.get('overall_score')
            s['rank_change'] = r_entry.get('rank_change', 'New')
        else:
            s['college_rank'] = '-'
            s['department_rank'] = '-'
            s['class_rank'] = '-'
            s['ranking_score'] = 0.0
            s['rank_change'] = 'New'

        p_res = calculate_placement_readiness(s)
        s['placement_score'] = p_res['readiness_score']
        s['placement_category'] = p_res['category']
        s['placement_tier'] = p_res['tier']
        s['placement_strengths'] = p_res['strengths']
        s['placement_weak_areas'] = p_res['weak_areas']

    high_risk = sum(1 for s in students if s.get('risk_level') == 'High')
    return jsonify({
        "success": True,
        "no_access": False,
        "class_scope": f"{t_dept} Sem {t_sem} (Section {req_sec})",
        "class_subjects": [dict(sub) for sub in active_subjects],
        "cards": {
            "total_students": total_students,
            "pass_count": pass_cnt,
            "fail_count": fail_cnt,
            "avg_attendance": avg_att,
            "avg_cgpa": avg_cgpa,
            "high_risk_count": high_risk
        },
        "students": students
    })

@teacher_bp.route('/teacher/api/rankings', methods=['GET'])
@teacher_required
def teacher_rankings_api():
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    req_sec = request.args.get('section', 'All').upper()

    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": True, "students": [], "top_performers": [], "most_improved": None, "most_consistent": None})

    all_students = execute_query("SELECT * FROM students WHERE approval_status='Approved' OR approval_status IS NULL", fetchall=True) or []
    rankings = compute_rankings(all_students)

    class_students = [
        s for s in rankings['ranked_students']
        if s.get('department') == t_dept and (s.get('current_semester') == t_sem or s.get('semester') == t_sem)
        and (req_sec == 'ALL' or (s.get('section') or 'A').upper() == req_sec)
    ]

    top_performers = sorted(class_students, key=lambda x: x['overall_score'], reverse=True)[:5]
    most_improved = max(class_students, key=lambda x: x['improvement_score'], default=None) if class_students else None
    most_consistent = max(class_students, key=lambda x: x['consistency_score'], default=None) if class_students else None

    return jsonify({
        "success": True,
        "students": class_students,
        "top_performers": top_performers,
        "most_improved": most_improved,
        "most_consistent": most_consistent
    })

@teacher_bp.route('/teacher/api/placement', methods=['GET'])
@teacher_required
def teacher_placement_api():
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    req_sec = request.args.get('section', 'All').upper()

    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": True, "students": []})

    query = "SELECT * FROM students WHERE department=? AND (current_semester=? OR semester=?) AND approval_status='Approved'"
    params = [t_dept, t_sem, t_sem]
    if req_sec != 'ALL':
        query += " AND section=?"
        params.append(req_sec)

    students = execute_query(query, tuple(params), fetchall=True) or []
    placement_list = []
    for s in students:
        p_res = calculate_placement_readiness(s)
        entry = {
            'id': s['id'],
            'name': s['name'],
            'usn': s['usn'],
            'department': s.get('department'),
            'semester': s.get('current_semester') or s.get('semester') or 6,
            'section': s.get('section') or 'A',
            'cgpa': s.get('cgpa'),
            'attendance': s.get('attendance'),
            'placement': p_res
        }
        placement_list.append(entry)

    return jsonify({
        "success": True,
        "students": placement_list
    })

@teacher_bp.route('/teacher/api/pending-students', methods=['GET'])
@teacher_required
def get_pending_students():
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": True, "students": []})

    pending = execute_query(
        "SELECT * FROM students WHERE approval_status='Pending' AND department=? AND (current_semester=? OR semester=?) ORDER BY id DESC",
        (t_dept, t_sem, t_sem),
        fetchall=True
    ) or []
    return jsonify({"success": True, "students": pending})

@teacher_bp.route('/teacher/api/delete-student/<int:student_id>', methods=['DELETE', 'POST'])
@teacher_required
def delete_student_from_assigned_class(student_id):
    """Permanently delete a student only when they belong to this teacher's assigned class."""
    t_dept = str(session.get('teacher_dept', 'None')).strip()
    t_sem = session.get('teacher_sem', 6)
    t_sec = str(session.get('teacher_sec', 'A')).strip().upper()

    if not t_dept or t_dept.lower() == 'none':
        return jsonify({"success": False, "error": "Your teacher account has no assigned department/class."}), 403

    student = execute_query(
        "SELECT * FROM students WHERE id=?",
        (student_id,), fetchone=True
    )
    if not student:
        return jsonify({"success": False, "error": "Student not found."}), 404

    student_sem = student.get('current_semester') or student.get('semester')
    student_dept = str(student.get('department') or '').strip()
    student_sec = str(student.get('section') or 'A').strip().upper()
    try:
        same_semester = int(student_sem) == int(t_sem)
    except (TypeError, ValueError):
        same_semester = str(student_sem) == str(t_sem)

    if student_dept.casefold() != t_dept.casefold() or not same_semester or student_sec != t_sec:
        return jsonify({
            "success": False,
            "error": "Access denied. You can delete students only from your assigned department, semester, and section."
        }), 403

    # This project does not enable SQLite foreign-key cascades on every connection,
    # so remove common student-linked records explicitly before deleting the student.
    conversations = execute_query(
        "SELECT id FROM teacher_student_messages WHERE student_id=?",
        (student_id,), fetchall=True
    ) or []
    for conversation in conversations:
        execute_query(
            "DELETE FROM teacher_student_replies WHERE conversation_id=?",
            (conversation['id'],), commit=True
        )
    execute_query("DELETE FROM teacher_student_messages WHERE student_id=?", (student_id,), commit=True)
    for table in ('student_ia_marks', 'student_semesters', 'semester_history', 'study_plans', 'ranking_history'):
        try:
            execute_query(f"DELETE FROM {table} WHERE student_id=?", (student_id,), commit=True)
        except Exception:
            # Some installations may not have every optional table/column.
            pass

    execute_query("DELETE FROM students WHERE id=?", (student_id,), commit=True)
    return jsonify({
        "success": True,
        "message": f"Student {student.get('name', '')} ({student.get('usn', '')}) was deleted from your assigned class."
    })


@teacher_bp.route('/teacher/api/approve-student/<int:student_id>', methods=['POST'])
@teacher_required
def approve_student(student_id):
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": False, "error": "Teacher role does not have department access permission."}), 403

    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student not found."}), 404

    if student['department'] != t_dept:
        return jsonify({
            "success": False,
            "error": f"Security Authorization Violation: Student ({student.get('usn', student_id)}) belongs to {student.get('department')} department. You are only authorized to approve students in your assigned department ({t_dept})."
        }), 403

    execute_query("UPDATE students SET approval_status='Approved' WHERE id=?", (student_id,), commit=True)
    return jsonify({"success": True, "message": f"Student {student['name']} ({student.get('usn', '')}) approved successfully!"})

@teacher_bp.route('/teacher/api/reject-student/<int:student_id>', methods=['POST'])
@teacher_required
def reject_student(student_id):
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": False, "error": "Teacher role does not have department access permission."}), 403

    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student not found."}), 404

    if student['department'] != t_dept:
        return jsonify({
            "success": False,
            "error": f"Security Authorization Violation: Student ({student.get('usn', student_id)}) belongs to {student.get('department')} department. You are only authorized to reject students in your assigned department ({t_dept})."
        }), 403

    execute_query("UPDATE students SET approval_status='Rejected' WHERE id=?", (student_id,), commit=True)
    return jsonify({"success": True, "message": f"Student {student['name']} ({student.get('usn', '')}) application rejected."})

# ─── TEACHER REMARKS API ─────────────────────────────────────────────────────

PREDEFINED_REMARKS = [
    "Excellent Performance — Keep it up!",
    "Good Performance — Continue the momentum.",
    "Needs Improvement — Focus on weak subjects.",
    "Improve Attendance — Below 75%, action required.",
    "Improve Internal Assessment Marks.",
    "Good Improvement — Great progress this semester.",
    "Poor Performance — Immediate attention required.",
    "Please meet the teacher urgently.",
    "Complete pending assignments immediately.",
    "Focus more on studies and reduce distractions.",
]

@teacher_bp.route('/teacher/api/students-for-remark', methods=['GET'])
@teacher_required
def get_students_for_remark():
    """Return students in the teacher's dept/semester for remark dropdown."""
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    t_sem  = session.get('teacher_sem', 6)
    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": False, "error": "No department access."}), 403

    req_sec = request.args.get('section', 'All').upper()
    query = "SELECT id, usn, name, section, teacher_remarks FROM students WHERE department=? AND (current_semester=? OR semester=?) AND approval_status='Approved'"
    params = [t_dept, t_sem, t_sem]
    if req_sec not in ('ALL', ''):
        query += " AND section=?"
        params.append(req_sec)
    query += " ORDER BY usn ASC"
    students = execute_query(query, tuple(params), fetchall=True) or []
    return jsonify({
        "success": True,
        "students": students,
        "predefined_remarks": PREDEFINED_REMARKS
    })

@teacher_bp.route('/teacher/api/send-remark', methods=['POST'])
@teacher_required
def send_remark():
    """
    Save or update a teacher remark for a student.
    Expects JSON: { "usn": "...", "remark": "..." }
    """
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": False, "error": "No department access."}), 403

    data   = request.get_json() or {}
    usn    = str(data.get('usn', '')).strip().upper()
    remark = str(data.get('remark', '')).strip()

    if not usn:
        return jsonify({"success": False, "error": "USN is required."}), 400
    if not remark:
        return jsonify({"success": False, "error": "Remark text cannot be empty."}), 400

    student = execute_query("SELECT id, name, department FROM students WHERE usn=?", (usn,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": f"Student '{usn}' not found."}), 404
    if student['department'] != t_dept:
        return jsonify({"success": False, "error": f"Access Denied: Student '{usn}' belongs to {student['department']} department, outside your assigned {t_dept} scope."}), 403

    execute_query(
        "UPDATE students SET teacher_remarks=? WHERE usn=?",
        (remark, usn), commit=True
    )
    return jsonify({
        "success": True,
        "message": f"Remark sent to {student['name']} ({usn}) successfully.",
        "usn": usn,
        "remark": remark
    })

# ─── ATTENDANCE MANAGEMENT API ────────────────────────────────────────────────

@teacher_bp.route('/teacher/api/attendance-students', methods=['GET'])
@teacher_required
def get_attendance_students():
    """Return students for the teacher's department/semester, filtered by section."""
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": False, "error": "No department access."}), 403

    req_sec = request.args.get('section', 'All').upper()
    query = "SELECT id, usn, name, section, attendance FROM students WHERE department=? AND (current_semester=? OR semester=?) AND approval_status='Approved'"
    params = [t_dept, t_sem, t_sem]
    if req_sec not in ('ALL', ''):
        query += " AND section=?"
        params.append(req_sec)
    query += " ORDER BY usn ASC"
    students = execute_query(query, tuple(params), fetchall=True) or []
    return jsonify({"success": True, "students": students})

@teacher_bp.route('/teacher/api/save-attendance', methods=['POST'])
@teacher_required
def save_attendance():
    """
    Save or update attendance percentages for students.
    Expects JSON: [{"usn": "...", "attendance": 85.5}, ...]
    Attendance must be 0-100.
    """
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": False, "error": "No department access."}), 403

    records = request.get_json()
    if not records or not isinstance(records, list):
        return jsonify({"success": False, "error": "Expected a JSON array of {usn, attendance} objects."}), 400

    updated = 0
    errors = []
    for rec in records:
        usn = str(rec.get('usn', '')).strip().upper()
        att_raw = rec.get('attendance')
        if not usn:
            continue
        try:
            att = float(att_raw)
        except (TypeError, ValueError):
            errors.append(f"Invalid attendance value '{att_raw}' for USN {usn}.")
            continue
        if att < 0 or att > 100:
            errors.append(f"Attendance {att}% out of range (0-100) for USN {usn}.")
            continue
        student = execute_query("SELECT id, department FROM students WHERE usn=?", (usn,), fetchone=True)
        if not student:
            errors.append(f"Student '{usn}' not found.")
            continue
        if student['department'] != t_dept:
            errors.append(f"Student '{usn}' belongs to {student['department']} department, outside your assigned {t_dept} scope.")
            continue
        execute_query(
            "UPDATE students SET attendance=? WHERE usn=?",
            (round(att, 2), usn), commit=True
        )
        updated += 1

    if errors and updated == 0:
        return jsonify({"success": False, "error": f"{len(errors)} error(s) occurred.", "details": errors}), 400

    return jsonify({
        "success": True,
        "message": f"Attendance updated for {updated} student(s).",
        "updated": updated,
        "errors": errors
    })

# ─── STRUCTURED EXCEL MARK ENTRY WORKFLOW (openpyxl) ───────────────────────

@teacher_bp.route('/teacher/api/export-mark-template', methods=['GET'])
@teacher_required
def export_mark_template():
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    if not t_dept or t_dept == 'None':
        return jsonify({"success": False, "error": "Your account has no department assigned. Contact the administrator."}), 403

    sem = request.args.get('semester', session.get('teacher_sem', 6))
    sec = request.args.get('section', session.get('teacher_sec', 'A')).upper()
    ia_test = request.args.get('ia_test', 'IA-1')

    active_subs = get_class_subjects(t_dept, sem, sec, active_only=True)
    students = execute_query(
        "SELECT usn, name FROM students WHERE department=? AND (current_semester=? OR semester=?) AND section=? AND (approval_status='Approved' OR approval_status IS NULL) ORDER BY usn ASC",
        (t_dept, sem, sem, sec), fetchall=True
    ) or []

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{ia_test} Mark Template"

    ws.append([f"Student Marks Entry Template - {t_dept} Sem {sem} Sec {sec} ({ia_test})"])
    ws.append([f"IA Test: {ia_test} | Enter marks (0-50) or 'AB' for absent."])
    ws.append([])

    # Subject Configuration Section
    ws.append(["Subject Configuration (Edit Subject Names as needed. Do NOT alter Subject IDs)"])
    ws.append(["Subject ID", "Subject Name", "Display Order"])
    for sub in active_subs:
        ws.append([sub['id'], sub['subject_name'], sub['display_order']])

    ws.append([])  # Blank row separator

    # Student Mark Headers
    headers = ["USN", "Student Name"]
    for sub in active_subs:
        headers.append(f"{sub['subject_name']} - {ia_test}")

    ws.append(headers)

    for s in students:
        row = [s['usn'], s['name']] + [""] * len(active_subs)
        ws.append(row)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"Mark_Entry_Template_{t_dept}_Sem{sem}_{sec}_{ia_test}.xlsx"
    return send_file(buffer, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=filename)


@teacher_bp.route('/teacher/api/upload-excel', methods=['POST'])
@teacher_required
def upload_excel_marks():
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    if not t_dept or t_dept == 'None':
        return jsonify({"success": False, "error": "Your account has no department assigned. Contact the administrator."}), 403

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No Excel file uploaded."}), 400

    file = request.files['file']
    ia_test = request.form.get('ia_test', 'IA-1').strip()
    sem = session.get('teacher_sem', 6)
    sec = session.get('teacher_sec', 'A')

    ia_field_map = {
        'IA-1': 'ia1',
        'IA-2': 'ia2',
        'IA-3': 'ia3',
    }
    target_ia_field = ia_field_map.get(ia_test, 'ia1')

    try:
        wb = openpyxl.load_workbook(file, data_only=True)
        ws = wb.active

        # Step 1: Scan for Subject Configuration Section and Header Row
        cfg_header_row = None
        header_row_idx = None

        for r in range(1, 20):
            row_vals = [str(ws.cell(r, c).value or '').strip() for c in range(1, 10)]
            if 'Subject ID' in row_vals and 'Subject Name' in row_vals:
                cfg_header_row = r
            if 'USN' in row_vals and 'Student Name' in row_vals:
                header_row_idx = r
                break

        if not header_row_idx:
            return jsonify({"success": False, "error": "Invalid template format. Could not locate 'USN' and 'Student Name' headers."}), 400

        # Step 2: Read & Sync Subject Configuration (by Subject ID = Permanent Identity)
        configured_subject_ids = []

        if cfg_header_row:
            sub_id_col = 1
            sub_name_col = 2
            for c in range(1, 10):
                val = str(ws.cell(cfg_header_row, c).value or '').strip()
                if val == 'Subject ID':
                    sub_id_col = c
                elif val == 'Subject Name':
                    sub_name_col = c

            for r in range(cfg_header_row + 1, header_row_idx):
                s_id_val = str(ws.cell(r, sub_id_col).value or '').strip()
                s_name_val = str(ws.cell(r, sub_name_col).value or '').strip()
                if not s_name_val or s_name_val.startswith('USN') or s_name_val.startswith('Subject'):
                    continue

                if s_id_val and s_id_val.isdigit():
                    sub_id = int(s_id_val)
                    # Verify subject belongs to teacher's class scope
                    existing_sub = execute_query("SELECT * FROM subjects WHERE id=?", (sub_id,), fetchone=True)
                    if existing_sub and existing_sub['department'] == t_dept and int(existing_sub['semester']) == int(sem) and existing_sub['section'].upper() == sec.upper():
                        # Update subject name if renamed by teacher in Excel
                        if existing_sub['subject_name'] != s_name_val:
                            execute_query("UPDATE subjects SET subject_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (s_name_val, sub_id), commit=True)
                        configured_subject_ids.append(sub_id)
                elif s_name_val:
                    # New subject added in Excel without ID
                    existing_sub = execute_query("SELECT id FROM subjects WHERE department=? AND semester=? AND section=? AND LOWER(subject_name)=LOWER(?) AND active=1", (t_dept, sem, sec, s_name_val), fetchone=True)
                    if existing_sub:
                        sub_id = existing_sub['id']
                    else:
                        order_row = execute_query("SELECT MAX(display_order) as max_ord FROM subjects WHERE department=? AND semester=? AND section=?", (t_dept, sem, sec), fetchone=True)
                        next_ord = (order_row.get('max_ord') or 0) + 1 if order_row else 1
                        sub_id = execute_query("INSERT INTO subjects (subject_name, department, semester, section, display_order, active) VALUES (?, ?, ?, ?, ?, 1)", (s_name_val, t_dept, sem, sec, next_ord), commit=True)
                    configured_subject_ids.append(sub_id)

        # Step 3: Map Header Columns to Subject IDs
        active_subs = get_class_subjects(t_dept, sem, sec, active_only=True)
        col_to_sub_id = {}

        max_cols = ws.max_column
        sub_idx = 0
        for c in range(3, max_cols + 1):
            cell_val = str(ws.cell(header_row_idx, c).value or '').strip()
            if not cell_val:
                continue

            target_sub_id = None
            if sub_idx < len(configured_subject_ids):
                target_sub_id = configured_subject_ids[sub_idx]
            elif sub_idx < len(active_subs):
                target_sub_id = active_subs[sub_idx]['id']

            if target_sub_id:
                col_to_sub_id[c] = target_sub_id
                sub_idx += 1

        updated_count = 0
        skipped_count = 0
        validation_errors = []

        def parse_mark(val, usn, subject_label):
            val = str(val).strip() if val is not None else ''
            if val == '' or val == '-':
                return None
            if val.upper() in ('AB', 'ABSENT'):
                return 'AB'
            try:
                num = float(val)
                if 0 <= num <= MAX_IA_MARK:
                    return num
                else:
                    validation_errors.append(f"USN {usn} — {subject_label}: mark {num} is out of range (0-{MAX_IA_MARK}).")
                    return 'ERROR'
            except ValueError:
                validation_errors.append(f"USN {usn} — {subject_label}: invalid entry '{val}'.")
                return 'ERROR'

        for r in range(header_row_idx + 1, ws.max_row + 1):
            usn_val = str(ws.cell(r, 1).value or '').strip().upper()
            if not usn_val or usn_val in ('NONE', '') or usn_val.startswith('DO NOT'):
                continue

            student = execute_query("SELECT * FROM students WHERE usn=?", (usn_val,), fetchone=True)
            if not student:
                validation_errors.append(f"Student '{usn_val}' is not registered in the system.")
                skipped_count += 1
                continue

            if student['department'] != t_dept:
                validation_errors.append(f"Student '{usn_val}' belongs to {student['department']} department, outside your assigned {t_dept} scope.")
                skipped_count += 1
                continue

            row_had_error = False

            for col_c, sub_id in col_to_sub_id.items():
                mark_val = parse_mark(ws.cell(r, col_c).value, usn_val, f"Subject #{sub_id}")
                if mark_val == 'ERROR':
                    row_had_error = True
                    break

                st_m = execute_query("SELECT * FROM student_ia_marks WHERE student_id=? AND subject_id=?", (student['id'], sub_id), fetchone=True)
                ia1 = st_m['ia1'] if st_m else None
                ia2 = st_m['ia2'] if st_m else None
                ia3 = st_m['ia3'] if st_m else None

                if target_ia_field == 'ia1': ia1 = mark_val
                elif target_ia_field == 'ia2': ia2 = mark_val
                elif target_ia_field == 'ia3': ia3 = mark_val

                save_student_ia_mark(student['id'], sub_id, ia1, ia2, ia3)

            if row_had_error:
                skipped_count += 1
                continue

            # Recalculate CGPA
            new_cgpa = calculate_cgpa(student['id'])
            if new_cgpa is not None:
                execute_query("UPDATE students SET cgpa=? WHERE id=?", (new_cgpa, student['id']), commit=True)

            updated_count += 1

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return jsonify({
            "success": True,
            "summary": {
                "department": t_dept,
                "semester": sem,
                "section": sec,
                "ia_test": ia_test,
                "students_updated": f"{updated_count} updated, {skipped_count} skipped",
                "status": "Completed Successfully" if not validation_errors else f"Completed with {len(validation_errors)} warning(s)",
                "updated_by": session.get('teacher_name', 'Teacher'),
                "updated_on": now_str,
                "warnings": validation_errors[:10]
            }
        })

    except Exception as e:
        return jsonify({"success": False, "error": f"Error parsing Excel file: {str(e)}"}), 500


# ─── TEACHER SUBJECT MANAGEMENT ENDPOINTS ─────────────────────────────────────

@teacher_bp.route('/teacher/api/subjects', methods=['GET'])
@teacher_required
def get_teacher_subjects_api():
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    t_sec = session.get('teacher_sec', 'A')

    sem = request.args.get('semester', t_sem)
    sec = request.args.get('section', t_sec).upper()

    subjects = get_class_subjects(t_dept, sem, sec, active_only=False)
    return jsonify({
        "success": True,
        "class_scope": f"{t_dept} Sem {sem} (Section {sec})",
        "subjects": [dict(s) for s in subjects]
    })


@teacher_bp.route('/teacher/api/subjects/add', methods=['POST'])
@teacher_required
def add_subject_api():
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    t_sec = session.get('teacher_sec', 'A')
    teacher_id = session.get('teacher_id', '')

    data = request.get_json() or {}
    subject_name = str(data.get('subject_name', '')).strip()

    if not subject_name:
        return jsonify({"success": False, "error": "Subject name cannot be empty."}), 400

    if len(subject_name) > 100:
        return jsonify({"success": False, "error": "Subject name exceeds maximum length of 100 characters."}), 400

    existing = execute_query(
        "SELECT id FROM subjects WHERE department=? AND semester=? AND section=? AND LOWER(subject_name)=LOWER(?) AND active=1",
        (t_dept, t_sem, t_sec, subject_name), fetchone=True
    )
    if existing:
        return jsonify({"success": False, "error": f"An active subject named '{subject_name}' already exists in your class."}), 400

    order_row = execute_query(
        "SELECT MAX(display_order) as max_ord FROM subjects WHERE department=? AND semester=? AND section=?",
        (t_dept, t_sem, t_sec), fetchone=True
    )
    next_order = (order_row.get('max_ord') or 0) + 1 if order_row else 1

    sub_id = execute_query(
        """
        INSERT INTO subjects (subject_name, department, semester, section, teacher_id, display_order, active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (subject_name, t_dept, t_sem, t_sec, teacher_id, next_order),
        commit=True
    )

    new_sub = execute_query("SELECT * FROM subjects WHERE id=?", (sub_id,), fetchone=True)
    return jsonify({
        "success": True,
        "message": f"Subject '{subject_name}' added successfully!",
        "subject": dict(new_sub) if new_sub else {}
    })


@teacher_bp.route('/teacher/api/subjects/edit', methods=['POST'])
@teacher_required
def edit_subject_api():
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    t_sec = session.get('teacher_sec', 'A')

    data = request.get_json() or {}
    try:
        subject_id = int(data.get('subject_id'))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid Subject ID."}), 400

    new_name = str(data.get('subject_name', '')).strip()

    if not new_name:
        return jsonify({"success": False, "error": "Subject name cannot be empty."}), 400

    if len(new_name) > 100:
        return jsonify({"success": False, "error": "Subject name exceeds maximum length of 100 characters."}), 400

    target_sub = execute_query("SELECT * FROM subjects WHERE id=?", (subject_id,), fetchone=True)
    if not target_sub:
        return jsonify({"success": False, "error": "Subject not found."}), 404

    if target_sub['department'] != t_dept or int(target_sub['semester']) != int(t_sem) or target_sub['section'].upper() != t_sec.upper():
        return jsonify({"success": False, "error": "Access Denied: You are not authorized to edit subjects outside your assigned class scope."}), 403

    dup = execute_query(
        "SELECT id FROM subjects WHERE department=? AND semester=? AND section=? AND LOWER(subject_name)=LOWER(?) AND active=1 AND id!=?",
        (t_dept, t_sem, t_sec, new_name, subject_id), fetchone=True
    )
    if dup:
        return jsonify({"success": False, "error": f"Another active subject named '{new_name}' already exists in your class."}), 400

    execute_query("UPDATE subjects SET subject_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_name, subject_id), commit=True)

    return jsonify({
        "success": True,
        "message": f"Subject updated to '{new_name}' successfully!",
        "subject_id": subject_id,
        "subject_name": new_name
    })


@teacher_bp.route('/teacher/api/subjects/deactivate', methods=['POST'])
@teacher_required
def deactivate_subject_api():
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    t_sec = session.get('teacher_sec', 'A')

    data = request.get_json() or {}
    try:
        subject_id = int(data.get('subject_id'))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid Subject ID."}), 400

    target_sub = execute_query("SELECT * FROM subjects WHERE id=?", (subject_id,), fetchone=True)
    if not target_sub:
        return jsonify({"success": False, "error": "Subject not found."}), 404

    if target_sub['department'] != t_dept or int(target_sub['semester']) != int(t_sem) or target_sub['section'].upper() != t_sec.upper():
        return jsonify({"success": False, "error": "Access Denied: You are not authorized to deactivate subjects outside your assigned class scope."}), 403

    execute_query("UPDATE subjects SET active=0, updated_at=CURRENT_TIMESTAMP WHERE id=?", (subject_id,), commit=True)

    return jsonify({
        "success": True,
        "message": f"Subject '{target_sub['subject_name']}' deactivated successfully!"
    })


# ─── TEACHER-STUDENT PRIVATE COMMUNICATION ENDPOINTS ───────────────────────

def check_teacher_student_scope(teacher_session, student, conv_teacher_id=None):
    """
    Verify whether a student belongs to the Class Teacher's assigned scope.
    Strictly enforces department boundaries and assigned teacher IDs.
    """
    t_role = teacher_session.get('teacher_role', 'Teacher')
    t_dept = teacher_session.get('teacher_dept', 'None')
    t_id = teacher_session.get('teacher_id', '')

    if t_role == 'Teacher' or t_dept == 'None':
        return False

    st_dept = student.get('department')

    # Cross-department check: CSE teacher cannot access ISE student unless explicitly assigned
    if st_dept and t_dept and st_dept.upper() != t_dept.upper() and conv_teacher_id != t_id:
        return False

    return True


@teacher_bp.route('/teacher/api/conversations', methods=['GET'])
@teacher_required
def get_teacher_conversations():
    t_role = session.get('teacher_role', 'Teacher')
    t_dept = session.get('teacher_dept', 'None')
    t_sem = session.get('teacher_sem', 6)
    t_sec = session.get('teacher_sec', 'A')
    t_id = session.get('teacher_id', '')

    filter_status = request.args.get('status', 'All').strip()

    if t_role == 'Teacher' or t_dept == 'None':
        return jsonify({"success": True, "conversations": [], "unread_total": 0, "no_access": True})

    # Fetch conversations joined with student info within teacher's scope
    query = """
        SELECT m.*, s.usn, s.name as student_name, s.department as student_dept,
               s.current_semester as student_sem, s.section as student_sec,
               s.attendance, s.internal_marks, s.dbms_marks, s.java_marks, s.cgpa, s.risk_level, s.predicted_result
        FROM teacher_student_messages m
        JOIN students s ON m.student_id = s.id
        WHERE (s.department = ? OR m.teacher_id = ?)
        ORDER BY m.updated_at DESC
    """
    params = [t_dept, t_id]

    rows = execute_query(query, tuple(params), fetchall=True) or []

    conversations = []
    unread_total = 0

    for r in rows:
        conv_id = r['id']

        # Get unread student messages count
        unread_row = execute_query("""
            SELECT COUNT(*) as cnt FROM teacher_student_replies
            WHERE conversation_id=? AND sender_role='Student' AND read_status=0
        """, (conv_id,), fetchone=True)
        unread_cnt = unread_row['cnt'] if unread_row else 0
        unread_total += unread_cnt

        # Filter by status parameter if requested
        conv_status = r['status']
        if filter_status == 'Unread' and unread_cnt == 0:
            continue
        elif filter_status in ['Open', 'Replied', 'Resolved'] and conv_status != filter_status:
            continue

        # Get latest message
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
            "student_name": r['student_name'],
            "usn": r['usn'],
            "department": r['student_dept'],
            "semester": r['student_sem'],
            "section": r['student_sec'],
            "category": r['category'],
            "topic": r['topic'],
            "status": conv_status,
            "context_data": context_obj,
            "unread_count": unread_cnt,
            "created_at": r['created_at'],
            "updated_at": r['updated_at'],
            "last_message": last_reply['message'] if last_reply else '',
            "last_sender": last_reply['sender_name'] if last_reply else '',
            "last_sender_role": last_reply['sender_role'] if last_reply else ''
        })

    return jsonify({
        "success": True,
        "unread_total": unread_total,
        "conversations": conversations
    })


@teacher_bp.route('/teacher/api/conversations/<int:conv_id>', methods=['GET'])
@teacher_required
def get_teacher_conversation_detail(conv_id):
    conv = execute_query("SELECT * FROM teacher_student_messages WHERE id=?", (conv_id,), fetchone=True)
    if not conv:
        return jsonify({"success": False, "error": "Conversation not found."}), 404

    student = execute_query("SELECT * FROM students WHERE id=?", (conv['student_id'],), fetchone=True)
    if not student or not check_teacher_student_scope(session, student, conv.get('teacher_id')):
        return jsonify({"success": False, "error": "Access Denied: Student is outside your assigned class scope."}), 403

    # Mark student messages as read by teacher
    execute_query("""
        UPDATE teacher_student_replies
        SET read_status=1
        WHERE conversation_id=? AND sender_role='Student'
    """, (conv_id,), commit=True)

    replies = execute_query("""
        SELECT * FROM teacher_student_replies
        WHERE conversation_id=?
        ORDER BY id ASC
    """, (conv_id,), fetchall=True) or []

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
            "context_data": context_obj,
            "created_at": conv['created_at'],
            "updated_at": conv['updated_at']
        },
        "student": {
            "id": student['id'],
            "name": student['name'],
            "usn": student['usn'],
            "department": student['department'],
            "semester": student['current_semester'],
            "section": student['section'],
            "attendance": student.get('attendance', 78),
            "cgpa": student.get('cgpa', 7.5),
            "internal_marks": student.get('internal_marks', 70),
            "dbms_marks": student.get('dbms_marks', 70),
            "java_marks": student.get('java_marks', 70),
            "risk_level": student.get('risk_level', 'Low'),
            "predicted_result": student.get('predicted_result', 'Pass')
        },
        "replies": replies
    })


@teacher_bp.route('/teacher/api/conversations/<int:conv_id>/reply', methods=['POST'])
@teacher_required
def send_teacher_reply(conv_id):
    conv = execute_query("SELECT * FROM teacher_student_messages WHERE id=?", (conv_id,), fetchone=True)
    if not conv:
        return jsonify({"success": False, "error": "Conversation not found."}), 404

    student = execute_query("SELECT * FROM students WHERE id=?", (conv['student_id'],), fetchone=True)
    if not student or not check_teacher_student_scope(session, student, conv.get('teacher_id')):
        return jsonify({"success": False, "error": "Access Denied: Student is outside your assigned class scope."}), 403

    data = request.get_json() or {}
    message = data.get('message', '').strip()

    if not message:
        return jsonify({"success": False, "error": "Reply message cannot be empty."}), 400

    if len(message) > 5000:
        return jsonify({"success": False, "error": "Reply cannot exceed 5000 characters."}), 400

    t_name = session.get('teacher_name', 'Class Teacher')
    t_id = session.get('teacher_id', 'Teacher')

    execute_query("""
        INSERT INTO teacher_student_replies (conversation_id, sender_id, sender_role, sender_name, message, read_status)
        VALUES (?, ?, 'Teacher', ?, ?, 0)
    """, (conv_id, str(t_id), t_name, message), commit=True)

    new_status = 'Replied'
    execute_query("""
        UPDATE teacher_student_messages
        SET status=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (new_status, conv_id), commit=True)

    return jsonify({"success": True, "message": "Reply sent to student."})


@teacher_bp.route('/teacher/api/conversations/<int:conv_id>/resolve', methods=['POST'])
@teacher_required
def resolve_teacher_conversation(conv_id):
    conv = execute_query("SELECT * FROM teacher_student_messages WHERE id=?", (conv_id,), fetchone=True)
    if not conv:
        return jsonify({"success": False, "error": "Conversation not found."}), 404

    student = execute_query("SELECT * FROM students WHERE id=?", (conv['student_id'],), fetchone=True)
    if not student or not check_teacher_student_scope(session, student, conv.get('teacher_id')):
        return jsonify({"success": False, "error": "Access Denied: Student is outside your assigned class scope."}), 403

    execute_query("""
        UPDATE teacher_student_messages
        SET status='Resolved', updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (conv_id,), commit=True)

    return jsonify({"success": True, "message": "Conversation marked as resolved."})

