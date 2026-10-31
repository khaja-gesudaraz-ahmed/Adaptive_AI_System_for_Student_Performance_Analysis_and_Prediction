from flask import Blueprint, send_file, jsonify, request, session
import io

from services.db_service import execute_query
from services.pdf_service import generate_pdf_report, generate_class_pdf_report
from services.shap_service import compute_shap_explanation
from services.planner_service import generate_study_plan
from services.ranking_service import compute_rankings
from services.timeline_service import generate_semester_timeline
from services.placement_service import calculate_placement_readiness
from services.see_prediction_service import predict_student_see, summarize_student_see
from services.risk_service import assess_student_risk

report_bp = Blueprint('report', __name__)

@report_bp.route('/report/pdf/<int:student_id>', methods=['GET'])
def download_student_pdf(student_id):
    student = execute_query("SELECT * FROM students WHERE id=?", (student_id,), fetchone=True)
    if not student:
        return jsonify({"success": False, "error": "Student not found"}), 404

    if session.get('teacher_logged_in'):
        t_dept = session.get('teacher_dept')
        if t_dept and t_dept != 'None' and student.get('department') != t_dept:
            return jsonify({"success": False, "error": f"Access Denied: Student belongs to {student.get('department')} department, outside your assigned {t_dept} scope."}), 403

    if session.get('hod_logged_in'):
        h_dept = session.get('hod_dept')
        if h_dept and h_dept != 'None' and student.get('department') != h_dept:
            return jsonify({"success": False, "error": f"Access Denied: Student belongs to {student.get('department')} department, outside your assigned HOD department ({h_dept})."}), 403

    risk = assess_student_risk(student)
    student.update({k: risk[k] for k in ('risk_level', 'risk_reasons', 'risk_subjects_high', 'risk_subjects_medium', 'risk_subjects_assessed', 'see_predictions')})

    # Fetch previous semester history
    sem_history = execute_query(
        "SELECT semester, sgpa, backlog_count, backlog_status FROM semester_history WHERE student_id=? ORDER BY semester ASC",
        (student_id,), fetchall=True
    ) or []

    from services.pdf_service import compute_subject_ia_data
    ia_subjects = compute_subject_ia_data(student)

    weak_subjects = []
    for ws in ia_subjects:
        try:
            score = float(ws['best_two'])
            if score < 30.0:
                weak_subjects.append({"subject": ws['subject'], "marks": score})
        except ValueError:
            pass

    details = {
        'weak_subjects': weak_subjects,
        'ia_subjects': ia_subjects,
        'semester_history': sem_history,
        'study_plan': generate_study_plan(student, weak_subjects, student.get('risk_level', 'Low')),
        'timeline': generate_semester_timeline(student_id, student),
        'placement': calculate_placement_readiness(student),
        'ranking': None,
        'shap': None,
        'see_predictions': predict_student_see(student)
    }

    pdf_bytes = generate_pdf_report(student, details)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Student_Report_{student.get('usn', student_id)}.pdf"
    )

@report_bp.route('/report/class-pdf', methods=['GET'])
def download_class_pdf():
    dept = request.args.get('department', 'All')
    sem  = request.args.get('semester', 'All')
    sec  = request.args.get('section', 'All')

    # Security enforcement for teacher session: Force assigned department & semester scope
    if session.get('teacher_logged_in'):
        t_role = session.get('teacher_role', 'Teacher')
        t_dept = session.get('teacher_dept', 'None')
        t_sem  = session.get('teacher_sem', 6)
        if t_role == 'Teacher' or t_dept == 'None':
            return jsonify({"success": False, "error": "Access Denied: Teacher role has no department access permission."}), 403
        dept = t_dept
        sem = str(t_sem)

    # Security enforcement for HOD session: Force assigned department scope
    if session.get('hod_logged_in'):
        h_dept = session.get('hod_dept')
        if not h_dept or h_dept == 'None':
            return jsonify({"success": False, "error": "Access Denied: No department assigned to HOD account."}), 403
        dept = h_dept

    # Base: only approved (or implicitly approved) students
    query = "SELECT * FROM students WHERE (approval_status='Approved' OR approval_status IS NULL)"
    params = []

    if dept != 'All':
        query += " AND department = ?"
        params.append(dept)

    # Students table may store semester in either 'semester' or 'current_semester'
    if sem != 'All':
        query += " AND (semester = ? OR current_semester = ?)"
        params.extend([int(sem), int(sem)])

    # Section must be an exact match
    if sec != 'All':
        query += " AND section = ?"
        params.append(sec.upper())

    query += " ORDER BY usn ASC"
    students = execute_query(query, tuple(params), fetchall=True) or []
    for student_row in students:
        risk = assess_student_risk(student_row)
        student_row.update({k: risk[k] for k in ('risk_level', 'risk_reasons', 'risk_subjects_high', 'risk_subjects_medium', 'risk_subjects_assessed', 'see_predictions')})
    pdf_bytes = generate_class_pdf_report(students, dept, sem, sec)

    filename = f"Class_Report_Sem{sem}_Sec{sec}_{dept}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )
