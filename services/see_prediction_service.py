"""Rule-based, explainable SEE forecast using existing IA records.

The forecast is an early-warning estimate, not a trained/validated ML probability.
Configured baseline: CIE >= 20/50, SEE >= 20/50 (so 18/50 is treated as fail
as requested for this project), and CIE + SEE >= 40/100. Verify these thresholds
against the student's exact VTU scheme/curriculum before official use.
"""
from services.db_service import get_student_ia_marks, get_class_subjects

CIE_MIN = 20.0
SEE_MIN = 20.0
TOTAL_MIN = 40.0


def _number(value):
    if value is None or value == '' or str(value).strip().upper() in {'AB', 'ABSENT', '-', '—', 'NULL'}:
        return None
    try:
        n = float(value)
        return n if 0 <= n <= 50 else None
    except (ValueError, TypeError):
        return None


def best_two_average(ia1, ia2, ia3):
    """Best-two IA average, matching the existing teacher/student calculation.

    Blank values mean no mark entered; AB/ABSENT is a recorded zero. If only
    one numeric IA is available, average it with zero (mark + 0) / 2. With two
    numeric IAs, average those two. All blank values remain insufficient data.
    """
    raw_values = (ia1, ia2, ia3)
    numeric = []
    has_recorded_absence = False
    for raw in raw_values:
        if raw is None or str(raw).strip().upper() in {'', '-', '—', 'NULL'}:
            continue
        if str(raw).strip().upper() in {'AB', 'ABSENT'}:
            numeric.append(0.0)
            has_recorded_absence = True
            continue
        value = _number(raw)
        if value is not None:
            numeric.append(value)
    if not numeric:
        return 0.0 if has_recorded_absence else None
    numeric = sorted(numeric, reverse=True)[:2]
    if len(numeric) == 1:
        numeric.append(0.0)
    return round(sum(numeric) / 2.0, 1)


def predict_subject_see(cie, previous_sem_percentage=None):
    """Return consistent SEE forecast and VTU-style threshold checks for one subject."""
    if cie is None:
        return {
            'cie': None, 'predicted_see': None, 'required_see': None,
            'predicted_total': None, 'prediction': 'Insufficient Data',
            'risk': 'Unknown', 'reason': 'Enter at least one valid IA mark.'
        }

    # A transparent baseline: 70% current subject IA performance + 30% prior-semester
    # percentage converted to /50. If no prior-semester data exists, use IA alone.
    prev = None
    try:
        if previous_sem_percentage not in (None, ''):
            prev = max(0.0, min(100.0, float(previous_sem_percentage))) / 2.0
    except (ValueError, TypeError):
        prev = None
    estimate = 0.7 * cie + 0.3 * prev if prev is not None else cie
    predicted_see = round(max(0.0, min(50.0, estimate)), 1)
    required_see = max(SEE_MIN, TOTAL_MIN - cie)
    predicted_total = round(cie + predicted_see, 1)

    passes = cie >= CIE_MIN and predicted_see >= SEE_MIN and predicted_total >= TOTAL_MIN
    if not passes:
        risk = 'High'
        prediction = 'At Risk of Failing'
        reasons = []
        if cie < CIE_MIN:
            reasons.append(f'CIE below {CIE_MIN:g}/50')
        if predicted_see < SEE_MIN:
            reasons.append(f'forecast SEE below {SEE_MIN:g}/50')
        if predicted_total < TOTAL_MIN:
            reasons.append(f'forecast total below {TOTAL_MIN:g}/100')
        reason = '; '.join(reasons)
    elif predicted_see < SEE_MIN + 5 or predicted_total < TOTAL_MIN + 5:
        risk = 'Medium'
        prediction = 'Borderline Pass'
        reason = 'Forecast is close to the minimum passing requirements.'
    else:
        risk = 'Low'
        prediction = 'Likely Pass'
        reason = 'Forecast meets the configured minimum passing requirements.'

    return {
        'cie': round(cie, 1), 'predicted_see': predicted_see,
        'required_see': round(required_see, 1), 'predicted_total': predicted_total,
        'prediction': prediction, 'risk': risk, 'reason': reason
    }


def predict_student_see(student, subject_rows=None):
    """Forecast every active subject for a student using their stored IA marks."""
    student_id = student.get('id')
    if subject_rows is None:
        subject_rows = get_student_ia_marks(student_id) if student_id else []
    active_rows = [r for r in (subject_rows or []) if r.get('active', 1) == 1]
    if not active_rows and student_id:
        dept = student.get('department') or 'CSE'
        sem = student.get('current_semester') or student.get('semester') or 6
        sec = student.get('section') or 'A'
        active_rows = [dict(s, ia1=None, ia2=None, ia3=None) for s in get_class_subjects(dept, sem, sec, active_only=True)]

    result = []
    for row in active_rows:
        cie = best_two_average(row.get('ia1'), row.get('ia2'), row.get('ia3'))
        pred = predict_subject_see(cie, student.get('prev_sem_percentage'))
        result.append({
            'subject': row.get('subject_name') or row.get('subject') or 'Subject',
            'subject_id': row.get('subject_id') or row.get('id'),
            **pred
        })
    return result


def summarize_student_see(student, subject_predictions=None):
    predictions = subject_predictions if subject_predictions is not None else predict_student_see(student)
    known = [p for p in predictions if p.get('prediction') != 'Insufficient Data']
    at_risk = sum(p.get('risk') == 'High' for p in known)
    borderline = sum(p.get('risk') == 'Medium' for p in known)
    return {
        'subjects': predictions,
        'subjects_with_data': len(known),
        'at_risk_subjects': at_risk,
        'borderline_subjects': borderline,
        'likely_pass_subjects': sum(p.get('risk') == 'Low' for p in known),
        'overall_prediction': ('Insufficient Data' if not known else
                               'At Risk' if at_risk else
                               'Borderline' if borderline else 'Likely Pass')
    }
