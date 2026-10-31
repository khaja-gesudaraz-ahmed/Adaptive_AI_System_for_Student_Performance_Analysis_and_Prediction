"""Centralized, explainable academic risk assessment used by dashboards and reports.

Risk is recomputed from current subject IA records and the shared SEE forecast;
legacy ML risk_level stored at registration is not treated as current truth.
"""
from services.see_prediction_service import predict_student_see


def assess_student_risk(student, subject_rows=None):
    reasons = []
    try:
        attendance = float(student.get('attendance')) if student.get('attendance') not in (None, '') else None
    except (TypeError, ValueError):
        attendance = None
    try:
        cgpa = float(student.get('cgpa')) if student.get('cgpa') not in (None, '') else None
    except (TypeError, ValueError):
        cgpa = None
    try:
        backlogs = int(student.get('active_backlogs') or 0)
    except (TypeError, ValueError):
        backlogs = 0

    predictions = predict_student_see(student, subject_rows=subject_rows)
    valid_predictions = [p for p in predictions if p.get('prediction') != 'Insufficient Data']
    high_subjects = [p for p in valid_predictions if p.get('risk') == 'High']
    medium_subjects = [p for p in valid_predictions if p.get('risk') == 'Medium']

    if attendance is not None and attendance < 60:
        reasons.append(f'Attendance is below 60% ({attendance:g}%).')
    if cgpa is not None and cgpa < 5.0:
        reasons.append(f'CGPA is below 5.0 ({cgpa:g}).')
    if backlogs > 0:
        reasons.append(f'{backlogs} active backlog(s).')
    if high_subjects:
        names = ', '.join(p.get('subject', 'Subject') for p in high_subjects[:4])
        reasons.append(f'Subject-level SEE forecast indicates failure risk: {names}.')

    if ((attendance is not None and attendance < 60) or
            (cgpa is not None and cgpa < 5.0) or backlogs > 0 or high_subjects):
        level = 'High'
    elif ((attendance is not None and attendance < 75) or
          (cgpa is not None and cgpa < 6.0) or medium_subjects):
        level = 'Medium'
        if attendance is not None and attendance < 75:
            reasons.append(f'Attendance is below 75% ({attendance:g}%).')
        if cgpa is not None and cgpa < 6.0:
            reasons.append(f'CGPA is below 6.0 ({cgpa:g}).')
        if medium_subjects:
            names = ', '.join(p.get('subject', 'Subject') for p in medium_subjects[:4])
            reasons.append(f'Borderline SEE forecast in: {names}.')
    elif not valid_predictions:
        level = 'Unknown'
        reasons.append('No valid subject IA marks are available; enter marks before assigning a low-risk label.')
    else:
        level = 'Low'
        reasons.append('No current high-risk indicators found in available academic data.')

    return {
        'risk_level': level,
        'risk_reasons': reasons,
        'risk_subjects_high': len(high_subjects),
        'risk_subjects_medium': len(medium_subjects),
        'risk_subjects_assessed': len(valid_predictions),
        'see_predictions': predictions,
    }
