"""
AI Personalized Study Planner Service
Generates dynamic weekly study schedules tailored to student weak subjects (low IA marks).
Allocates dedicated extra study time:
- Below 18 marks (< 18/50): Very Low Performance -> HIGH PRIORITY (2 hours/day)
- 18 to below 30 marks (18-29.99/50): Low Performance -> MEDIUM PRIORITY (1 hour/day)
- 30 and above (>= 30/50): Normal -> No additional mandatory study time
"""
import os
import json

from services.db_service import get_student_ia_marks, get_class_subjects


def _compute_subject_score(student_data, sub_num, default_col=None):
    """
    Computes best two IA average out of 50 for a subject from DB ia1/ia2/ia3 columns.
    Falls back to 100-mark scaled to 50 if IA test marks are not yet present.
    """
    prefix = f"sub{sub_num}"
    ia1 = student_data.get(f'ia1_{prefix}')
    ia2 = student_data.get(f'ia2_{prefix}')
    ia3 = student_data.get(f'ia3_{prefix}')

    numeric_marks = []
    for val in [ia1, ia2, ia3]:
        try:
            if val not in ["AB", "-", "", None]:
                numeric_marks.append(float(val))
        except (ValueError, TypeError):
            pass

    if len(numeric_marks) >= 2:
        sorted_m = sorted(numeric_marks, reverse=True)
        return round((sorted_m[0] + sorted_m[1]) / 2.0, 1)
    elif len(numeric_marks) == 1:
        return round(numeric_marks[0], 1)
    else:
        # Fallback to 100-scale column scaled to 50
        if default_col:
            val100 = student_data.get(default_col)
            if val100 is not None:
                try:
                    return round(float(val100) * 0.5, 1)
                except (ValueError, TypeError):
                    pass
        return 35.0  # Safe default (normal performance)


def evaluate_student_subjects(student_data):
    """
    Evaluates all active subjects based on live database marks.
    Classifies performance into Very Low (< 18), Low (18-29.99), and Normal (>= 30).
    """
    st_id = student_data.get('id')
    subjects = []
    if st_id:
        st_m = get_student_ia_marks(st_id)
        for sm in st_m:
            if sm.get('active', 1) == 1:
                ia1 = sm.get('ia1')
                ia2 = sm.get('ia2')
                ia3 = sm.get('ia3')
                
                numeric = []
                for v in [ia1, ia2, ia3]:
                    try:
                        if v not in ['AB', 'ABSENT', '-', '—', '', None]:
                            numeric.append(float(v))
                    except (ValueError, TypeError):
                        pass
                
                if len(numeric) >= 2:
                    sorted_m = sorted(numeric, reverse=True)
                    sub_score = round((sorted_m[0] + sorted_m[1]) / 2.0, 1)
                elif len(numeric) == 1:
                    sub_score = round(numeric[0], 1)
                else:
                    sub_score = 35.0
                
                s_name = sm['subject_name']
                subjects.append({
                    "code": f"SUB{sm['subject_id']}",
                    "name": s_name,
                    "full_name": s_name,
                    "score": sub_score,
                    "recommended_high": f"Revise core concepts, solve previous questions, and practice problem solving for {s_name}.",
                    "recommended_med": f"Review key topics, formulas, and weak areas in {s_name}."
                })

    if not subjects:
        s1_score = _compute_subject_score(student_data, 1, 'dbms_marks')
        s2_score = _compute_subject_score(student_data, 2, 'java_marks')
        s3_score = _compute_subject_score(student_data, 3, 'subject3_marks')
        s4_score = _compute_subject_score(student_data, 4, 'subject4_marks')

        subjects = [
            {
                "code": "21CS51",
                "name": "DBMS",
                "full_name": "Database Management Systems (DBMS)",
                "score": s1_score,
                "recommended_high": "Practice SQL queries, normalization, ER diagrams and solve previous IA questions.",
                "recommended_med": "Practice SQL queries, indexing, transactions and review weak DBMS topics."
            },
            {
                "code": "21CS52",
                "name": "Java",
                "full_name": "Java Programming",
                "score": s2_score,
                "recommended_high": "Practice core Java programming, OOP concepts, exception handling and coding exercises.",
                "recommended_med": "Practice Java collections, multithreading, OOP problem solving and syntax practice."
            },
            {
                "code": "21CS53",
                "name": "Computer Networks",
                "full_name": "Computer Networks",
                "score": s3_score,
                "recommended_high": "Study OSI/TCP-IP layers, IP addressing, subnetting, network protocols and past questions.",
                "recommended_med": "Review routing algorithms, TCP/UDP protocols, DNS/HTTP concepts and network diagrams."
            },
            {
                "code": "21CS54",
                "name": "Software Engineering",
                "full_name": "Software Engineering",
                "score": s4_score,
                "recommended_high": "Review Agile SDLC, design patterns, UML diagrams, requirements engineering and past questions.",
                "recommended_med": "Practice UML use-case design, software testing principles, QA metrics and project design."
            }
        ]

    for sub in subjects:
        score = sub["score"]
        if score < 18.0:
            sub["performance_level"] = "Very Low Performance"
            sub["priority"] = "HIGH"
            sub["duration"] = "2 hours"
            sub["duration_hours"] = 2.0
            sub["activity"] = sub["recommended_high"]
            sub["is_weak"] = True
        elif score < 30.0:
            sub["performance_level"] = "Low Performance"
            sub["priority"] = "MEDIUM"
            sub["duration"] = "1 hour"
            sub["duration_hours"] = 1.0
            sub["activity"] = sub["recommended_med"]
            sub["is_weak"] = True
        else:
            sub["performance_level"] = "Normal Performance"
            sub["priority"] = "NORMAL"
            sub["duration"] = "None"
            sub["duration_hours"] = 0.0
            sub["activity"] = "Maintain consistent revision with regular coursework."
            sub["is_weak"] = False

    return subjects


def generate_study_plan(student_data, weak_subjects=None, risk_level='Low'):
    """
    Generates a structured weekly schedule (Monday to Sunday) based on weak subjects.
    Prioritizes low-mark subjects:
    - < 18 marks: 2 hours/day (HIGH priority)
    - 18 to < 30 marks: 1 hour/day (MEDIUM priority)
    - >= 30 marks: normal revision
    """
    all_subjects = evaluate_student_subjects(student_data)
    weak_list = [s for s in all_subjects if s["is_weak"]]

    # Sort weak subjects so HIGH priority appears before MEDIUM priority
    weak_list.sort(key=lambda s: 0 if s["priority"] == "HIGH" else 1)

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    schedule = {}

    if weak_list:
        daily_hours = sum(s["duration_hours"] for s in weak_list)
        for day in days:
            schedule[day] = [
                {
                    "subject": w["name"],
                    "full_name": w["full_name"],
                    "marks": f"{w['score']}/50",
                    "score": w["score"],
                    "performance_level": w["performance_level"],
                    "priority": w["priority"],
                    "duration": w["duration"],
                    "activity": w["activity"]
                }
                for w in weak_list
            ]
    else:
        # All subjects are >= 30/50 - Normal maintenance schedule
        daily_hours = 1.0
        for day in days:
            schedule[day] = [
                {
                    "subject": "Core Revision & Practice",
                    "full_name": "Core Engineering Revision & Advanced Practice",
                    "marks": "All >= 30/50",
                    "score": 35.0,
                    "performance_level": "Good Performance",
                    "priority": "NORMAL",
                    "duration": "1 hour",
                    "activity": "Maintain regular revision, practice coding problems, and work on academic projects."
                }
            ]

    recommendations = []
    for w in weak_list:
        if w["priority"] == "HIGH":
            recommendations.append(f"CRITICAL: {w['name']} scored {w['score']}/50 (Very Low). Allocate 2 hours daily for remedial practice.")
        else:
            recommendations.append(f"ATTENTION: {w['name']} scored {w['score']}/50 (Low). Allocate 1 hour daily to strengthen key topics.")

    if not recommendations:
        recommendations.append("All subjects have internal scores of 30/50 or higher. Keep up the consistent performance!")

    return {
        "weekly_target_hours": round(daily_hours * 7, 1),
        "risk_level": risk_level,
        "weak_subjects_count": len(weak_list),
        "weak_subjects": [w["name"] for w in weak_list],
        "schedule": schedule,
        "ai_recommendations": recommendations
    }
