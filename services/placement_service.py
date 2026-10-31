"""
Placement Readiness Service
Evaluates campus placement readiness using the exact weighted formula:
  1. Programming Skills    = 30% (coding_score, programming_experience, languages, platforms, hackathons)
  2. CGPA                  = 20% (normalized to 0-100: CGPA / 10.0 * 100)
  3. Projects              = 20% (academic_projects + personal_projects + GitHub profile)
  4. Communication Skills  = 10% (communication_score / certifications)
  5. Internship Experience = 10% (internships_count)
  6. Attendance            = 10% (actual attendance percentage)
  Total = 100%

Categorizes into Highly Ready (80-100), Placement Ready (65-79.99), Needs Improvement (50-64.99), and Not Ready (<50).
Preserves company tier recommendations, skill gap analysis, and tailored action plans.
"""

# Placement Readiness Category Threshold Constants
CATEGORY_HIGHLY_READY      = "Highly Ready"
CATEGORY_PLACEMENT_READY   = "Placement Ready"
CATEGORY_NEEDS_IMPROVEMENT = "Needs Improvement"
CATEGORY_NOT_READY         = "Not Ready"

THRESH_HIGHLY_READY        = 80.0
THRESH_PLACEMENT_READY     = 65.0
THRESH_NEEDS_IMPROVEMENT   = 50.0

COMPANY_TIERS = {
    'Tier 1 (Product & Tech Giants)': {
        'min_score': 80.0,
        'companies': ['Google', 'Microsoft', 'Amazon', 'IBM', 'Adobe', 'Cisco', 'Oracle']
    },
    'Tier 2 (Global IT Services & Product)': {
        'min_score': 65.0,
        'companies': ['Cognizant', 'Accenture', 'Capgemini', 'Wipro Digital', 'LTI Mindtree', 'Deloitte']
    },
    'Tier 3 (Mass Recruiters & Mass IT)': {
        'min_score': 50.0,
        'companies': ['TCS', 'Infosys', 'Wipro', 'HCL Tech', 'Tech Mahindra']
    }
}


def get_placement_category(score):
    """Returns the standardized placement readiness category string."""
    if score >= THRESH_HIGHLY_READY:
        return CATEGORY_HIGHLY_READY
    elif score >= THRESH_PLACEMENT_READY:
        return CATEGORY_PLACEMENT_READY
    elif score >= THRESH_NEEDS_IMPROVEMENT:
        return CATEGORY_NEEDS_IMPROVEMENT
    else:
        return CATEGORY_NOT_READY


def calculate_placement_readiness(student):
    """
    Calculates normalized placement factor scores (0-100), overall readiness score,
    category, strengths, weak areas, recommended company tiers, and action items.
    """
    # 1. Programming Skills Score (30%) -> 0-100 scale
    coding_raw = float(student.get('coding_score') or 0.0)
    prog_exp = float(student.get('programming_experience') or 1.0)
    java_m = float(student.get('java_marks') or 60.0)
    prog_langs = str(student.get('prog_languages') or 'Python, Java')
    hackathons = str(student.get('hackathons') or 'No').lower() in ['yes', '1', 'true']
    contests = str(student.get('coding_contests') or 'No').lower() in ['yes', '1', 'true']

    # Compute programming composite score
    lang_count = len([l.strip() for l in prog_langs.split(',') if l.strip()])
    lang_bonus = min(20.0, lang_count * 5.0)
    exp_bonus = min(25.0, prog_exp * 10.0)
    contest_bonus = (10.0 if hackathons else 0.0) + (10.0 if contests else 0.0)
    core_coding = coding_raw if coding_raw > 0 else (java_m * 0.5)

    prog_score = min(100.0, max(0.0, (core_coding * 0.45) + exp_bonus + lang_bonus + contest_bonus))

    # 2. CGPA Score (20%) -> 0-100 scale
    cgpa_val = float(student.get('cgpa') or 0.0)
    if cgpa_val <= 0.0:
        cgpa_val = float(student.get('prev_sem_percentage') or 70.0) / 10.0
    cgpa_score = min(100.0, max(0.0, cgpa_val * 10.0))

    # 3. Projects Score (20%) -> 0-100 scale (uses academic_projects + personal_projects + github)
    acad_proj = int(student.get('academic_projects') or 0)
    pers_proj = int(student.get('personal_projects') or 0)
    total_projects = acad_proj + pers_proj
    has_github = bool(str(student.get('github_profile') or '').strip())

    proj_pts = total_projects * 25.0
    if has_github:
        proj_pts += 15.0
    projects_score = min(100.0, max(20.0 if total_projects > 0 else 0.0, proj_pts))

    # 4. Communication Skills Score (10%) -> 0-100 scale
    comm_raw = float(student.get('communication_score') or 0.0)
    cert_count = int(student.get('certifications_count') or 0)
    if comm_raw > 0:
        comm_score = min(100.0, max(0.0, comm_raw))
    else:
        # Evaluate from certifications and background
        comm_score = min(100.0, max(50.0, 60.0 + (cert_count * 10.0)))

    # 5. Internship Experience Score (10%) -> 0-100 scale
    intern_cnt = int(student.get('internships_count') or 0)
    if intern_cnt >= 2:
        internship_score = 100.0
    elif intern_cnt == 1:
        internship_score = 80.0
    else:
        internship_score = 30.0

    # 6. Attendance Score (10%) -> 0-100 scale
    attendance_score = min(100.0, max(0.0, float(student.get('attendance') or 75.0)))

    # Weighted Overall Placement Readiness Score (0-100)
    readiness_score = (
        (prog_score * 0.30) +
        (cgpa_score * 0.20) +
        (projects_score * 0.20) +
        (comm_score * 0.10) +
        (internship_score * 0.10) +
        (attendance_score * 0.10)
    )

    readiness_score = round(min(100.0, max(0.0, readiness_score)), 1)
    category = get_placement_category(readiness_score)

    # Strengths and Weak Areas Identification
    factor_scores = {
        'Programming & Problem Solving': prog_score,
        'Academic CGPA': cgpa_score,
        'Technical Projects': projects_score,
        'Communication Skills': comm_score,
        'Industry Internship Experience': internship_score,
        'Attendance & Regularity': attendance_score
    }

    strengths = [factor for factor, val in factor_scores.items() if val >= 75.0]
    weak_areas = [factor for factor, val in factor_scores.items() if val < 65.0]

    # Preserved Company Tier Recommendations
    recommended_companies = []
    eligible_tiers = []
    for tier_name, tier_info in COMPANY_TIERS.items():
        if readiness_score >= tier_info['min_score']:
            recommended_companies.extend(tier_info['companies'])
            eligible_tiers.append(tier_name)

    if not eligible_tiers:
        recommended_companies = ['TCS Ninja', 'Infosys Springboard', 'Wipro TalentNext']
        eligible_tiers = ['Preparatory & Foundation Tier']

    # Actionable Tailored Recommendations
    recommendations = []
    if prog_score < 70.0:
        recommendations.append("Practice Data Structures & Algorithms (DSA) daily on LeetCode / HackerRank.")
    if projects_score < 70.0:
        recommendations.append("Build and deploy 1 full-stack or AI/ML project with a clear GitHub repository & documentation.")
    if intern_cnt == 0:
        recommendations.append("Apply for at least 1 summer industry internship or virtual technical externship program.")
    if comm_score < 70.0:
        recommendations.append("Participate in technical presentations and attend mock HR / technical interviews.")
    if cgpa_score < 65.0:
        recommendations.append("Improve IA marks and target minimum 6.5+ CGPA to meet top company eligibility criteria.")
    if attendance_score < 75.0:
        recommendations.append("Ensure attendance stays above 75% to avoid campus placement drive disqualification.")

    if not recommendations:
        recommendations.append("Excellent placement profile! Focus on advanced system design and competitive coding rounds.")

    return {
        'readiness_score': readiness_score,
        'placement_readiness_index': readiness_score,
        'category': category,
        'tier': eligible_tiers[0] if eligible_tiers else 'Preparatory Tier',
        'breakdown': {
            'programming': round(prog_score, 1),
            'cgpa': round(cgpa_score, 1),
            'projects': round(projects_score, 1),
            'communication': round(comm_score, 1),
            'internship': round(internship_score, 1),
            'attendance': round(attendance_score, 1)
        },
        'strengths': strengths,
        'weak_areas': weak_areas,
        'recommendations': recommendations,
        'suggestions': recommendations,
        'recommended_companies': recommended_companies,
        'eligible_tiers': eligible_tiers
    }
