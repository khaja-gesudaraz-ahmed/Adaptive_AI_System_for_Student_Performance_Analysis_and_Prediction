"""
Student Ranking System Service
Calculates overall academic performance scores based on the weighted formula:
  1. Current CGPA                = 30% (normalized to 0-100: CGPA / 10.0 * 100)
  2. Past Academic Performance   = 25% (normalized from actual semester_history SGPAs)
  3. Internal Marks (IA)         = 15% (normalized from live subject-wise IA Best Two averages: score / 50.0 * 100)
  4. Attendance                  = 10% (actual attendance percentage 0-100)
  5. Consistency                 = 10% (variance-based consistency score 0-100)
  6. Improvement                 = 10% (historical trend delta score 0-100)
  Total = 100%

Produces College Rank, Department Rank, Class Rank (Dept + Sem + Section), and tracks Rank Change via ranking_history.
"""
from services.db_service import execute_query, get_student_ia_marks


def _compute_subject_best_two_avg(ia1, ia2, ia3):
    """Best-two IA average out of 50; AB and unentered marks count as zero."""
    marks = []
    for value in (ia1, ia2, ia3):
        if value is None or str(value).strip().upper() in ('AB', 'ABSENT', '-', '—', ''):
            marks.append(0.0)
            continue
        try:
            marks.append(max(0.0, min(50.0, float(value))))
        except (ValueError, TypeError):
            marks.append(0.0)
    return round(sum(sorted(marks, reverse=True)[:2]) / 2.0, 1)

def calculate_overall_score(student_record):
    """
    Calculates normalized ranking factor scores (0-100) and overall weighted score.
    
    Formula:
      CGPA (30%) + Past SGPA (25%) + Internal Marks (15%) + Attendance (10%) + Consistency (10%) + Improvement (10%)
    """
    student_id = student_record.get('id')

    # 1. Current CGPA Score (30%) -> 0-100 scale
    cgpa_raw = float(student_record.get('cgpa') or 0.0)
    if cgpa_raw <= 0.0:
        # Fallback to calculated CGPA or baseline
        cgpa_score = float(student_record.get('prev_sem_percentage') or 70.0)
        cgpa_raw = round(cgpa_score / 10.0, 2)
    else:
        cgpa_score = min(100.0, max(0.0, (cgpa_raw / 10.0) * 100.0))

    # 2. Past Academic Performance (25%) -> 0-100 scale
    history_rows = []
    if student_id:
        history_rows = execute_query(
            "SELECT semester, sgpa FROM semester_history WHERE student_id=? AND sgpa IS NOT NULL AND sgpa > 0 ORDER BY semester ASC",
            (student_id,), fetchall=True
        ) or []

    historical_sgpas = [float(r['sgpa']) for r in history_rows if r.get('sgpa') is not None and float(r['sgpa']) > 0]

    if historical_sgpas:
        avg_past_sgpa = sum(historical_sgpas) / len(historical_sgpas)
        past_academic_score = min(100.0, max(0.0, (avg_past_sgpa / 10.0) * 100.0))
    else:
        past_academic_score = float(student_record.get('twelfth_percentage') or student_record.get('tenth_percentage') or cgpa_score)
        past_academic_score = min(100.0, max(0.0, past_academic_score))

    # 3. Internal Marks (15%) -> 0-100 scale
    # Uses actual dynamic teacher-entered IA marks across all active subjects
    valid_ia_avgs = []
    if student_id:
        st_marks = get_student_ia_marks(student_id)
        for sm in st_marks:
            if sm.get('active', 1) == 1:
                b_avg = _compute_subject_best_two_avg(sm.get('ia1'), sm.get('ia2'), sm.get('ia3'))
                if b_avg is not None:
                    valid_ia_avgs.append(b_avg)

    if not valid_ia_avgs:
        sub1_avg = _compute_subject_best_two_avg(student_record.get('ia1_sub1'), student_record.get('ia2_sub1'), student_record.get('ia3_sub1'))
        sub2_avg = _compute_subject_best_two_avg(student_record.get('ia1_sub2'), student_record.get('ia2_sub2'), student_record.get('ia3_sub2'))
        sub3_avg = _compute_subject_best_two_avg(student_record.get('ia1_sub3'), student_record.get('ia2_sub3'), student_record.get('ia3_sub3'))
        sub4_avg = _compute_subject_best_two_avg(student_record.get('ia1_sub4'), student_record.get('ia2_sub4'), student_record.get('ia3_sub4'))
        valid_ia_avgs = [v for v in [sub1_avg, sub2_avg, sub3_avg, sub4_avg] if v is not None]

    if valid_ia_avgs:
        mean_ia_50 = sum(valid_ia_avgs) / len(valid_ia_avgs)
        internal_score = min(100.0, max(0.0, (mean_ia_50 / 50.0) * 100.0))
    else:
        internal_raw = float(student_record.get('internal_marks') or 70.0)
        internal_score = min(100.0, max(0.0, internal_raw))

    # 4. Attendance (10%) -> 0-100 scale
    attendance_score = min(100.0, max(0.0, float(student_record.get('attendance') or 0.0)))

    # 5. Consistency (10%) -> 0-100 scale
    # Evaluates stability across semester SGPAs and/or internal subject marks
    data_points = []
    if historical_sgpas:
        data_points.extend([(s / 10.0) * 100.0 for s in historical_sgpas])
    if valid_ia_avgs:
        data_points.extend([(v / 50.0) * 100.0 for v in valid_ia_avgs])

    if len(data_points) >= 2:
        mean_val = sum(data_points) / len(data_points)
        variance = sum((x - mean_val) ** 2 for x in data_points) / len(data_points)
        std_dev = variance ** 0.5
        # Low std_dev -> High Consistency Score (std_dev 0 gives 100.0)
        consistency_score = min(100.0, max(0.0, 100.0 - (std_dev * 2.5)))
    else:
        # When single data point, baseline reflects current performance stability
        consistency_score = min(100.0, max(60.0, cgpa_score))

    # 6. Improvement (10%) -> 0-100 scale
    # Measures performance progression across semesters
    if len(historical_sgpas) >= 2:
        # Trend from first to latest recorded SGPA
        sgpa_delta = historical_sgpas[-1] - historical_sgpas[0]
        # A positive delta increases score above 50, a negative delta decreases it
        # +2.0 SGPA delta = +20% delta -> Score 100
        improvement_score = min(100.0, max(0.0, 50.0 + (sgpa_delta * 25.0)))
    elif historical_sgpas:
        delta = (cgpa_raw * 10.0) - float(student_record.get('twelfth_percentage') or (cgpa_raw * 10.0))
        improvement_score = min(100.0, max(0.0, 50.0 + (delta * 1.5)))
    else:
        delta = cgpa_score - float(student_record.get('twelfth_percentage') or cgpa_score)
        improvement_score = min(100.0, max(0.0, 50.0 + (delta * 1.5)))

    # 7. Exact Weighted Overall Score Calculation
    overall_score = (
        (cgpa_score * 0.30) +
        (past_academic_score * 0.25) +
        (internal_score * 0.15) +
        (attendance_score * 0.10) +
        (consistency_score * 0.10) +
        (improvement_score * 0.10)
    )

    overall_score = round(min(100.0, max(0.0, overall_score)), 2)

    return {
        'overall_score': overall_score,
        'ranking_score': overall_score,
        'cgpa_score': round(cgpa_score, 1),
        'past_academic_score': round(past_academic_score, 1),
        'internal_score': round(internal_score, 1),
        'attendance_score': round(attendance_score, 1),
        'consistency_score': round(consistency_score, 1),
        'improvement_score': round(improvement_score, 1),
        'factors': {
            'cgpa': {'weight': '30%', 'value': round(cgpa_raw, 2), 'score': round(cgpa_score, 1)},
            'past_academic': {'weight': '25%', 'sgpas': historical_sgpas, 'score': round(past_academic_score, 1)},
            'internal_marks': {'weight': '15%', 'subjects_evaluated': len(valid_ia_avgs), 'score': round(internal_score, 1)},
            'attendance': {'weight': '10%', 'value': f"{attendance_score:.1f}%", 'score': round(attendance_score, 1)},
            'consistency': {'weight': '10%', 'score': round(consistency_score, 1)},
            'improvement': {'weight': '10%', 'score': round(improvement_score, 1)}
        }
    }


def compute_rankings(all_students, record_history=False):
    """
    Computes overall score, College Rank, Department Rank, Class Rank,
    calculates Rank Change from ranking_history, and identifies awards and insights.
    """
    if not all_students:
        return {
            'ranked_students': [],
            'top_10': [],
            'top_3': [],
            'most_improved': None,
            'best_attendance': None,
            'most_consistent': None,
            'improved_students': [],
            'dropped_students': []
        }

    scored_list = []
    for s in all_students:
        scores = calculate_overall_score(s)
        scored_entry = dict(s)
        scored_entry.update(scores)
        scored_list.append(scored_entry)

    # 1. College-wide Ranking (all approved students)
    scored_list.sort(key=lambda x: x['overall_score'], reverse=True)
    for idx, s in enumerate(scored_list):
        s['college_rank'] = idx + 1
        s['overall_rank'] = idx + 1
        s['is_top_10'] = 1 if idx < 10 else 0
        s['is_top_3'] = 1 if idx < 3 else 0

    # 2. Department Ranking (same department)
    dept_groups = {}
    for s in scored_list:
        dept = s.get('department') or 'CSE'
        dept_groups.setdefault(dept, []).append(s)

    for dept, group in dept_groups.items():
        group.sort(key=lambda x: x['overall_score'], reverse=True)
        for idx, s in enumerate(group):
            s['department_rank'] = idx + 1
            s['dept_rank'] = idx + 1

    # 3. Class Ranking (same department + semester + section)
    class_groups = {}
    for s in scored_list:
        dept = s.get('department') or 'CSE'
        sem = s.get('current_semester') or s.get('semester') or 6
        sec = (s.get('section') or 'A').upper()
        key = f"{dept}_{sem}_{sec}"
        class_groups.setdefault(key, []).append(s)

    for key, group in class_groups.items():
        group.sort(key=lambda x: x['overall_score'], reverse=True)
        for idx, s in enumerate(group):
            s['class_rank'] = idx + 1

    # 4. Rank Change calculation from ranking_history
    improved_students = []
    dropped_students = []

    for s in scored_list:
        sid = s.get('id')
        prev_row = None
        if sid:
            prev_row = execute_query(
                "SELECT college_rank, ranking_score FROM ranking_history WHERE student_id=? ORDER BY id DESC LIMIT 1",
                (sid,), fetchone=True
            )

        if prev_row and prev_row.get('college_rank') is not None:
            prev_rank = int(prev_row['college_rank'])
            curr_rank = int(s['college_rank'])
            rank_diff = prev_rank - curr_rank  # Positive means rank improved (e.g. 25 -> 18 = +7)

            if rank_diff > 0:
                s['rank_change'] = f"+{rank_diff}"
                s['rank_change_num'] = rank_diff
                s['rank_change_status'] = 'improved'
                improved_students.append(s)
            elif rank_diff < 0:
                s['rank_change'] = f"{rank_diff}"
                s['rank_change_num'] = rank_diff
                s['rank_change_status'] = 'dropped'
                dropped_students.append(s)
            else:
                s['rank_change'] = "0"
                s['rank_change_num'] = 0
                s['rank_change_status'] = 'same'
        else:
            s['rank_change'] = "New"
            s['rank_change_num'] = 0
            s['rank_change_status'] = 'new'

        # Optionally record snapshot in ranking_history
        if record_history and sid:
            execute_query("""
                INSERT INTO ranking_history (student_id, ranking_score, college_rank, department_rank, class_rank)
                VALUES (?, ?, ?, ?, ?)
            """, (sid, s['overall_score'], s['college_rank'], s['department_rank'], s['class_rank']), commit=True)

    # 5. Ranking Awards & Insights
    most_improved = max(scored_list, key=lambda x: x['improvement_score'], default=None)
    best_attendance = max(scored_list, key=lambda x: x['attendance_score'], default=None)
    most_consistent = max(scored_list, key=lambda x: x['consistency_score'], default=None)

    if most_improved:
        most_improved['award'] = 'Most Improved Performer'
    if best_attendance:
        best_attendance['award'] = 'Best Attendance Award'
    if most_consistent:
        most_consistent['award'] = 'Most Consistent Academic Performer'

    return {
        'ranked_students': scored_list,
        'top_10': scored_list[:10],
        'top_3': scored_list[:3],
        'most_improved': most_improved,
        'best_attendance': best_attendance,
        'most_consistent': most_consistent,
        'improved_students': improved_students,
        'dropped_students': dropped_students
    }


def get_student_ranking(student_id):
    """
    Returns ranking details, scores, factor breakdown, and class context for a single student.
    """
    all_students = execute_query("SELECT * FROM students WHERE approval_status='Approved' OR approval_status IS NULL", fetchall=True) or []
    rankings = compute_rankings(all_students, record_history=False)
    
    student_rank = next((s for s in rankings['ranked_students'] if s.get('id') == student_id), None)
    return {
        'success': True if student_rank else False,
        'ranking': student_rank,
        'insights': {
            'top_3': rankings['top_3'],
            'most_improved': rankings['most_improved'],
            'best_attendance': rankings['best_attendance'],
            'most_consistent': rankings['most_consistent']
        }
    }
