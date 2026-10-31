"""
PDF Report Generator Service
Generates styled ReportLab PDF documents for Individual Students and Complete Class Overview.
Includes Student Profile, Subject-wise Internal Assessment (IA) Performance, CGPA & SGPAs,
Attendance, Evaluation Summary, and Teacher Remarks.
"""
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import datetime

from services.db_service import get_student_ia_marks, get_class_subjects
from services.see_prediction_service import predict_student_see, summarize_student_see


def compute_subject_ia_data(student):
    """
    Computes subject-wise IA-1, IA-2, IA-3 marks and Best Two IA Average out of 50.
    Handles missing marks gracefully as '—'.
    """
    def fmt_val(v):
        if v is None or v == '' or v == '-' or v == '—':
            return '—'
        return str(v)

    def best_two(ia1, ia2, ia3):
        numeric = []
        for v in [ia1, ia2, ia3]:
            try:
                if v not in ['AB', 'ABSENT', '-', '—', '', None]:
                    numeric.append(float(v))
            except (ValueError, TypeError):
                pass
        if len(numeric) >= 2:
            s = sorted(numeric, reverse=True)
            return round((s[0] + s[1]) / 2.0, 1)
        elif len(numeric) == 1:
            return round(numeric[0], 1)
        return '—'

    st_id = student.get('id')
    res = []
    if st_id:
        st_m = get_student_ia_marks(st_id)
        for sm in st_m:
            if sm.get('active', 1) == 1:
                ia1 = sm.get('ia1')
                ia2 = sm.get('ia2')
                ia3 = sm.get('ia3')
                b_val = best_two(ia1, ia2, ia3)
                res.append({
                    "subject": sm['subject_name'],
                    "full_name": sm['subject_name'],
                    "code": f"SUB{sm['subject_id']}",
                    "ia1": fmt_val(ia1),
                    "ia2": fmt_val(ia2),
                    "ia3": fmt_val(ia3),
                    "best_two": str(b_val) if b_val != '—' else '—'
                })

    if not res:
        dept = student.get('department', 'CSE')
        sem = student.get('current_semester') or student.get('semester') or 6
        sec = student.get('section', 'A')
        active_subs = get_class_subjects(dept, sem, sec, active_only=True)
        for sub in active_subs:
            res.append({
                "subject": sub['subject_name'],
                "full_name": sub['subject_name'],
                "code": f"SUB{sub['id']}",
                "ia1": '—',
                "ia2": '—',
                "ia3": '—',
                "best_two": '—'
            })

    return res


def generate_pdf_report(student, details):
    """
    Generates Individual Student Analytics PDF Report.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom Color Palette
    PRIMARY = colors.HexColor('#0F172A')    # Slate 900
    ACCENT = colors.HexColor('#2563EB')     # Royal Blue
    SUCCESS = colors.HexColor('#10B981')    # Emerald
    WARNING = colors.HexColor('#F59E0B')    # Amber
    DANGER = colors.HexColor('#EF4444')     # Red
    LIGHT_BG = colors.HexColor('#F8FAFC')   # Light Gray
    TEXT_MUTED = colors.HexColor('#64748B') # Muted Slate

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=PRIMARY,
        spaceAfter=2
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=TEXT_MUTED,
        spaceAfter=10
    )

    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=PRIMARY,
        spaceBefore=8,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=PRIMARY
    )

    header_cell = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=colors.white
    )

    story = []

    # 1. Header Branding
    header_data = [
        [
            Paragraph("<b>ADAPTIVE STUDENT PERFORMANCE ANALYZER</b>", title_style),
            Paragraph(f"<b>Generated:</b> {datetime.datetime.now().strftime('%d %b %Y, %I:%M %p')}", subtitle_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[360, 180])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'RIGHT')
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6))

    # 2. Student Profile Summary Box
    sem_val = student.get('current_semester') or student.get('semester') or 6
    sec_val = student.get('section') or 'A'
    st_info = [
        [Paragraph(f"<b>Student Name:</b> {student.get('name', 'N/A')}", body_style), Paragraph(f"<b>USN:</b> {student.get('usn', 'N/A')}", body_style)],
        [Paragraph(f"<b>Department:</b> {student.get('department', 'CSE')}", body_style), Paragraph(f"<b>Semester / Section:</b> Sem {sem_val} (Sec {sec_val})", body_style)],
        [Paragraph(f"<b>Email:</b> {student.get('email', 'N/A')}", body_style), Paragraph(f"<b>Phone:</b> {student.get('phone', 'N/A')}", body_style)]
    ]
    profile_table = Table(st_info, colWidths=[270, 270])
    profile_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(profile_table)
    story.append(Spacer(1, 8))

    # 3. Subject-wise Internal Assessment (IA) Performance Table
    story.append(Paragraph("Internal Assessment Performance (Each IA out of 50)", section_heading))
    ia_subjects = details.get('ia_subjects') or compute_subject_ia_data(student)

    ia_table_data = [
        [
            Paragraph("<b>Subject</b>", header_cell),
            Paragraph("<b>IA-1 (/50)</b>", header_cell),
            Paragraph("<b>IA-2 (/50)</b>", header_cell),
            Paragraph("<b>IA-3 (/50)</b>", header_cell),
            Paragraph("<b>Best Two IA Avg</b>", header_cell)
        ]
    ]

    for item in ia_subjects:
        ia_table_data.append([
            Paragraph(f"<b>{item['subject']}</b>", body_style),
            Paragraph(str(item['ia1']), body_style),
            Paragraph(str(item['ia2']), body_style),
            Paragraph(str(item['ia3']), body_style),
            Paragraph(f"<b><font color='{ACCENT.hexval()}'>{item['best_two']}</font></b>", body_style)
        ])

    ia_table = Table(ia_table_data, colWidths=[180, 90, 90, 90, 90])
    ia_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_BG]),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(ia_table)
    story.append(Spacer(1, 8))

    # 3A. Subject-wise SEE forecast (same rule-based logic used in class reports)
    see_summary = summarize_student_see(student, details.get('see_predictions'))
    story.append(Paragraph("Semester-End Examination (SEE) Prediction", section_heading))
    story.append(Paragraph(
        "Rule-based early-warning estimate from current IA performance and previous-semester percentage where available. "
        "Configured baseline: CIE >= 20/50, SEE >= 20/50, and CIE + SEE >= 40/100. "
        "Forecasts are estimates, not guaranteed results; confirm the applicable VTU scheme.", body_style))
    see_header = ["Subject", "CIE (/50)", "Required SEE", "Predicted SEE", "Predicted Total", "Forecast"]
    see_data = [[Paragraph(f"<b>{h}</b>", header_cell) for h in see_header]]
    for item in see_summary['subjects']:
        pred_color = DANGER if item['risk'] == 'High' else (WARNING if item['risk'] == 'Medium' else SUCCESS)
        see_data.append([
            Paragraph(str(item['subject']), body_style),
            Paragraph(str(item['cie']) if item['cie'] is not None else '—', body_style),
            Paragraph(str(item['required_see']) if item['required_see'] is not None else '—', body_style),
            Paragraph(str(item['predicted_see']) if item['predicted_see'] is not None else '—', body_style),
            Paragraph(str(item['predicted_total']) if item['predicted_total'] is not None else '—', body_style),
            Paragraph(f"<font color='{pred_color.hexval()}'><b>{item['prediction']}</b></font>", body_style)
        ])
    see_table = Table(see_data, colWidths=[145, 58, 70, 70, 75, 122], repeatRows=1)
    see_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_BG]),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(see_table)
    story.append(Spacer(1, 8))

    # 4. Academic History & Previous Semester SGPAs
    sem_history = details.get('semester_history') or []
    if sem_history:
        story.append(Paragraph("Previous Semester Performance & SGPAs", section_heading))
        sem_header = [Paragraph("<b>Semester</b>", header_cell)]
        sem_row = [Paragraph("<b>SGPA</b>", body_style)]

        col_w = min(540 / max(len(sem_history) + 1, 2), 70)
        widths = [70] + [col_w] * len(sem_history)

        for sh in sem_history:
            s_num = sh.get('semester', '-')
            s_val = sh.get('sgpa', '-')
            sem_header.append(Paragraph(f"<b>Sem {s_num}</b>", header_cell))
            sem_row.append(Paragraph(f"<b>{s_val}</b>", body_style))

        sem_table = Table([sem_header, sem_row], colWidths=widths)
        sem_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(sem_table)
        story.append(Spacer(1, 8))

    # 5. Overall Academic & Evaluation Summary
    story.append(Paragraph("Overall Performance & Evaluation Summary", section_heading))
    res = student.get('predicted_result', 'Pass')
    risk = student.get('risk_level', 'Low')
    cgpa = student.get('cgpa', 7.5)
    att = student.get('attendance', 78)

    res_color = SUCCESS if res == 'Pass' else DANGER
    risk_color = DANGER if risk == 'High' else (WARNING if risk == 'Medium' else SUCCESS)

    eval_data = [
        [
            Paragraph("<b>Overall CGPA</b>", body_style),
            Paragraph(f"<b>{cgpa} / 10.0</b>", body_style),
            Paragraph("<b>Attendance</b>", body_style),
            Paragraph(f"<b>{att}%</b>", body_style)
        ],
        [
            Paragraph("<b>ML Predicted Result</b>", body_style),
            Paragraph(f"<font color='{res_color.hexval()}'><b>{res}</b></font>", body_style),
            Paragraph("<b>Risk Status</b>", body_style),
            Paragraph(f"<font color='{risk_color.hexval()}'><b>{risk} Risk</b></font>", body_style)
        ],
        [
            Paragraph("<b>Active Backlogs</b>", body_style),
            Paragraph(f"<b>{student.get('active_backlogs', 0)}</b>", body_style),
            Paragraph("<b>Cleared Backlogs</b>", body_style),
            Paragraph(f"<b>{student.get('cleared_backlogs', 0)}</b>", body_style)
        ]
    ]
    eval_table = Table(eval_data, colWidths=[135, 135, 135, 135])
    eval_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(eval_table)
    story.append(Spacer(1, 8))

    # 6. Official Teacher Remarks
    story.append(Paragraph("Official Teacher Remarks & Academic Counseling", section_heading))
    remarks_text = student.get('teacher_remarks') or "Student progress monitored. Good overall academic engagement."
    story.append(Paragraph(f"<i>\"{remarks_text}\"</i>", body_style))
    story.append(Spacer(1, 14))

    # 7. Signature Block
    sig_data = [
        [Paragraph("<b>Class Coordinator Signature</b>", body_style), Paragraph("<b>Head of Department (HOD)</b>", body_style)],
        [Spacer(1, 20), Spacer(1, 20)],
        [Paragraph("_____________________________", body_style), Paragraph("_____________________________", body_style)]
    ]
    sig_table = Table(sig_data, colWidths=[270, 270])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER')
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_class_pdf_report(students, dept, sem, sec):
    """
    Generates Complete Class Analytics PDF Report.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    PRIMARY = colors.HexColor('#0F172A')
    SUCCESS = colors.HexColor('#10B981')
    DANGER = colors.HexColor('#EF4444')
    LIGHT_BG = colors.HexColor('#F8FAFC')

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=PRIMARY
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#64748B')
    )
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=PRIMARY,
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11)
    header_cell = ParagraphStyle('HeaderCell', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=colors.white)

    story = []

    # Header
    story.append(Paragraph("<b>ADAPTIVE STUDENT PERFORMANCE ANALYZER</b>", title_style))
    story.append(Paragraph(f"<b>Class Performance Report</b> — Dept: {dept} | Sem: {sem} | Section: {sec} | Date: {datetime.datetime.now().strftime('%d %b %Y')}", subtitle_style))
    story.append(Spacer(1, 10))

    # Executive Summary Cards Table
    total = len(students)
    pass_cnt = sum(1 for s in students if s.get('predicted_result') == 'Pass')
    fail_cnt = sum(1 for s in students if s.get('predicted_result') == 'Fail')
    pass_pct = round((pass_cnt / total)*100, 1) if total > 0 else 0
    avg_cgpa = round(sum(s.get('cgpa', 7.5) for s in students) / total, 2) if total > 0 else 0
    avg_att = round(sum(s.get('attendance', 75) for s in students) / total, 1) if total > 0 else 0
    high_risk = sum(1 for s in students if s.get('risk_level') == 'High')

    summary_data = [
        [Paragraph("<b>Total Students</b>", body_style), Paragraph(f"<b>{total}</b>", body_style), Paragraph("<b>Pass Rate</b>", body_style), Paragraph(f"<b>{pass_pct}%</b>", body_style)],
        [Paragraph("<b>Avg CGPA</b>", body_style), Paragraph(f"<b>{avg_cgpa}</b>", body_style), Paragraph("<b>Avg Attendance</b>", body_style), Paragraph(f"<b>{avg_att}%</b>", body_style)],
        [Paragraph("<b>High Risk Count</b>", body_style), Paragraph(f"<b><font color='red'>{high_risk}</font></b>", body_style), Paragraph("<b>Fail Count</b>", body_style), Paragraph(f"<b>{fail_cnt}</b>", body_style)]
    ]
    summary_table = Table(summary_data, colWidths=[135, 135, 135, 135])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0,0), (-1,-1), 6)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # Student Roster Table
    story.append(Paragraph("Complete Class Student Roster", section_heading))
    
    roster_data = [
        [
            Paragraph("<b>USN</b>", header_cell),
            Paragraph("<b>Student Name</b>", header_cell),
            Paragraph("<b>Att %</b>", header_cell),
            Paragraph("<b>CGPA</b>", header_cell),
            Paragraph("<b>Backlogs</b>", header_cell),
            Paragraph("<b>Result</b>", header_cell),
            Paragraph("<b>Risk Level</b>", header_cell)
        ]
    ]

    for s in students:
        res = s.get('predicted_result', 'Pass')
        risk = s.get('risk_level', 'Low')
        res_c = "green" if res == 'Pass' else "red"
        risk_c = "red" if risk == 'High' else ("orange" if risk == 'Medium' else "green")

        roster_data.append([
            Paragraph(s.get('usn', 'N/A'), body_style),
            Paragraph(s.get('name', 'N/A'), body_style),
            Paragraph(f"{s.get('attendance', 75)}%", body_style),
            Paragraph(str(s.get('cgpa', 7.5)), body_style),
            Paragraph(str(s.get('active_backlogs', 0)), body_style),
            Paragraph(f"<font color='{res_c}'><b>{res}</b></font>", body_style),
            Paragraph(f"<font color='{risk_c}'><b>{risk}</b></font>", body_style)
        ])

    roster_table = Table(roster_data, colWidths=[90, 160, 50, 50, 50, 60, 80])
    roster_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_BG]),
        ('PADDING', (0,0), (-1,-1), 4)
    ]))
    story.append(roster_table)
    story.append(Spacer(1, 12))

    # Class PDF intentionally contains class-wide information only.
    # Individual subject-wise SEE predictions are available through each student's
    # separate Student Report PDF endpoint (/report/pdf/<student_id>).
    story.append(Spacer(1, 20))

    # Signature Block
    sig_data = [
        [Paragraph("<b>Class Teacher Signature</b>", body_style), Paragraph("<b>Head of Department (HOD)</b>", body_style)],
        [Spacer(1, 25), Spacer(1, 25)],
        [Paragraph("_____________________________", body_style), Paragraph("_____________________________", body_style)]
    ]
    sig_table = Table(sig_data, colWidths=[270, 270])
    sig_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
