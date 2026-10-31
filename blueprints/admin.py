"""
Admin Blueprint - College-wide System Administration, Role Editing, & Credentials Management
Handles User Creation (Class Teacher, HOD, Teacher, Admin), Role Editing, Password Resets to Rns@123, & Credential Exports.
"""
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, Response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import random
import datetime
import io

from services.db_service import execute_query, DEFAULT_DEMO_PASSWORD

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            if request.is_json or request.path.startswith('/admin/api'):
                return jsonify({"success": False, "error": "Unauthorized. Admin login required."}), 401
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_login_id(role, department, semester=None, section=None):
    dept_code = (department or 'CSE').replace(" ", "").replace("&", "").upper()[:4]
    if role == 'HOD':
        return f"HOD_{dept_code}"
    elif role == 'Class Teacher':
        sem_str = str(semester or 6)
        sec_str = (section or 'A').upper()
        cnt_row = execute_query("SELECT COUNT(*) as cnt FROM users WHERE role='Class Teacher' AND department=? AND semester=? AND section=?", (department, semester, section), fetchone=True)
        cnt = (cnt_row['cnt'] if cnt_row else 0) + 1
        return f"{dept_code}{sem_str}{sec_str}{cnt:02d}"
    elif role == 'Teacher':
        cnt_row = execute_query("SELECT COUNT(*) as cnt FROM users WHERE role='Teacher'", fetchone=True)
        cnt = (cnt_row['cnt'] if cnt_row else 0) + 1
        return f"TCH_{cnt:04d}"
    else:
        return f"ADMIN_{random.randint(100, 999)}"

@admin_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        data = request.get_json() or {}
        login_id = data.get('login_id', '').strip()
        password = data.get('password', '')

        if not login_id or not password:
            return jsonify({"success": False, "error": "Login ID/Email and Password are required."}), 400

        user = execute_query("SELECT * FROM users WHERE (login_id=? OR email=?) AND role='Admin'", (login_id, login_id.lower()), fetchone=True)
        
        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            session['admin_name'] = user['name']
            session['admin_id'] = user['user_id']
            return jsonify({"success": True, "redirect": url_for('admin.admin_dashboard')})
        elif login_id in ['ADMIN001', 'admin@example.com'] and password in [DEFAULT_DEMO_PASSWORD, 'AdminPass123!']:
            session['admin_logged_in'] = True
            session['admin_name'] = 'System Administrator'
            session['admin_id'] = 'ADMIN001'
            return jsonify({"success": True, "redirect": url_for('admin.admin_dashboard')})
        else:
            return jsonify({"success": False, "error": "Invalid Admin Login ID or Password."}), 401

    return render_template('admin_login.html')

@admin_bp.route('/admin/logout', methods=['GET'])
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_name', None)
    session.pop('admin_id', None)
    return redirect(url_for('admin.admin_login'))

@admin_bp.route('/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html', admin_name=session.get('admin_name', 'Administrator'))

# ─── USER CREATION, ROLE EDITING & PASSWORD RESET APIs ──────────────────────

@admin_bp.route('/admin/api/users', methods=['GET'])
@admin_required
def get_all_users():
    users_list = execute_query("SELECT id, user_id, name, email, login_id, role, department, semester, section, academic_year, account_status, first_login, created_at FROM users ORDER BY id DESC", fetchall=True) or []
    return jsonify({"success": True, "users": users_list})

@admin_bp.route('/admin/api/create-user', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    role = data.get('role', 'Class Teacher')
    department = data.get('department', 'CSE') if role != 'Teacher' else 'None'
    semester = int(data.get('semester', 6)) if role == 'Class Teacher' else None
    section = data.get('section', 'A').upper() if role == 'Class Teacher' else None
    academic_year = data.get('academic_year', '2024-25')

    if not name or not email:
        return jsonify({"success": False, "error": "Full Name and Email are required."}), 400

    # Check for duplicate email in users table
    existing_email = execute_query("SELECT id FROM users WHERE email=?", (email,), fetchone=True)
    if existing_email:
        return jsonify({"success": False, "error": f"Email '{email}' is already registered."}), 400

    try:
        login_id = generate_login_id(role, department, semester, section)
        temp_password = DEFAULT_DEMO_PASSWORD
        hashed_pwd = generate_password_hash(temp_password)
        user_id = f"USR-{random.randint(1000, 9999)}"

        # Ensure user_id is unique
        while execute_query("SELECT id FROM users WHERE user_id=?", (user_id,), fetchone=True):
            user_id = f"USR-{random.randint(1000, 9999)}"

        execute_query("""
            INSERT INTO users (user_id, name, email, login_id, password_hash, temp_password, role, department, semester, section, academic_year, first_login)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (user_id, name, email, login_id, hashed_pwd, temp_password, role, department, semester, section, academic_year), commit=True)

        if role in ['Class Teacher', 'Teacher']:
            # Only insert into teachers if not already there (avoid duplicate on teacher_id)
            existing_teacher = execute_query("SELECT id FROM teachers WHERE email=? OR teacher_id=?", (email, login_id), fetchone=True)
            if not existing_teacher:
                execute_query("""
                    INSERT INTO teachers (teacher_id, name, email, password_hash, department, role)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (login_id, name, email, hashed_pwd, department, role), commit=True)

        return jsonify({
            "success": True,
            "message": f"Account created successfully for {name}!",
            "credentials": {
                "user_id": user_id,
                "name": name,
                "role": role,
                "department": department,
                "login_id": login_id,
                "temp_password": temp_password
            }
        })
    except Exception as e:
        import traceback
        err_detail = traceback.format_exc()
        print(f"[Admin create_user ERROR] {err_detail}")
        return jsonify({"success": False, "error": f"Account creation failed: {str(e)}"}), 500

@admin_bp.route('/admin/api/update-user/<int:id>', methods=['POST'])
@admin_required
def update_user_role(id):
    data = request.get_json() or {}
    new_role = data.get('role')
    new_dept = data.get('department')
    new_sem = data.get('semester')
    new_sec = data.get('section')
    new_status = data.get('account_status', 'Active')

    user = execute_query("SELECT * FROM users WHERE id=?", (id,), fetchone=True)
    if not user:
        return jsonify({"success": False, "error": "User not found."}), 404

    target_role = new_role or user['role']
    target_dept = 'None' if target_role == 'Teacher' else (new_dept or user['department'])

    execute_query("""
        UPDATE users
        SET role=?, department=?, semester=?, section=?, account_status=?
        WHERE id=?
    """, (target_role, target_dept, new_sem or user['semester'], new_sec or user['section'], new_status, id), commit=True)

    return jsonify({"success": True, "message": f"Updated role and assignment for {user['name']} to '{target_role}' (Dept Access: {target_dept})."})

@admin_bp.route('/admin/api/reset-password/<int:id>', methods=['POST'])
@admin_required
def reset_user_password(id):
    user = execute_query("SELECT * FROM users WHERE id=?", (id,), fetchone=True)
    if not user:
        return jsonify({"success": False, "error": "User not found."}), 404

    temp_pwd = DEFAULT_DEMO_PASSWORD
    hashed_pwd = generate_password_hash(temp_pwd)

    execute_query("UPDATE users SET password_hash=?, temp_password=?, first_login=1 WHERE id=?", (hashed_pwd, temp_pwd, id), commit=True)
    
    return jsonify({
        "success": True,
        "message": f"Password reset for {user['name']} to demo password.",
        "login_id": user['login_id'],
        "new_temp_password": temp_pwd
    })

@admin_bp.route('/admin/api/export-credentials', methods=['GET'])
@admin_required
def export_credentials():
    fmt = request.args.get('format', 'excel').lower()
    users_list = execute_query("SELECT user_id, name, role, department, semester, section, login_id, temp_password, account_status FROM users ORDER BY id DESC", fetchall=True) or []

    if fmt == 'pdf':
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, leading=20, textColor=colors.HexColor('#0F172A'))
        body_style = ParagraphStyle('Body', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11)
        header_style = ParagraphStyle('Header', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=colors.white)

        story = [
            Paragraph("<b>USER CREDENTIALS REPORT</b>", title_style),
            Paragraph(f"Generated: {datetime.datetime.now().strftime('%d %b %Y, %I:%M %p')} | Confidential - Default Password: {DEFAULT_DEMO_PASSWORD}", styles['Normal']),
            Spacer(1, 12)
        ]

        table_data = [[
            Paragraph("<b>User ID</b>", header_style),
            Paragraph("<b>Name</b>", header_style),
            Paragraph("<b>Role</b>", header_style),
            Paragraph("<b>Dept Access</b>", header_style),
            Paragraph("<b>Login ID</b>", header_style),
            Paragraph("<b>Temporary Password</b>", header_style)
        ]]

        for u in users_list:
            table_data.append([
                Paragraph(u.get('user_id', ''), body_style),
                Paragraph(u.get('name', ''), body_style),
                Paragraph(u.get('role', ''), body_style),
                Paragraph(u.get('department', 'None'), body_style),
                Paragraph(f"<b>{u.get('login_id', '')}</b>", body_style),
                Paragraph(u.get('temp_password') or DEFAULT_DEMO_PASSWORD, body_style)
            ])

        t = Table(table_data, colWidths=[70, 130, 80, 60, 90, 110])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0,0), (-1,-1), 5)
        ]))
        story.append(t)
        doc.build(story)
        buffer.seek(0)
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name='User_Credentials_Report.pdf')

    else:
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['User ID', 'Full Name', 'Role', 'Department Access', 'Semester', 'Section', 'Login ID', 'Temporary Password', 'Account Status'])
        for u in users_list:
            writer.writerow([
                u.get('user_id'), u.get('name'), u.get('role'), u.get('department'),
                u.get('semester'), u.get('section'), u.get('login_id'),
                u.get('temp_password') or DEFAULT_DEMO_PASSWORD, u.get('account_status')
            ])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=User_Credentials_Report.csv"})

# ─── ADMIN RANKING, PLACEMENT & DEPARTMENT ANALYTICS APIs ───────────────────

from services.ranking_service import compute_rankings
from services.placement_service import calculate_placement_readiness, CATEGORY_HIGHLY_READY, CATEGORY_PLACEMENT_READY, CATEGORY_NEEDS_IMPROVEMENT, CATEGORY_NOT_READY
from services.department_analytics_service import compute_department_analytics

@admin_bp.route('/admin/api/rankings', methods=['GET'])
@admin_required
def admin_rankings_api():
    all_students = execute_query("SELECT * FROM students WHERE approval_status='Approved' OR approval_status IS NULL", fetchall=True) or []
    rankings = compute_rankings(all_students)

    dept_filter = request.args.get('department', 'All')
    sem_filter = request.args.get('semester', 'All')

    filtered_students = rankings['ranked_students']
    if dept_filter != 'All':
        filtered_students = [s for s in filtered_students if s.get('department') == dept_filter]
    if sem_filter != 'All':
        filtered_students = [s for s in filtered_students if str(s.get('current_semester') or s.get('semester')) == str(sem_filter)]

    return jsonify({
        "success": True,
        "total_ranked": len(rankings['ranked_students']),
        "students": filtered_students,
        "top_10": rankings['top_10'],
        "top_3": rankings.get('top_3', []),
        "most_improved": rankings.get('most_improved'),
        "best_attendance": rankings.get('best_attendance'),
        "most_consistent": rankings.get('most_consistent'),
        "improved_students": rankings.get('improved_students', []),
        "dropped_students": rankings.get('dropped_students', [])
    })

@admin_bp.route('/admin/api/placement', methods=['GET'])
@admin_required
def admin_placement_api():
    dept_filter = request.args.get('department', 'All')
    sem_filter = request.args.get('semester', 'All')

    query = "SELECT * FROM students WHERE (approval_status='Approved' OR approval_status IS NULL)"
    params = []
    if dept_filter != 'All':
        query += " AND department=?"
        params.append(dept_filter)
    if sem_filter != 'All':
        query += " AND (current_semester=? OR semester=?)"
        params.extend([int(sem_filter), int(sem_filter)])

    students = execute_query(query, tuple(params), fetchall=True) or []

    placement_list = []
    highly_ready_cnt = 0
    placement_ready_cnt = 0
    needs_improvement_cnt = 0
    not_ready_cnt = 0
    scores = []

    for s in students:
        p_res = calculate_placement_readiness(s)
        score = p_res['readiness_score']
        scores.append(score)

        entry = {
            'id': s['id'],
            'name': s['name'],
            'usn': s['usn'],
            'department': s.get('department'),
            'semester': s.get('current_semester') or s.get('semester') or 6,
            'section': s.get('section') or 'A',
            'cgpa': s.get('cgpa'),
            'attendance': s.get('attendance'),
            'placement_score': score,
            'category': p_res['category'],
            'tier': p_res['tier'],
            'strengths': p_res['strengths'],
            'weak_areas': p_res['weak_areas'],
            'recommendations': p_res['recommendations'],
            'breakdown': p_res['breakdown']
        }
        placement_list.append(entry)

        cat = p_res['category']
        if cat == CATEGORY_HIGHLY_READY:
            highly_ready_cnt += 1
        elif cat == CATEGORY_PLACEMENT_READY:
            placement_ready_cnt += 1
        elif cat == CATEGORY_NEEDS_IMPROVEMENT:
            needs_improvement_cnt += 1
        else:
            not_ready_cnt += 1

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    return jsonify({
        "success": True,
        "college_avg_placement_readiness": avg_score,
        "total_evaluated": len(placement_list),
        "highly_ready_count": highly_ready_cnt,
        "placement_ready_count": placement_ready_cnt,
        "needs_improvement_count": needs_improvement_cnt,
        "not_ready_count": not_ready_cnt,
        "top_placement_ready": sorted(placement_list, key=lambda x: x['placement_score'], reverse=True)[:10],
        "students": placement_list
    })

@admin_bp.route('/admin/api/department-analytics', methods=['GET'])
@admin_bp.route('/analytics/departments', methods=['GET'])
def get_department_analytics_api():
    acad_year = request.args.get('academic_year', 'All')
    dept = request.args.get('department', 'All')
    sem = request.args.get('semester', 'All')
    sec = request.args.get('section', 'All')

    data = compute_department_analytics(
        academic_year=acad_year,
        department_filter=dept,
        semester_filter=sem,
        section_filter=sec
    )
    return jsonify(data)
