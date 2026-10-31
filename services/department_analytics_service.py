"""
Department Comparison & Analytics Service
Calculates multi-department comparative analytics, department performance rankings,
academic metrics (CGPA, Attendance, Pass/Fail, High Risk, IA marks), and Placement Readiness.
Supports dynamic filtering by Academic Year, Department, Semester, and Section.
"""
from services.db_service import execute_query, get_student_ia_marks
from services.ranking_service import calculate_overall_score, _compute_subject_best_two_avg
from services.placement_service import calculate_placement_readiness, CATEGORY_HIGHLY_READY, CATEGORY_PLACEMENT_READY, CATEGORY_NEEDS_IMPROVEMENT, CATEGORY_NOT_READY
from services.risk_service import assess_student_risk


def compute_department_analytics(academic_year=None, department_filter=None, semester_filter=None, section_filter=None):
    """
    Computes comparative analytics for all departments present in the students database.
    Applies filters dynamically if specified.
    """
    query = "SELECT * FROM students WHERE (approval_status='Approved' OR approval_status IS NULL)"
    params = []

    if academic_year and academic_year != 'All':
        query += " AND (academic_year=? OR admission_year=?)"
        params.extend([academic_year, academic_year])

    if department_filter and department_filter != 'All':
        query += " AND department=?"
        params.append(department_filter)

    if semester_filter and semester_filter != 'All':
        query += " AND (current_semester=? OR semester=?)"
        params.extend([int(semester_filter), int(semester_filter)])

    if section_filter and section_filter != 'All':
        query += " AND section=?"
        params.append(section_filter.upper())

    all_students = execute_query(query, tuple(params), fetchall=True) or []

    if not all_students:
        return {
            'success': True,
            'departments': [],
            'overall_summary': {
                'total_students': 0,
                'avg_cgpa': 0.0,
                'avg_attendance': 0.0,
                'pass_percentage': 0.0,
                'high_risk_count': 0,
                'avg_ranking_score': 0.0,
                'avg_placement_readiness': 0.0
            },
            'charts': {
                'labels': [],
                'cgpa': [],
                'attendance': [],
                'pass_rate': [],
                'fail_rate': [],
                'high_risk': [],
                'placement_readiness': []
            }
        }

    for student_row in all_students:
        risk = assess_student_risk(student_row)
        student_row.update({k: risk[k] for k in ('risk_level', 'risk_reasons', 'risk_subjects_high', 'risk_subjects_medium', 'risk_subjects_assessed')})

    # Group students by department
    dept_map = {}
    for s in all_students:
        dept = s.get('department') or 'General'
        dept_map.setdefault(dept, []).append(s)

    dept_results = []

    for dept_name, students in dept_map.items():
        count = len(students)
        if count == 0:
            continue

        # 1. CGPA
        cgpa_vals = [float(s.get('cgpa') or 0.0) for s in students]
        avg_cgpa = round(sum(cgpa_vals) / count, 2)

        # 2. Attendance
        att_vals = [float(s.get('attendance') or 0.0) for s in students]
        avg_att = round(sum(att_vals) / count, 1)

        # 3. Predicted Result (Pass / Fail)
        pass_count = sum(1 for s in students if s.get('predicted_result') == 'Pass')
        fail_count = sum(1 for s in students if s.get('predicted_result') == 'Fail')
        pass_pct = round((pass_count / count) * 100.0, 1)
        fail_pct = round((fail_count / count) * 100.0, 1)

        # 4. High Risk Students
        high_risk_cnt = sum(1 for s in students if s.get('risk_level') == 'High')
        med_risk_cnt = sum(1 for s in students if s.get('risk_level') == 'Medium')
        low_risk_cnt = sum(1 for s in students if s.get('risk_level') == 'Low')

        # 5. Internal / IA Marks (normalized to 0-100 scale)
        ia_scores = []
        for s in students:
            st_id = s.get('id')
            valid_subs = []
            if st_id:
                st_m = get_student_ia_marks(st_id)
                for sm in st_m:
                    if sm.get('active', 1) == 1:
                        b_avg = _compute_subject_best_two_avg(sm.get('ia1'), sm.get('ia2'), sm.get('ia3'))
                        if b_avg is not None:
                            valid_subs.append(b_avg)
            if not valid_subs:
                sub_avgs = [
                    _compute_subject_best_two_avg(s.get('ia1_sub1'), s.get('ia2_sub1'), s.get('ia3_sub1')),
                    _compute_subject_best_two_avg(s.get('ia1_sub2'), s.get('ia2_sub2'), s.get('ia3_sub2')),
                    _compute_subject_best_two_avg(s.get('ia1_sub3'), s.get('ia2_sub3'), s.get('ia3_sub3')),
                    _compute_subject_best_two_avg(s.get('ia1_sub4'), s.get('ia2_sub4'), s.get('ia3_sub4'))
                ]
                valid_subs = [v for v in sub_avgs if v is not None]

            if valid_subs:
                ia_scores.append((sum(valid_subs) / len(valid_subs) / 50.0) * 100.0)
            else:
                ia_scores.append(float(s.get('internal_marks') or 70.0))
        avg_ia_score = round(sum(ia_scores) / len(ia_scores), 1) if ia_scores else 70.0

        # 6. Overall Ranking Scores
        rank_scores = [calculate_overall_score(s)['overall_score'] for s in students]
        avg_rank_score = round(sum(rank_scores) / len(rank_scores), 2) if rank_scores else 0.0

        # 7. Placement Readiness
        placement_scores = []
        highly_ready_cnt = 0
        placement_ready_cnt = 0
        needs_improvement_cnt = 0
        not_ready_cnt = 0

        for s in students:
            p_res = calculate_placement_readiness(s)
            score = p_res['readiness_score']
            placement_scores.append(score)
            cat = p_res['category']
            if cat == CATEGORY_HIGHLY_READY:
                highly_ready_cnt += 1
            elif cat == CATEGORY_PLACEMENT_READY:
                placement_ready_cnt += 1
            elif cat == CATEGORY_NEEDS_IMPROVEMENT:
                needs_improvement_cnt += 1
            else:
                not_ready_cnt += 1

        avg_placement_score = round(sum(placement_scores) / len(placement_scores), 1) if placement_scores else 0.0

        # 8. Department Performance Composite Ranking Score
        # Formula:
        #   Avg CGPA (25%) + Avg Attendance (20%) + Pass Rate (20%) + Avg IA (15%) + Avg Ranking (10%) + Avg Placement (10%)
        dept_composite_score = (
            ((avg_cgpa / 10.0) * 100.0 * 0.25) +
            (avg_att * 0.20) +
            (pass_pct * 0.20) +
            (avg_ia_score * 0.15) +
            (avg_rank_score * 0.10) +
            (avg_placement_score * 0.10)
        )
        dept_composite_score = round(min(100.0, max(0.0, dept_composite_score)), 2)

        dept_results.append({
            'department': dept_name,
            'student_count': count,
            'avg_cgpa': avg_cgpa,
            'avg_attendance': avg_att,
            'pass_count': pass_count,
            'fail_count': fail_count,
            'pass_percentage': pass_pct,
            'fail_percentage': fail_pct,
            'high_risk_count': high_risk_cnt,
            'medium_risk_count': med_risk_cnt,
            'low_risk_count': low_risk_cnt,
            'avg_internal_marks': avg_ia_score,
            'avg_ranking_score': avg_rank_score,
            'avg_placement_readiness': avg_placement_score,
            'highly_ready_count': highly_ready_cnt,
            'placement_ready_count': placement_ready_cnt,
            'needs_improvement_count': needs_improvement_cnt,
            'not_ready_count': not_ready_cnt,
            'composite_score': dept_composite_score
        })

    # Sort departments by composite_score DESC to assign Department Rank
    dept_results.sort(key=lambda x: x['composite_score'], reverse=True)
    for idx, d in enumerate(dept_results):
        d['department_rank'] = idx + 1

    # College-wide overall summary
    total_stus = len(all_students)
    overall_summary = {
        'total_students': total_stus,
        'department_count': len(dept_results),
        'avg_cgpa': round(sum(d['avg_cgpa'] * d['student_count'] for d in dept_results) / total_stus, 2) if total_stus > 0 else 0.0,
        'avg_attendance': round(sum(d['avg_attendance'] * d['student_count'] for d in dept_results) / total_stus, 1) if total_stus > 0 else 0.0,
        'pass_percentage': round(sum(d['pass_count'] for d in dept_results) / total_stus * 100.0, 1) if total_stus > 0 else 0.0,
        'high_risk_count': sum(d['high_risk_count'] for d in dept_results),
        'avg_ranking_score': round(sum(d['avg_ranking_score'] * d['student_count'] for d in dept_results) / total_stus, 2) if total_stus > 0 else 0.0,
        'avg_placement_readiness': round(sum(d['avg_placement_readiness'] * d['student_count'] for d in dept_results) / total_stus, 1) if total_stus > 0 else 0.0
    }

    # Chart datasets formatting
    chart_data = {
        'labels': [d['department'] for d in dept_results],
        'cgpa': [d['avg_cgpa'] for d in dept_results],
        'attendance': [d['avg_attendance'] for d in dept_results],
        'pass_rate': [d['pass_percentage'] for d in dept_results],
        'fail_rate': [d['fail_percentage'] for d in dept_results],
        'high_risk': [d['high_risk_count'] for d in dept_results],
        'placement_readiness': [d['avg_placement_readiness'] for d in dept_results],
        'composite_scores': [d['composite_score'] for d in dept_results]
    }

    return {
        'success': True,
        'departments': dept_results,
        'overall_summary': overall_summary,
        'charts': chart_data
    }
