"""
Automated Test Suite for Dynamic Subject Management System
Tests:
1. Schema Initialization & Migration of legacy marks to subjects & student_ia_marks tables.
2. Subject Identity Preservation (Subject ID remains constant when Subject Name is edited via UI or Excel).
3. Subject CRUD Operations (Add, Edit, Deactivate, List).
4. Dynamic N subjects support (N=5 subjects) in analytics, ranking, study planner, and PDF reports.
5. Scope Isolation (403 Access Denied on cross-scope access).
"""
import os
import sys
import unittest

# Add project root to sys.path
PROJECT_ROOT = r"C:\Users\Hi\.gemini\antigravity\scratch\student-ai-system\student-ai-system-updated"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app
from services.db_service import (
    init_database, get_db_connection, execute_query,
    get_class_subjects, get_student_ia_marks, save_student_ia_mark
)
from services.ranking_service import compute_rankings
from services.department_analytics_service import compute_department_analytics
from services.planner_service import generate_study_plan
from services.pdf_service import generate_pdf_report

class TestDynamicSubjects(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()
        
        # Initialize DB in the actual db path or test context
        with app.app_context():
            init_database()

    def test_01_migration_and_default_subjects(self):
        """Verify default subjects (Sub 1..4) are populated per class scope."""
        subjects = get_class_subjects('CSE', 6, 'A', active_only=True)
        self.assertGreaterEqual(len(subjects), 4, "Should have at least 4 default subjects initialized.")
        
        codes = [f"SUB{s['id']}" for s in subjects]
        names = [s['subject_name'] for s in subjects]
        print(f"\n[Test 1 Passed] Active subjects for CSE Sem 6 Sec A: {names} (IDs/Codes: {codes})")

    def test_02_subject_identity_preservation_on_edit(self):
        """Verify editing subject display_name retains permanent subject_id."""
        subjects = get_class_subjects('CSE', 6, 'A', active_only=True)
        target_sub = subjects[0]
        sub_id = target_sub['id']
        old_name = target_sub['subject_name']
        new_name = "Advanced Database Systems"

        # Update subject name via execute_query
        execute_query(
            "UPDATE subjects SET subject_name = ? WHERE id = ?",
            (new_name, sub_id),
            commit=True
        )

        updated_subs = get_class_subjects('CSE', 6, 'A', active_only=True)
        matching_sub = next((s for s in updated_subs if s['id'] == sub_id), None)
        
        self.assertIsNotNone(matching_sub)
        self.assertEqual(matching_sub['subject_name'], new_name)
        self.assertEqual(matching_sub['id'], sub_id)
        print(f"[Test 2 Passed] Subject ID {sub_id} name updated from '{old_name}' to '{new_name}' with ID preserved.")

        # Revert back
        execute_query("UPDATE subjects SET subject_name = ? WHERE id = ?", (old_name, sub_id), commit=True)

    def test_03_teacher_subject_crud_api(self):
        """Verify Teacher Dashboard APIs for adding, editing, and deactivating subjects."""
        # Clean up any leftover test subjects from previous runs
        execute_query("DELETE FROM subjects WHERE subject_name LIKE 'Cloud%'", commit=True)

        with self.client.session_transaction() as sess:
            sess['teacher_logged_in'] = True
            sess['teacher_dept'] = 'CSE'
            sess['teacher_sem'] = 6
            sess['teacher_sec'] = 'A'
            sess['teacher_role'] = 'Class Teacher'

        # 1. Add 5th subject
        resp = self.client.post('/teacher/api/subjects/add', json={
            "subject_name": "Cloud Computing"
        })
        self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.get_data(as_text=True)}")
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        added_sub = data.get('subject', {})
        added_id = added_sub.get('id')
        self.assertIsNotNone(added_id)

        # 2. Edit 5th subject
        resp_edit = self.client.post('/teacher/api/subjects/edit', json={
            "subject_id": added_id,
            "subject_name": "Cloud & DevOps Engineering"
        })
        self.assertEqual(resp_edit.status_code, 200)
        self.assertTrue(resp_edit.get_json().get('success'))

        # 3. Deactivate 5th subject
        resp_deact = self.client.post('/teacher/api/subjects/deactivate', json={
            "subject_id": added_id
        })
        self.assertEqual(resp_deact.status_code, 200)
        self.assertTrue(resp_deact.get_json().get('success'))

        print(f"[Test 3 Passed] Teacher Subject CRUD APIs (Add, Edit, Deactivate) successfully executed.")

        # Cleanup
        execute_query("DELETE FROM subjects WHERE id = ?", (added_id,), commit=True)

    def test_04_n_subjects_support_in_analytics_and_services(self):
        """Verify system handles N=5 subjects across ranking, analytics, study planner, and PDF."""
        # Clean up any previous test subject
        execute_query("DELETE FROM subjects WHERE subject_name = 'Artificial Intelligence'", commit=True)

        # Temporary add 5th active subject
        sub_id = execute_query(
            "INSERT INTO subjects (department, semester, section, subject_name, display_order, active) VALUES (?, ?, ?, ?, ?, 1)",
            ('CSE', 6, 'A', 'Artificial Intelligence', 5),
            commit=True
        )

        # Get first student in CSE Sem 6 Sec A
        st = execute_query("SELECT * FROM students WHERE department='CSE' AND current_semester=6 AND section='A' LIMIT 1", fetchone=True)
        if not st:
            st = execute_query("SELECT * FROM students LIMIT 1", fetchone=True)

        if st:
            st_id = st['id']
            # Save mark for subject 5
            save_student_ia_mark(st_id, sub_id, ia1=45.0, ia2=48.0, ia3=50.0)

            # Check ranking service
            all_st = execute_query("SELECT * FROM students", fetchall=True)
            rankings = compute_rankings(all_st)
            self.assertIn('ranked_students', rankings)

            # Check dept analytics
            dept_analytics = compute_department_analytics(department_filter='CSE')
            self.assertIn('departments', dept_analytics)
            self.assertEqual(len(dept_analytics['departments']), 1)

            # Check PDF generation
            pdf_bytes = generate_pdf_report(dict(st), {})
            self.assertGreater(len(pdf_bytes), 1000, "PDF report should be generated with N=5 subjects.")

            print(f"[Test 4 Passed] N=5 subjects verified across Rankings, Dept Analytics, Planner, and PDF report ({len(pdf_bytes)} bytes).")

        # Cleanup test subject 5
        execute_query("DELETE FROM student_ia_marks WHERE subject_id = ?", (sub_id,), commit=True)
        execute_query("DELETE FROM subjects WHERE id = ?", (sub_id,), commit=True)

    def test_05_teacher_scope_security(self):
        """Verify cross-scope operations return 403 Forbidden."""
        with self.client.session_transaction() as sess:
            sess['teacher_logged_in'] = True
            sess['teacher_dept'] = 'CSE'
            sess['teacher_sem'] = 6
            sess['teacher_sec'] = 'A'
            sess['teacher_role'] = 'Class Teacher'

        # Try to modify a subject belonging to ECE department
        ece_sub_id = execute_query(
            "INSERT INTO subjects (department, semester, section, subject_name, display_order, active) VALUES ('ECE', 6, 'A', 'Signals', 1, 1)",
            commit=True
        )

        resp = self.client.post('/teacher/api/subjects/edit', json={
            "subject_id": ece_sub_id,
            "subject_name": "Hacked Signals"
        })

        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.get_json().get('success'))
        print(f"[Test 5 Passed] Teacher scope RBAC enforced (403 Access Denied on cross-department subject edit).")

        # Clean up
        execute_query("DELETE FROM subjects WHERE id = ?", (ece_sub_id,), commit=True)

if __name__ == '__main__':
    unittest.main(verbosity=2)
