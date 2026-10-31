"""
Student Performance Analyzer & Marks Prediction System Application
Main Flask Application Server integrating Student, Teacher, HOD, and Admin portals.
"""
from flask import Flask, redirect, url_for, render_template, request, session, jsonify
import os
from werkzeug.security import generate_password_hash

from services.db_service import init_database, execute_query, DEFAULT_DEMO_PASSWORD

# Initialize DB and schema migrations
init_database()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'student_analyzer_secret_key_2026')

# Register Blueprints
from blueprints.student import student_bp
from blueprints.teacher import teacher_bp
from blueprints.hod import hod_bp
from blueprints.admin import admin_bp
from blueprints.report import report_bp

app.register_blueprint(student_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(hod_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(report_bp)

# Default landing page redirects to Student Login
@app.route('/')
def index():
    return redirect(url_for('student.student_login'))

@app.route('/force-password-change', methods=['GET', 'POST'])
def force_password_change():
    if request.method == 'POST':
        data = request.get_json() or {}
        user_id = session.get('temp_user_id')
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')

        if not user_id:
            return jsonify({"success": False, "error": "Session expired. Please log in again."}), 401

        if not new_password or new_password != confirm_password:
            return jsonify({"success": False, "error": "New password and confirmation do not match."}), 400

        # Teacher / user cannot keep the default demo password Rns@123
        if new_password == DEFAULT_DEMO_PASSWORD:
            return jsonify({"success": False, "error": f"Security violation: New password cannot be the temporary demo password ({DEFAULT_DEMO_PASSWORD}). Please enter a new unique password."}), 400

        hashed_pwd = generate_password_hash(new_password)
        execute_query("UPDATE users SET password_hash=?, temp_password='', first_login=0 WHERE user_id=?", (hashed_pwd, user_id), commit=True)

        session.pop('temp_user_id', None)
        return jsonify({"success": True, "message": "Password updated successfully! Please log in with your new password."})

    return render_template('force_password_change.html')

if __name__ == '__main__':
    print("Starting Student Performance Analyzer & Marks Prediction System Platform...")
    app.run(host='127.0.0.1', port=5000, debug=True)
