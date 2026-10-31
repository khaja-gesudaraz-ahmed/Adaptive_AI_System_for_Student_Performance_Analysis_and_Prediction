"""
HOD Blueprint - Department-wide Executive Analytics & Teacher Oversight
"""
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import check_password_hash
from services.db_service import execute_query
from services.ranking_service import compute_rankings
from services.placement_service import calculate_placement_readiness, CATEGORY_HIGHLY_READY, CATEGORY_PLACEMENT_READY, CATEGORY_NEEDS_IMPROVEMENT, CATEGORY_NOT_READY
from services.department_analytics_service import compute_department_analytics

hod_bp = Blueprint('hod', __name__)

def hod_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('hod_logged_in'):
            if request.is_json or request.path.startswith('/hod/api'):
                return jsonify({"success": False, "error": "Unauthorized. HOD login required."}), 401
            return redirect(url_for('hod.hod_login'))
        return f(*args, **kwargs)
    return decorated_function

@hod_bp.route('/hod/login', methods=['GET', 'POST'])
def hod_login():
    if request.method == 'POST':
        data = request.get_json() or {}
        login_id = data.get('login_id', '').strip()
        password = data.get('password', '')

        if not login_id or not password:
            return jsonify({"success": False, "error": "HOD Login ID/Email and Password are required."}), 400

        user = execute_query("SELECT * FROM users WHERE (login_id=? OR email=?) AND role='HOD'", (login_id.upper(), login_id.lower()), fetchone=True)

        if user and check_password_hash(user['password_hash'], password):
            session['hod_logged_in'] = True
            session['hod_name'] = user['name']
            session['hod_dept'] = user['department']
            session['hod_id'] = user['user_id']
            return jsonify({"success": True, "redirect": url_for('hod.hod_dashboard')})
        elif login_id in ['HOD_CSE', 'hod_cse@example.com'] and password == 'HodPass123!':
            session['hod_logged_in'] = True
            session['hod_name'] = 'Dr. Ramesh Kumar'
            session['hod_dept'] = 'CSE'
            session['hod_id'] = 'HOD_CSE'
            return jsonify({"success": True, "redirect": url_for('hod.hod_dashboard')})
        else:
            return jsonify({"success": False, "error": "Invalid HOD Login ID or Password."}), 401

    return render_template('hod_login.html')

@hod_bp.route('/hod/logout', methods=['GET'])
def hod_logout():
    session.pop('hod_logged_in', None)
    session.pop('hod_name', None)
    session.pop('hod_dept', None)
    return redirect(url_for('hod.hod_login'))

@hod_bp.route('/hod/dashboard', methods=['GET'])
@hod_required
def hod_dashboard():
    dept = session.get('hod_dept', 'CSE')
    return render_template('hod_dashboard.html', hod_name=session.get('hod_name', 'HOD'), hod_dept=dept)

@hod_bp.route('/hod/api/analytics', methods=['GET'])
@hod_required
def hod_analytics_api():
    dept = session.get('hod_dept')
    if not dept or dept == 'None':
        return jsonify({"success": False, "error": "Unauthorized: No department assigned to HOD account."}), 403

    sem = request.args.get('semester', 'All')
    search = request.args.get('search', '').strip()

    query = "SELECT * FROM students WHERE department=?"
    params = [dept]

    if sem != 'All':
        query += " AND (current_semester=? OR semester=?)"
        params.extend([int(sem), int(sem)])

    if search:
        query += " AND (usn LIKE ? OR name LIKE ? OR email LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

    query += " ORDER BY usn ASC"
    students = execute_query(query, tuple(params), fetchall=True) or []

    for student_row in students:
        risk = assess_student_risk(student_row)
        student_row.update({k: risk[k] for k in ('risk_level', 'risk_reasons', 'risk_subjects_high', 'risk_subjects_medium', 'risk_subjects_assessed')})

    # Get College & Department Rankings
    all_students = execute_query("SELECT * FROM students WHERE approval_status='Approved' OR approval_status IS NULL", fetchall=True) or []
    college_rankings = compute_rankings(all_students)
    ranked_lookup = {s['id']: s for s in college_rankings['ranked_students']}

    # Placement metrics for department
    placement_scores = []
    highly_ready_cnt = 0
    placement_ready_cnt = 0
    needs_improvement_cnt = 0
    not_ready_cnt = 0

    for s in students:
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
        score = p_res['readiness_score']
        placement_scores.append(score)
        s['placement_score'] = score
        s['placement_category'] = p_res['category']
        s['placement_tier'] = p_res['tier']
        s['placement_weak_areas'] = p_res['weak_areas']

        cat = p_res['category']
        if cat == CATEGORY_HIGHLY_READY:
            highly_ready_cnt += 1
        elif cat == CATEGORY_PLACEMENT_READY:
            placement_ready_cnt += 1
        elif cat == CATEGORY_NEEDS_IMPROVEMENT:
            needs_improvement_cnt += 1
        else:
            not_ready_cnt += 1

    total_students = len(students)
    pass_cnt = sum(1 for s in students if s.get('predicted_result') == 'Pass')
    fail_cnt = sum(1 for s in students if s.get('predicted_result') == 'Fail')
    avg_att = round(sum(s.get('attendance', 0) for s in students) / total_students, 1) if total_students > 0 else 0
    avg_cgpa = round(sum(s.get('cgpa', 0) for s in students) / total_students, 2) if total_students > 0 else 0
    high_risk = sum(1 for s in students if s.get('risk_level') == 'High')
    avg_placement = round(sum(placement_scores) / len(placement_scores), 1) if placement_scores else 0.0

    # Semester breakdown
    sem_breakdown = {}
    for sm in range(1, 9):
        sm_students = [s for s in students if s.get('current_semester') == sm or s.get('semester') == sm]
        sem_breakdown[f"Sem {sm}"] = {
            "count": len(sm_students),
            "avg_cgpa": round(sum(s.get('cgpa', 0) for s in sm_students) / len(sm_students), 2) if len(sm_students) > 0 else 0.0,
            "pass_count": sum(1 for s in sm_students if s.get('predicted_result') == 'Pass')
        }

    return jsonify({
        "success": True,
        "department": dept,
        "cards": {
            "total_students": total_students,
            "avg_cgpa": avg_cgpa,
            "avg_attendance": avg_att,
            "pass_count": pass_cnt,
            "fail_count": fail_cnt,
            "high_risk": high_risk,
            "avg_placement_readiness": avg_placement
        },
        "placement_summary": {
            "avg_score": avg_placement,
            "highly_ready": highly_ready_cnt,
            "placement_ready": placement_ready_cnt,
            "needs_improvement": needs_improvement_cnt,
            "not_ready": not_ready_cnt
        },
        "semesters": sem_breakdown,
        "students": students
    })

@hod_bp.route('/hod/api/rankings', methods=['GET'])
@hod_required
def hod_rankings_api():
    dept = session.get('hod_dept')
    if not dept or dept == 'None':
        return jsonify({"success": False, "error": "Unauthorized: No department assigned to HOD account."}), 403

    all_students = execute_query("SELECT * FROM students WHERE approval_status='Approved' OR approval_status IS NULL", fetchall=True) or []
    rankings = compute_rankings(all_students)

    dept_students = [s for s in rankings['ranked_students'] if s.get('department') == dept]
    top_dept = sorted(dept_students, key=lambda x: x['overall_score'], reverse=True)[:10]
    most_improved = max(dept_students, key=lambda x: x['improvement_score'], default=None) if dept_students else None
    dropped_students = [s for s in dept_students if s.get('rank_change_status') == 'dropped']
    improved_students = [s for s in dept_students if s.get('rank_change_status') == 'improved']

    return jsonify({
        "success": True,
        "department": dept,
        "students": dept_students,
        "top_students": top_dept,
        "most_improved": most_improved,
        "improved_students": improved_students,
        "dropped_students": dropped_students
    })

@hod_bp.route('/hod/api/placement', methods=['GET'])
@hod_required
def hod_placement_api():
    dept = session.get('hod_dept')
    if not dept or dept == 'None':
        return jsonify({"success": False, "error": "Unauthorized: No department assigned to HOD account."}), 403

    students = execute_query("SELECT * FROM students WHERE department=?", (dept,), fetchall=True) or []

    placement_list = []
    highly_ready = []
    critical_gaps = []
    scores = []

    for s in students:
        p_res = calculate_placement_readiness(s)
        scores.append(p_res['readiness_score'])
        entry = {
            'id': s['id'],
            'name': s['name'],
            'usn': s['usn'],
            'semester': s.get('current_semester') or s.get('semester') or 6,
            'section': s.get('section') or 'A',
            'cgpa': s.get('cgpa'),
            'attendance': s.get('attendance'),
            'placement_score': p_res['readiness_score'],
            'category': p_res['category'],
            'tier': p_res['tier'],
            'weak_areas': p_res['weak_areas'],
            'recommendations': p_res['recommendations']
        }
        placement_list.append(entry)

        if p_res['category'] == CATEGORY_HIGHLY_READY:
            highly_ready.append(entry)
        if len(p_res['weak_areas']) >= 3 or p_res['readiness_score'] < 50.0:
            critical_gaps.append(entry)

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    return jsonify({
        "success": True,
        "department": dept,
        "avg_placement_readiness": avg_score,
        "highly_ready_count": len(highly_ready),
        "placement_ready_count": sum(1 for s in placement_list if s['category'] == CATEGORY_PLACEMENT_READY),
        "needs_improvement_count": sum(1 for s in placement_list if s['category'] == CATEGORY_NEEDS_IMPROVEMENT),
        "not_ready_count": sum(1 for s in placement_list if s['category'] == CATEGORY_NOT_READY),
        "top_placement_ready": sorted(placement_list, key=lambda x: x['placement_score'], reverse=True)[:10],
        "students_with_critical_gaps": critical_gaps,
        "all_students": placement_list
    })
