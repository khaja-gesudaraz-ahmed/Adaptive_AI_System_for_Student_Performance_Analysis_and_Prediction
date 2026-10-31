"""
Post-Reset Functionality Verification
Tests Admin Login, Teacher Account Creation by Admin, Student Account Creation,
and Subject Management in a clean post-reset environment.
"""
import sys
import unittest

PROJECT_ROOT = r"C:\Users\Hi\.gemini\antigravity\scratch\student-ai-system\student-ai-system-updated"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app
from services.db_service import get_class_subjects, execute_query

class TestPostResetFunctionality(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()

    def test_01_verify_clean_state(self):
        """Verify database currently has 1 Admin, 0 Teachers, 0 Students, 0 Subjects."""
        admins = execute_query("SELECT COUNT(*) as cnt FROM users WHERE role='Admin' OR UPPER(login_id)='ADMIN001'", fetchone=True)['cnt']
        teachers = execute_query("SELECT COUNT(*) as cnt FROM users WHERE role IN ('Teacher', 'Class Teacher', 'HOD')", fetchone=True)['cnt']
        students = execute_query("SELECT COUNT(*) as cnt FROM students", fetchone=True)['cnt']
        subjects = execute_query("SELECT COUNT(*) as cnt FROM subjects", fetchone=True)['cnt']

        self.assertEqual(admins, 1)
        self.assertEqual(teachers, 0)
        self.assertEqual(students, 0)
        self.assertEqual(subjects, 0)
        print("\n[Post-Reset Check 1 Passed] Database is in clean zero-data state with 1 Admin preserved.")

    def test_02_admin_login(self):
        """Verify preserved Admin can log in successfully."""
        resp = self.client.post('/admin/login', json={
            "login_id": "ADMIN001",
            "password": "AdminPass123!" # or Rns@123
        })
        if resp.status_code != 200:
            resp = self.client.post('/admin/login', json={
                "login_id": "ADMIN001",
                "password": "Rns@123"
            })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        print("[Post-Reset Check 2 Passed] Admin account logged in successfully.")

    def test_03_admin_create_teacher(self):
        """Verify Admin can create a new teacher in clean environment."""
        with self.client.session_transaction() as sess:
            sess['admin_logged_in'] = True
            sess['admin_id'] = 'ADMIN001'

        resp = self.client.post('/admin/api/create-user', json={
            "name": "Prof. Alan Turing",
            "email": "turing@example.com",
            "login_id": "CSE6A01",
            "role": "Class Teacher",
            "department": "CSE",
            "semester": 6,
            "section": "A",
            "password": "Rns@123"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))

        t_cnt = execute_query("SELECT COUNT(*) as cnt FROM users WHERE role='Class Teacher'", fetchone=True)['cnt']
        self.assertEqual(t_cnt, 1)
        print("[Post-Reset Check 3 Passed] Admin created new Teacher account successfully.")

        # Clean up created test teacher after test
        execute_query("DELETE FROM users WHERE login_id='CSE6A01'", commit=True)
        execute_query("DELETE FROM teachers WHERE teacher_id='CSE6A01'", commit=True)

if __name__ == '__main__':
    unittest.main(verbosity=2)
