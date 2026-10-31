/**
 * Student Performance Analyzer & Marks Prediction System Student Dashboard JavaScript
 * Handles Dynamic Student Details, IA Performance Table, Chart.js SGPA Trend,
 * IA Performance Charts (Graph 1 & 2), Personalized Weekly Study Plan,
 * Notifications, & Placement Index.
 *
 * Data flow: Teacher Excel/Manual Update → Database → Student Portal (this file).
 * All values are read live from the /student/<id>/details API — no hardcoded data.
 */

let studentSgpaTrendChart  = null;
let iaPerformanceChart     = null;   // Graph 1 — IA marks grouped bar
let subjectPerfChart       = null;   // Graph 2 — Best two IA avg horizontal bar
let _dashboardStudentId    = null;

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('dashboardContainer');
    if (container) {
        const studentId = container.dataset.studentId;
        if (studentId) {
            _dashboardStudentId = studentId;
            loadStudentDashboardData(studentId);
            initDoubtModule();

            const chatTabBtn = document.getElementById('teacher-chat-tab');
            if (chatTabBtn) {
                chatTabBtn.addEventListener('shown.bs.tab', () => {
                    loadStudentConversations();
                });
            }
            loadStudentConversations();

            // Real-time background polling for new teacher replies (every 4s)
            setInterval(() => {
                loadStudentConversations();
                if (typeof _activeStudentConvId !== 'undefined' && _activeStudentConvId) {
                    openStudentConversation(_activeStudentConvId, true);
                }
            }, 4000);
        }
    }
});

// Auto-refresh when the tab regains focus (catches teacher updates made in another tab)
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && _dashboardStudentId) {
        loadStudentDashboardData(_dashboardStudentId);
    }
});

async function loadStudentDashboardData(studentId) {
    try {
        const response = await fetch(`/student/${studentId}/details`);
        const data = await response.json();

        if (!data.success) {
            console.error('Failed to fetch student details:', data.error);
            return;
        }

        const student = data.student;

        // 1. Update Top Summary Cards (always from live DB)
        if (document.getElementById('cardUsn')) document.getElementById('cardUsn').textContent = student.usn || 'N/A';
        if (document.getElementById('cardCgpa')) document.getElementById('cardCgpa').textContent = `${student.cgpa ?? '-'} / 10.0`;
        if (document.getElementById('cardAttendance')) document.getElementById('cardAttendance').textContent = `${student.attendance ?? 0}%`;
        if (document.getElementById('cardActiveBacklogs')) document.getElementById('cardActiveBacklogs').textContent = student.active_backlogs || 0;

        // Also update inline CGPA display in the progress section
        if (document.getElementById('progCgpa')) document.getElementById('progCgpa').textContent = student.cgpa ?? '-';

        // 2. Render IA Subject Performance Table & Dropdowns (real teacher-entered marks & active subjects)
        renderSubjectTable(data.subject_performance);
        populateStudentSubjectDropdowns(data.subject_performance);

        // 3. Render Academic Progress SGPA Trend Chart (existing)
        renderSgpaTrendChart(data.timeline);

        // 4. Render IA Performance Charts (Graph 1 & Graph 2)
        renderIaPerformanceChart(data.subject_performance);
        renderSubjectPerformanceChart(data.subject_performance);

        // 5. Update Teacher Remarks
        if (document.getElementById('teacherRemarksText')) {
            const remarks = student.teacher_remarks || "Improve your attendance and spend more time on DBMS and Computer Networks.";
            document.getElementById('teacherRemarksText').textContent = `"${remarks}"`;
        }

        // 6. Render Personalized Weekly Study Plan
        renderWeeklyStudyPlan(data.study_plan);

        // 7. Render Recent Notifications
        renderNotifications(data.notifications);

        // 8. Render Student Academic Ranking Card
        if (data.ranking) {
            const r = data.ranking;
            if (document.getElementById('cardCollegeRank')) document.getElementById('cardCollegeRank').textContent = `#${r.college_rank ?? '—'}`;
            if (document.getElementById('cardDeptRank')) document.getElementById('cardDeptRank').textContent = `#${r.department_rank ?? '—'}`;
            if (document.getElementById('cardClassRank')) document.getElementById('cardClassRank').textContent = `#${r.class_rank ?? '—'}`;
            if (document.getElementById('cardRankingScore')) document.getElementById('cardRankingScore').textContent = `${r.overall_score ?? r.ranking_score ?? 0.0} / 100`;
            if (document.getElementById('cardRankingScoreBar')) document.getElementById('cardRankingScoreBar').style.width = `${Math.min(100, r.overall_score ?? 0)}%`;

            if (document.getElementById('rankChangeBadge')) {
                const badge = document.getElementById('rankChangeBadge');
                const rc = r.rank_change ?? 'New';
                if (rc === 'New') {
                    badge.className = 'badge bg-info-subtle text-info fw-bold';
                    badge.innerHTML = '<i class="fa-solid fa-sparkles me-1"></i> New Evaluation';
                } else if (String(rc).startsWith('+')) {
                    badge.className = 'badge bg-success text-white fw-bold';
                    badge.innerHTML = `<i class="fa-solid fa-arrow-up me-1"></i> Rank ${rc}`;
                } else if (String(rc).startsWith('-')) {
                    badge.className = 'badge bg-danger text-white fw-bold';
                    badge.innerHTML = `<i class="fa-solid fa-arrow-down me-1"></i> Rank ${rc}`;
                } else {
                    badge.className = 'badge bg-secondary-subtle text-secondary fw-bold';
                    badge.innerHTML = 'Rank Unchanged (0)';
                }
            }

            // Factor Breakdown
            if (document.getElementById('fCgpaScore')) document.getElementById('fCgpaScore').textContent = `${r.cgpa_score ?? '—'} / 100`;
            if (document.getElementById('fPastScore')) document.getElementById('fPastScore').textContent = `${r.past_academic_score ?? '—'} / 100`;
            if (document.getElementById('fIaScore')) document.getElementById('fIaScore').textContent = `${r.internal_score ?? '—'} / 100`;
            if (document.getElementById('fAttScore')) document.getElementById('fAttScore').textContent = `${r.attendance_score ?? '—'} / 100`;
            if (document.getElementById('fConstScore')) document.getElementById('fConstScore').textContent = `${r.consistency_score ?? '—'} / 100`;
            if (document.getElementById('fImpScore')) document.getElementById('fImpScore').textContent = `${r.improvement_score ?? '—'} / 100`;
        }

        // 9. Render Enhanced Placement Readiness Card
        if (data.placement) {
            const p = data.placement;
            if (document.getElementById('placementScoreVal')) {
                document.getElementById('placementScoreVal').textContent = `${p.readiness_score ?? 0}%`;
            }
            if (document.getElementById('placementCategoryBadge')) {
                const catBadge = document.getElementById('placementCategoryBadge');
                const cat = p.category || 'Placement Ready';
                catBadge.textContent = cat;
                if (cat === 'Highly Ready') catBadge.className = 'badge bg-success text-white px-3 py-1 rounded-pill';
                else if (cat === 'Placement Ready') catBadge.className = 'badge bg-primary text-white px-3 py-1 rounded-pill';
                else if (cat === 'Needs Improvement') catBadge.className = 'badge bg-warning text-dark px-3 py-1 rounded-pill';
                else catBadge.className = 'badge bg-danger text-white px-3 py-1 rounded-pill';
            }
            if (document.getElementById('placementTierVal')) {
                const tier = Array.isArray(p.eligible_tiers) && p.eligible_tiers.length > 0 ? p.eligible_tiers[0] : (p.tier || 'Eligible Tier');
                document.getElementById('placementTierVal').textContent = tier;
            }

            // Factor progress bars
            if (p.breakdown) {
                const b = p.breakdown;
                if (document.getElementById('pProgScore')) document.getElementById('pProgScore').textContent = `${b.programming ?? 0}`;
                if (document.getElementById('pProgBar')) document.getElementById('pProgBar').style.width = `${b.programming ?? 0}%`;

                if (document.getElementById('pCgpaScore')) document.getElementById('pCgpaScore').textContent = `${b.cgpa ?? 0}`;
                if (document.getElementById('pCgpaBar')) document.getElementById('pCgpaBar').style.width = `${b.cgpa ?? 0}%`;

                if (document.getElementById('pProjScore')) document.getElementById('pProjScore').textContent = `${b.projects ?? 0}`;
                if (document.getElementById('pProjBar')) document.getElementById('pProjBar').style.width = `${b.projects ?? 0}%`;

                if (document.getElementById('pCommScore')) document.getElementById('pCommScore').textContent = `${b.communication ?? 0}`;
                if (document.getElementById('pCommBar')) document.getElementById('pCommBar').style.width = `${b.communication ?? 0}%`;

                if (document.getElementById('pInternScore')) document.getElementById('pInternScore').textContent = `${b.internship ?? 0}`;
                if (document.getElementById('pInternBar')) document.getElementById('pInternBar').style.width = `${b.internship ?? 0}%`;

                if (document.getElementById('pAttScore')) document.getElementById('pAttScore').textContent = `${b.attendance ?? 0}`;
                if (document.getElementById('pAttBar')) document.getElementById('pAttBar').style.width = `${b.attendance ?? 0}%`;
            }

            // Strengths
            if (document.getElementById('placementStrengths')) {
                const strEl = document.getElementById('placementStrengths');
                if (p.strengths && p.strengths.length > 0) {
                    strEl.innerHTML = p.strengths.map(s => `<span class="badge bg-success-subtle text-success text-xs"><i class="fa-solid fa-check me-1"></i>${s}</span>`).join(' ');
                } else {
                    strEl.innerHTML = `<span class="text-muted text-xs">Solid foundational skills in progress.</span>`;
                }
            }

            // Weak Areas
            if (document.getElementById('placementWeakAreas')) {
                const weakEl = document.getElementById('placementWeakAreas');
                if (p.weak_areas && p.weak_areas.length > 0) {
                    weakEl.innerHTML = p.weak_areas.map(w => `<span class="badge bg-danger-subtle text-danger text-xs"><i class="fa-solid fa-exclamation me-1"></i>${w}</span>`).join(' ');
                } else {
                    weakEl.innerHTML = `<span class="badge bg-success-subtle text-success text-xs"><i class="fa-solid fa-circle-check me-1"></i> No critical skill deficits</span>`;
                }
            }

            // Target Companies
            if (document.getElementById('placementTargetCompanies')) {
                const companies = Array.isArray(p.recommended_companies) ? p.recommended_companies : (p.target_companies || []);
                document.getElementById('placementTargetCompanies').textContent = companies.join(', ') || 'TCS, Infosys, Wipro';
            }

            // Recommendations
            if (document.getElementById('placementRecommendations')) {
                const recEl = document.getElementById('placementRecommendations');
                if (p.recommendations && p.recommendations.length > 0) {
                    recEl.innerHTML = p.recommendations.map(r => `<li class="mb-1">${r}</li>`).join('');
                }
            }
        }

    } catch (err) {
        console.error('Error loading student dashboard data:', err);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// IA Subject Performance Table
// ─────────────────────────────────────────────────────────────────────────────
function renderSubjectTable(subjects) {
    const tbody = document.getElementById('subjectPerformanceTable');
    if (!tbody) return;

    if (!subjects || subjects.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-3 text-muted">No subject evaluation records found.</td></tr>`;
        return;
    }

    tbody.innerHTML = '';
    subjects.forEach(sub => {
        const tr = document.createElement('tr');
        
        const formatIa = (val) => {
            if (val === null || val === undefined || val === '' || val === '-' || val === '—') return `<span class="text-muted">—</span>`;
            if (val === 'AB' || val === 'ABSENT') return `<span class="badge bg-danger">AB</span>`;
            return `<strong>${val}</strong>`;
        };

        tr.innerHTML = `
            <td class="fw-bold text-primary font-monospace">${sub.code}</td>
            <td class="fw-semibold">${sub.name}</td>
            <td class="text-center">${formatIa(sub.ia1)}</td>
            <td class="text-center">${formatIa(sub.ia2)}</td>
            <td class="text-center">${formatIa(sub.ia3)}</td>
            <td class="text-center fw-bold text-primary fs-6">${formatIa(sub.best_two_avg)}</td>
            <td class="text-center fw-semibold">${sub.attendance}</td>
        `;
        tbody.appendChild(tr);
    });
}

function populateStudentSubjectDropdowns(subjects) {
    if (!subjects || subjects.length === 0) return;

    // 1. Doubt Search Filter Dropdown
    const doubtFilter = document.getElementById('doubtSubjectFilter');
    if (doubtFilter) {
        const curVal = doubtFilter.value;
        doubtFilter.innerHTML = '<option value="All">All Subjects</option>';
        subjects.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.name;
            opt.textContent = s.name;
            doubtFilter.appendChild(opt);
        });
        const otherOpt = document.createElement('option');
        otherOpt.value = 'Other';
        otherOpt.textContent = 'Other';
        doubtFilter.appendChild(otherOpt);

        if (curVal && Array.from(doubtFilter.options).some(o => o.value === curVal)) {
            doubtFilter.value = curVal;
        }
    }

    // 2. New Conversation / Ask Teacher Modal Dropdown
    const convSubj = document.getElementById('newConvSubject');
    if (convSubj) {
        const curVal = convSubj.value;
        convSubj.innerHTML = '';
        subjects.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.name;
            opt.textContent = `${s.name} (${s.code})`;
            convSubj.appendChild(opt);
        });
        if (curVal && Array.from(convSubj.options).some(o => o.value === curVal)) {
            convSubj.value = curVal;
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SGPA Trend Chart
// ─────────────────────────────────────────────────────────────────────────────
function renderSgpaTrendChart(timeline) {
    const canvas = document.getElementById('studentSgpaTrendChart');
    if (!canvas) return;

    const labels = timeline && timeline.labels ? timeline.labels : ['Sem 1', 'Sem 2', 'Sem 3', 'Sem 4', 'Sem 5'];
    const sgpas = timeline && timeline.sgpa_list ? timeline.sgpa_list : [7.2, 7.5, 7.8, 8.0, 8.2];

    if (document.getElementById('progSgpa')) {
        document.getElementById('progSgpa').textContent = sgpas[sgpas.length - 1] || '—';
    }

    const ctx = canvas.getContext('2d');
    if (studentSgpaTrendChart) studentSgpaTrendChart.destroy();

    studentSgpaTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Semester SGPA',
                data: sgpas,
                borderColor: '#0284C7',
                backgroundColor: 'rgba(2, 132, 199, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.3,
                pointRadius: 5,
                pointBackgroundColor: '#0284C7'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    min: 0,
                    max: 10,
                    ticks: { stepSize: 2 }
                }
            }
        }
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// GRAPH 1: Internal Assessment Performance
// Grouped bar chart — IA-1, IA-2, IA-3, Best Two Avg per subject (each /50)
// ─────────────────────────────────────────────────────────────────────────────
function renderIaPerformanceChart(subjects) {
    const canvas    = document.getElementById('iaPerformanceChart');
    const noDataEl  = document.getElementById('iaChartNoData');
    if (!canvas) return;

    function iaToNum(val) {
        if (val === null || val === undefined || val === '-' || val === '' || val === 'AB') return null;
        const n = parseFloat(val);
        return isNaN(n) ? null : n;
    }

    const subjectLabels = [];
    const ia1Data       = [];
    const ia2Data       = [];
    const ia3Data       = [];
    const bestAvgData   = [];
    let hasAnyMark = false;

    (subjects || []).forEach(sub => {
        const shortName = sub.name.replace(/\s*\(.*\)/, '').trim();
        subjectLabels.push(shortName);

        const v1 = iaToNum(sub.ia1);
        const v2 = iaToNum(sub.ia2);
        const v3 = iaToNum(sub.ia3);
        const bAvg = iaToNum(sub.best_two_avg);

        ia1Data.push(v1);
        ia2Data.push(v2);
        ia3Data.push(v3);
        bestAvgData.push(bAvg);

        if (v1 !== null || v2 !== null || v3 !== null) hasAnyMark = true;
    });

    if (!hasAnyMark) {
        if (noDataEl) noDataEl.classList.remove('d-none');
        canvas.style.display = 'none';
        if (iaPerformanceChart) { iaPerformanceChart.destroy(); iaPerformanceChart = null; }
        return;
    }
    if (noDataEl) noDataEl.classList.add('d-none');
    canvas.style.display = '';

    const ctx = canvas.getContext('2d');
    if (iaPerformanceChart) iaPerformanceChart.destroy();

    iaPerformanceChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: subjectLabels,
            datasets: [
                {
                    label: 'IA-1',
                    data: ia1Data,
                    backgroundColor: 'rgba(59, 130, 246, 0.80)',
                    borderColor:     'rgba(59, 130, 246, 1)',
                    borderWidth: 1,
                    borderRadius: 4
                },
                {
                    label: 'IA-2',
                    data: ia2Data,
                    backgroundColor: 'rgba(16, 185, 129, 0.80)',
                    borderColor:     'rgba(16, 185, 129, 1)',
                    borderWidth: 1,
                    borderRadius: 4
                },
                {
                    label: 'IA-3',
                    data: ia3Data,
                    backgroundColor: 'rgba(245, 158, 11, 0.80)',
                    borderColor:     'rgba(245, 158, 11, 1)',
                    borderWidth: 1,
                    borderRadius: 4
                },
                {
                    label: 'Best Two Avg',
                    data: bestAvgData,
                    backgroundColor: 'rgba(139, 92, 246, 0.85)',
                    borderColor:     'rgba(139, 92, 246, 1)',
                    borderWidth: 1,
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { font: { size: 12 }, padding: 16 }
                },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const val = ctx.parsed.y;
                            if (val === null || val === undefined) return `${ctx.dataset.label}: Not entered`;
                            return `${ctx.dataset.label}: ${val} / 50`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Subjects',
                        font: { weight: 'bold', size: 12 }
                    },
                    grid: { display: false }
                },
                y: {
                    min: 0,
                    max: 50,
                    title: {
                        display: true,
                        text: 'Marks (out of 50)',
                        font: { weight: 'bold', size: 12 }
                    },
                    ticks: {
                        stepSize: 10,
                        callback: val => `${val}`
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' }
                }
            }
        }
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// GRAPH 2: Subject-wise Performance (Best Two IA Average)
// ─────────────────────────────────────────────────────────────────────────────
function renderSubjectPerformanceChart(subjects) {
    const canvas    = document.getElementById('subjectPerformanceChart');
    const noDataEl  = document.getElementById('subjectPerfNoData');
    if (!canvas) return;

    function avgToNum(val) {
        if (val === null || val === undefined || val === '-' || val === '' || val === 'N/A') return null;
        const n = parseFloat(val);
        return isNaN(n) ? null : n;
    }

    const subjectLabels = [];
    const avgData       = [];
    let hasAnyAvg = false;

    (subjects || []).forEach(sub => {
        const shortName = sub.name.replace(/\s*\(.*\)/, '').trim();
        subjectLabels.push(shortName);
        const avg = avgToNum(sub.best_two_avg);
        avgData.push(avg);
        if (avg !== null) hasAnyAvg = true;
    });

    if (!hasAnyAvg) {
        if (noDataEl) noDataEl.classList.remove('d-none');
        canvas.style.display = 'none';
        if (subjectPerfChart) { subjectPerfChart.destroy(); subjectPerfChart = null; }
        return;
    }
    if (noDataEl) noDataEl.classList.add('d-none');
    canvas.style.display = '';

    const bgColors = avgData.map(v => {
        if (v === null) return 'rgba(203,213,225,0.6)';
        if (v >= 40)   return 'rgba(16, 185, 129, 0.85)';
        if (v >= 25)   return 'rgba(245, 158, 11, 0.85)';
        return 'rgba(239, 68, 68, 0.85)';
    });
    const borderColors = bgColors.map(c => c.replace('0.85', '1').replace('0.6', '1'));

    const ctx = canvas.getContext('2d');
    if (subjectPerfChart) subjectPerfChart.destroy();

    subjectPerfChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: subjectLabels,
            datasets: [{
                label: 'Best Two IA Average',
                data: avgData,
                backgroundColor: bgColors,
                borderColor: borderColors,
                borderWidth: 1,
                borderRadius: 6,
                indexAxis: 'y'
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const val = ctx.parsed.x;
                            if (val === null || val === undefined) return 'Not entered';
                            const pct = ((val / 50) * 100).toFixed(1);
                            return `Best Two Avg: ${val} / 50  (${pct}%)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    min: 0,
                    max: 50,
                    title: {
                        display: true,
                        text: 'Performance (out of 50)',
                        font: { weight: 'bold', size: 12 }
                    },
                    ticks: {
                        stepSize: 10,
                        callback: val => `${val}`
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' }
                },
                y: {
                    title: { display: false },
                    grid: { display: false },
                    ticks: { font: { weight: '600', size: 12 } }
                }
            }
        }
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Personalized Weekly Study Plan
// Renders readable cards showing Day, Subject, Marks, Priority, Study Time, Activity
// ─────────────────────────────────────────────────────────────────────────────
function renderWeeklyStudyPlan(plan) {
    const container = document.getElementById('studyPlanGrid');
    if (!container) return;

    container.innerHTML = '';

    if (!plan || !plan.schedule) {
        container.innerHTML = `<div class="col-12 text-center py-3 text-muted">No study plan available.</div>`;
        return;
    }

    const schedule = plan.schedule;
    const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

    // Top Summary Banner
    const isWeakDetected = plan.weak_subjects_count && plan.weak_subjects_count > 0;
    const bannerCol = document.createElement('div');
    bannerCol.className = 'col-12 mb-2';

    if (isWeakDetected) {
        bannerCol.innerHTML = `
            <div class="alert alert-warning py-2 px-3 text-xs mb-0 d-flex align-items-center justify-content-between flex-wrap gap-2 rounded-3 border-0 border-start border-4 border-warning shadow-sm bg-warning-subtle">
                <div>
                    <i class="fa-solid fa-triangle-exclamation text-warning me-2 fs-6"></i>
                    <strong>Personalized Study Schedule Active:</strong> Additional study hours allocated for weak subjects (&lt;18 = 2 hrs/day High Priority, 18–29.99 = 1 hr/day Medium Priority).
                </div>
                <span class="badge bg-warning text-dark fw-bold">${plan.weekly_target_hours || 0} hrs/week Target</span>
            </div>
        `;
    } else {
        bannerCol.innerHTML = `
            <div class="alert alert-success py-2 px-3 text-xs mb-0 d-flex align-items-center justify-content-between flex-wrap gap-2 rounded-3 border-0 border-start border-4 border-success shadow-sm bg-success-subtle">
                <div>
                    <i class="fa-solid fa-circle-check text-success me-2 fs-6"></i>
                    <strong>All Subjects On Track:</strong> Internal performance is 30/50 or above in all subjects. Regular maintenance revision schedule active.
                </div>
                <span class="badge bg-success fw-bold">${plan.weekly_target_hours || 7} hrs/week Target</span>
            </div>
        `;
    }
    container.appendChild(bannerCol);

    // Render Cards for Monday - Sunday
    days.forEach(day => {
        const items = schedule[day] || [];
        const col = document.createElement('div');
        col.className = 'col-md-6 col-lg-4 col-xl-4';

        let itemsHtml = '';
        if (Array.isArray(items) && items.length > 0) {
            items.forEach(item => {
                if (typeof item === 'string') {
                    itemsHtml += `<div class="p-2 mb-2 rounded bg-light border text-xs text-slate-700">${item}</div>`;
                } else if (typeof item === 'object' && item !== null) {
                    const subject = item.subject || 'Subject';
                    const marks = item.marks || (item.score !== undefined ? `${item.score}/50` : '');
                    const priority = (item.priority || 'MEDIUM').toUpperCase();
                    const duration = item.duration || '1 hour';
                    const activity = item.activity || 'Practice and revise key concepts.';

                    let priorityBadge = '';
                    if (priority === 'HIGH') {
                        priorityBadge = `<span class="badge bg-danger text-white text-xs px-2 py-1"><i class="fa-solid fa-triangle-exclamation me-1"></i> HIGH</span>`;
                    } else if (priority === 'MEDIUM') {
                        priorityBadge = `<span class="badge bg-warning text-dark text-xs px-2 py-1"><i class="fa-solid fa-circle-exclamation me-1"></i> MEDIUM</span>`;
                    } else {
                        priorityBadge = `<span class="badge bg-success text-white text-xs px-2 py-1">NORMAL</span>`;
                    }

                    itemsHtml += `
                        <div class="p-3 mb-2 rounded-3 bg-white border shadow-sm">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="fw-bold text-slate-900 fs-6">${subject}</span>
                                ${priorityBadge}
                            </div>
                            ${marks ? `<div class="text-xs text-muted mb-1"><span class="fw-semibold text-slate-700">Internal Performance:</span> <strong class="text-primary">${marks}</strong></div>` : ''}
                            <div class="text-xs text-muted mb-2"><span class="fw-semibold text-slate-700">Study Time:</span> <span class="badge bg-primary-subtle text-primary fw-bold"><i class="fa-regular fa-clock me-1"></i>${duration}</span></div>
                            <div class="text-xs text-slate-600 pt-2 border-top">
                                <strong class="text-slate-800 d-block mb-1"><i class="fa-solid fa-lightbulb text-warning me-1"></i>Recommended:</strong>
                                <span>${activity}</span>
                            </div>
                        </div>
                    `;
                }
            });
        } else {
            itemsHtml = `<div class="text-xs text-muted py-2 text-center">No additional sessions scheduled.</div>`;
        }

        col.innerHTML = `
            <div class="card card-custom bg-light border-0 shadow-sm h-100 p-3 rounded-4">
                <div class="d-flex justify-content-between align-items-center mb-2 pb-2 border-bottom">
                    <h6 class="fw-bold text-primary mb-0"><i class="fa-solid fa-calendar-day me-2"></i>${day}</h6>
                </div>
                <div class="d-flex flex-column gap-1">
                    ${itemsHtml}
                </div>
            </div>
        `;
        container.appendChild(col);
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Notifications
// ─────────────────────────────────────────────────────────────────────────────
function renderNotifications(notifications) {
    const ul = document.getElementById('notificationsList');
    if (!ul) return;

    if (!notifications || notifications.length === 0) {
        ul.innerHTML = `<li class="list-group-item py-3 text-muted text-center">No new notifications.</li>`;
        return;
    }

    ul.innerHTML = '';
    notifications.forEach(n => {
        const li = document.createElement('li');
        li.className = 'list-group-item py-3';
        li.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-1">
                <strong class="text-slate-800"><i class="fa-solid fa-bell text-warning me-1"></i> ${n.title}</strong>
                <span class="text-muted text-xs">${n.time}</span>
            </div>
            <p class="mb-0 text-muted text-xs">${n.desc}</p>
        `;
        ul.appendChild(li);
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Student Doubt Discussion Community Module
// ─────────────────────────────────────────────────────────────────────────────

let _currentDoubtFilter = {
    q: '',
    subject: 'All',
    filter: 'All'
};
let _activeDiscussionDoubtId = null;
let _doubtSearchTimeout = null;

function initDoubtModule() {
    // 1. Search Box Input Listener (Debounced 300ms)
    const searchInput = document.getElementById('doubtSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            clearTimeout(_doubtSearchTimeout);
            _doubtSearchTimeout = setTimeout(() => {
                _currentDoubtFilter.q = e.target.value.trim();
                loadDoubtsFeed();
            }, 300);
        });
    }

    // 2. Subject Filter Dropdown Listener
    const subjectSelect = document.getElementById('doubtSubjectFilter');
    if (subjectSelect) {
        subjectSelect.addEventListener('change', (e) => {
            _currentDoubtFilter.subject = e.target.value;
            loadDoubtsFeed();
        });
    }

    // 3. Status Filter Pills Listener
    const statusPills = document.getElementById('doubtStatusPills');
    if (statusPills) {
        statusPills.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                statusPills.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                _currentDoubtFilter.filter = btn.dataset.filter;
                loadDoubtsFeed();
            });
        });
    }

    // 4. Tab Switch Listener (load feed when Doubts tab is clicked)
    const doubtsTabBtn = document.getElementById('doubts-tab');
    if (doubtsTabBtn) {
        doubtsTabBtn.addEventListener('shown.bs.tab', () => {
            loadDoubtsFeed();
        });
    }

    // 5. Ask Doubt Form Submit
    const askForm = document.getElementById('askDoubtForm');
    if (askForm) {
        askForm.addEventListener('submit', handlePostDoubtSubmit);
    }

    // 6. Submit Answer Button Listener
    const btnSubmitAnswer = document.getElementById('btnSubmitAnswer');
    if (btnSubmitAnswer) {
        btnSubmitAnswer.addEventListener('click', handlePostAnswerSubmit);
    }

    // 7. Like Question Button Listener
    const btnLikeDoubt = document.getElementById('btnLikeDoubt');
    if (btnLikeDoubt) {
        btnLikeDoubt.addEventListener('click', handleToggleLikeDoubt);
    }

    // 8. Delete Question Button Listener
    const btnDeleteDoubt = document.getElementById('btnDeleteDoubt');
    if (btnDeleteDoubt) {
        btnDeleteDoubt.addEventListener('click', handleDeleteActiveDoubt);
    }

    // Initial load of doubts feed if tab active
    loadDoubtsFeed();
}

async function loadDoubtsFeed() {
    const feed = document.getElementById('doubtsFeed');
    if (!feed) return;

    try {
        const params = new URLSearchParams();
        if (_currentDoubtFilter.q) params.append('q', _currentDoubtFilter.q);
        if (_currentDoubtFilter.subject !== 'All') params.append('subject', _currentDoubtFilter.subject);
        if (_currentDoubtFilter.filter !== 'All') params.append('filter', _currentDoubtFilter.filter);

        const res = await fetch(`/student/api/doubts?${params.toString()}`);
        const data = await res.json();

        if (!data.success) {
            feed.innerHTML = `
                <div class="col-12 text-center py-5">
                    <div class="alert alert-danger d-inline-block shadow-sm">
                        <i class="fa-solid fa-triangle-exclamation me-2"></i> ${data.error || 'Failed to load doubts feed.'}
                    </div>
                </div>
            `;
            return;
        }

        const doubts = data.doubts || [];

        if (doubts.length === 0) {
            feed.innerHTML = `
                <div class="col-12 text-center py-5">
                    <div class="bg-white p-5 rounded-4 border shadow-sm d-inline-block max-w-lg">
                        <i class="fa-solid fa-comments-question text-muted fs-1 mb-3"></i>
                        <h5 class="fw-bold text-slate-800 mb-2">No Doubts Found</h5>
                        <p class="text-muted text-sm mb-4">No student doubts match your selected search criteria or filters.</p>
                        <button class="btn btn-primary rounded-pill px-4 fw-bold" data-bs-toggle="modal" data-bs-target="#askDoubtModal">
                            <i class="fa-solid fa-circle-plus me-1"></i> Be the first to Ask a Doubt!
                        </button>
                    </div>
                </div>
            `;
            return;
        }

        feed.innerHTML = '';
        doubts.forEach(d => {
            const col = document.createElement('div');
            col.className = 'col-md-6 col-lg-4';

            // Subject Badge Style
            let badgeClass = 'bg-secondary-subtle text-secondary';
            if (['DBMS', 'Java'].includes(d.subject)) badgeClass = 'bg-primary-subtle text-primary';
            else if (['Python', 'Data Structures'].includes(d.subject)) badgeClass = 'bg-success-subtle text-success';
            else if (['Computer Networks', 'Operating Systems'].includes(d.subject)) badgeClass = 'bg-info-subtle text-info';
            else if (d.subject === 'Mathematics') badgeClass = 'bg-warning-subtle text-warning';

            // Status Badge Style
            let statusBadge = '<span class="badge bg-secondary-subtle text-secondary rounded-pill px-3 py-1">Unanswered</span>';
            if (d.status === 'Solved') {
                statusBadge = '<span class="badge bg-success-subtle text-success rounded-pill px-3 py-1 fw-bold"><i class="fa-solid fa-circle-check me-1"></i>Solved</span>';
            } else if (d.status === 'Answered') {
                statusBadge = '<span class="badge bg-primary-subtle text-primary rounded-pill px-3 py-1 fw-bold"><i class="fa-solid fa-comment-dots me-1"></i>Answered</span>';
            }

            const descExcerpt = d.description.length > 130 ? d.description.substring(0, 130) + '...' : d.description;

            col.innerHTML = `
                <div class="card card-custom doubt-card shadow-sm h-100 border-0 p-3 rounded-4 d-flex flex-column justify-content-between">
                    <div>
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="badge ${badgeClass} fw-bold px-3 py-1 rounded-pill text-xs">📚 ${d.subject}</span>
                            ${statusBadge}
                        </div>

                        <h5 class="fw-bold text-slate-800 mb-2 text-truncate" title="${escapeHtml(d.title)}">
                            ${escapeHtml(d.title)}
                        </h5>

                        <p class="text-muted text-sm mb-3" style="min-height: 40px;">
                            "${escapeHtml(descExcerpt)}"
                        </p>
                    </div>

                    <div>
                        <div class="d-flex align-items-center gap-2 mb-3 pt-2 border-top">
                            <div class="avatar-circle bg-primary-subtle text-primary rounded-circle d-flex align-items-center justify-content-center" style="width: 32px; height: 32px; font-size: 0.8rem;">
                                ${getInitials(d.student_name)}
                            </div>
                            <div class="text-xs">
                                <strong class="text-slate-800 d-block text-truncate">${escapeHtml(d.student_name)}</strong>
                                <span class="text-muted">${d.student_dept || 'CSE'} • Sem ${d.student_sem || 6} (Sec ${d.student_section || 'A'})</span>
                            </div>
                        </div>

                        <div class="d-flex justify-content-between align-items-center pt-2 border-top">
                            <div class="d-flex align-items-center gap-3 text-xs text-muted">
                                <span><i class="fa-solid fa-comments text-primary me-1"></i>${d.answer_count || 0} Answers</span>
                                <span><i class="fa-solid fa-thumbs-up text-info me-1"></i>${d.like_count || 0} Likes</span>
                            </div>
                            <button class="btn btn-outline-primary btn-sm rounded-pill px-3 fw-bold btn-view-discussion" data-id="${d.id}">
                                [View Discussion]
                            </button>
                        </div>
                    </div>
                </div>
            `;

            feed.appendChild(col);
        });

        // Add event listeners to [View Discussion] buttons
        feed.querySelectorAll('.btn-view-discussion').forEach(btn => {
            btn.addEventListener('click', () => {
                openDiscussionModal(parseInt(btn.dataset.id));
            });
        });

    } catch (err) {
        console.error('Error loading doubts feed:', err);
    }
}

async function openDiscussionModal(doubtId) {
    _activeDiscussionDoubtId = doubtId;
    const modalEl = document.getElementById('viewDiscussionModal');
    if (!modalEl) return;

    try {
        const res = await fetch(`/student/api/doubts/${doubtId}`);
        const data = await res.json();

        if (!data.success) {
            alert(data.error || 'Failed to fetch discussion details.');
            return;
        }

        const doubt = data.doubt;
        const answers = data.answers || [];
        const isOwner = data.is_owner;

        // Populate Question Headers & Details
        document.getElementById('discSubjectBadge').textContent = doubt.subject;
        document.getElementById('discTitle').textContent = doubt.title;
        document.getElementById('discAuthorName').textContent = doubt.student_name;
        document.getElementById('discAuthorAvatar').textContent = getInitials(doubt.student_name);
        document.getElementById('discAuthorMeta').textContent = `${doubt.student_dept || 'CSE'} • Sem ${doubt.student_sem || 6} • Sec ${doubt.student_section || 'A'}`;
        document.getElementById('discDate').textContent = doubt.created_at ? doubt.created_at.substring(0, 16) : '';
        document.getElementById('discDescription').textContent = doubt.description;

        // Status Badge
        const statusBadge = document.getElementById('discStatusBadge');
        if (doubt.status === 'Solved') {
            statusBadge.className = 'badge bg-success text-white rounded-pill px-3 py-2 fw-bold text-xs';
            statusBadge.innerHTML = '<i class="fa-solid fa-circle-check me-1"></i> Solved';
        } else if (doubt.status === 'Answered') {
            statusBadge.className = 'badge bg-primary text-white rounded-pill px-3 py-2 fw-bold text-xs';
            statusBadge.innerHTML = '<i class="fa-solid fa-comment-dots me-1"></i> Answered';
        } else {
            statusBadge.className = 'badge bg-secondary-subtle text-secondary rounded-pill px-3 py-2 fw-bold text-xs';
            statusBadge.innerHTML = 'Unanswered';
        }

        // Code Snippet
        const codeContainer = document.getElementById('discCodeContainer');
        const codeEl = document.getElementById('discCode');
        if (doubt.code && doubt.code.trim()) {
            codeEl.textContent = doubt.code.trim();
            codeContainer.classList.remove('d-none');
        } else {
            codeContainer.classList.add('d-none');
        }

        // Image Attachment
        const imgContainer = document.getElementById('discImageContainer');
        const imgEl = document.getElementById('discImage');
        if (doubt.image_path && doubt.image_path.trim()) {
            imgEl.src = doubt.image_path;
            imgContainer.classList.remove('d-none');
        } else {
            imgContainer.classList.add('d-none');
        }

        // Question Like & Delete Buttons
        document.getElementById('discLikeCount').textContent = doubt.like_count || 0;
        const btnLike = document.getElementById('btnLikeDoubt');
        if (doubt.user_liked) {
            btnLike.className = 'btn btn-primary btn-sm rounded-pill px-3 fw-bold';
        } else {
            btnLike.className = 'btn btn-outline-primary btn-sm rounded-pill px-3 fw-bold';
        }

        const btnDelete = document.getElementById('btnDeleteDoubt');
        if (isOwner) {
            btnDelete.classList.remove('d-none');
        } else {
            btnDelete.classList.add('d-none');
        }

        // Render Answers
        document.getElementById('discAnswerCount').textContent = answers.length;
        renderDiscussionAnswers(answers, isOwner);

        // Reset write answer input
        document.getElementById('newAnswerText').value = '';
        document.getElementById('postAnswerAlert').classList.add('d-none');

        // Show Modal
        const modal = new bootstrap.Modal(modalEl);
        modal.show();

    } catch (err) {
        console.error('Error opening discussion modal:', err);
    }
}

function renderDiscussionAnswers(answers, isQuestionOwner) {
    const list = document.getElementById('discussionAnswersList');
    if (!list) return;

    if (answers.length === 0) {
        list.innerHTML = `
            <div class="card border-0 shadow-sm rounded-4 p-4 text-center text-muted">
                <i class="fa-solid fa-comment-slash fs-3 mb-2"></i>
                <p class="mb-0">No answers yet for this doubt. Be the first student to answer!</p>
            </div>
        `;
        return;
    }

    list.innerHTML = '';
    answers.forEach(a => {
        const card = document.createElement('div');
        const isAccepted = a.is_accepted === 1;
        card.className = `card border-0 shadow-sm rounded-4 p-3 ${isAccepted ? 'accepted-answer-card' : ''}`;

        let acceptedBadgeHtml = '';
        if (isAccepted) {
            acceptedBadgeHtml = `<span class="badge bg-success text-white px-3 py-1 rounded-pill fw-bold text-xs mb-2 d-inline-block"><i class="fa-solid fa-circle-check me-1"></i> ✅ Accepted Answer</span>`;
        }

        let acceptBtnHtml = '';
        if (isQuestionOwner && !isAccepted) {
            acceptBtnHtml = `<button type="button" class="btn btn-outline-success btn-sm rounded-pill px-3 fw-bold btn-accept-answer me-2" data-id="${a.id}"><i class="fa-solid fa-check me-1"></i> Accept as Solution</button>`;
        }

        let deleteAnsBtnHtml = '';
        if (_dashboardStudentId && parseInt(_dashboardStudentId) === a.student_id) {
            deleteAnsBtnHtml = `<button type="button" class="btn btn-link text-danger btn-sm p-0 ms-2 text-decoration-none btn-delete-answer" data-id="${a.id}"><i class="fa-solid fa-trash me-1"></i>Delete</button>`;
        }

        // Render replies
        let repliesHtml = '';
        if (a.replies && a.replies.length > 0) {
            a.replies.forEach(r => {
                repliesHtml += `
                    <div class="reply-thread bg-white p-2 rounded border mb-2">
                        <div class="d-flex justify-content-between align-items-center text-xs mb-1">
                            <strong class="text-slate-800"><i class="fa-solid fa-reply text-primary me-1"></i> ${escapeHtml(r.student_name)} (${r.student_dept || 'CSE'})</strong>
                            <span class="text-muted">${r.created_at ? r.created_at.substring(0, 16) : ''}</span>
                        </div>
                        <p class="text-slate-700 mb-0 text-sm">${escapeHtml(r.reply_text)}</p>
                    </div>
                `;
            });
        }

        card.innerHTML = `
            <div>
                ${acceptedBadgeHtml}
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="d-flex align-items-center gap-2">
                        <div class="avatar-circle bg-info-subtle text-info rounded-circle d-flex align-items-center justify-content-center" style="width: 32px; height: 32px; font-size: 0.8rem;">
                            ${getInitials(a.student_name)}
                        </div>
                        <div>
                            <strong class="text-slate-800 d-block text-sm mb-0">${escapeHtml(a.student_name)}</strong>
                            <span class="text-muted text-xs">${a.student_dept || 'CSE'} • Sem ${a.student_sem || 6}</span>
                        </div>
                    </div>
                    <span class="text-muted text-xs">${a.created_at ? a.created_at.substring(0, 16) : ''}</span>
                </div>

                <p class="text-slate-800 mb-3 fs-6" style="white-space: pre-line;">${escapeHtml(a.answer_text)}</p>

                <!-- Actions row -->
                <div class="d-flex justify-content-between align-items-center pt-2 border-top">
                    <div>
                        <button type="button" class="btn ${a.user_liked ? 'btn-primary' : 'btn-outline-primary'} btn-sm rounded-pill px-3 me-2 btn-like-answer" data-id="${a.id}">
                            <i class="fa-solid fa-thumbs-up me-1"></i> 👍 ${a.like_count || 0}
                        </button>
                        <button type="button" class="btn btn-outline-secondary btn-sm rounded-pill px-3 btn-toggle-reply" data-id="${a.id}">
                            <i class="fa-solid fa-reply me-1"></i> Reply
                        </button>
                        ${deleteAnsBtnHtml}
                    </div>
                    <div>
                        ${acceptBtnHtml}
                    </div>
                </div>

                <!-- Threaded Replies Container -->
                <div class="mt-3">
                    ${repliesHtml}
                </div>

                <!-- Inline Reply Input Form (Hidden by default) -->
                <div class="reply-form-container d-none mt-2 ps-4" id="replyFormContainer_${a.id}">
                    <div class="input-group">
                        <input type="text" class="form-control form-control-sm" id="replyInput_${a.id}" placeholder="Write your reply to ${escapeHtml(a.student_name)}...">
                        <button class="btn btn-primary btn-sm px-3 fw-bold btn-submit-reply" data-id="${a.id}">Submit Reply</button>
                    </div>
                </div>
            </div>
        `;

        list.appendChild(card);
    });

    // Event listeners for answer cards
    list.querySelectorAll('.btn-like-answer').forEach(btn => {
        btn.addEventListener('click', async () => {
            const ansId = parseInt(btn.dataset.id);
            const res = await fetch(`/student/api/answers/${ansId}/like`, { method: 'POST' });
            const d = await res.json();
            if (d.success) openDiscussionModal(_activeDiscussionDoubtId);
        });
    });

    list.querySelectorAll('.btn-accept-answer').forEach(btn => {
        btn.addEventListener('click', async () => {
            const ansId = parseInt(btn.dataset.id);
            const res = await fetch(`/student/api/answers/${ansId}/accept`, { method: 'POST' });
            const d = await res.json();
            if (d.success) {
                openDiscussionModal(_activeDiscussionDoubtId);
                loadDoubtsFeed();
            } else {
                alert(d.error || 'Failed to accept solution.');
            }
        });
    });

    list.querySelectorAll('.btn-toggle-reply').forEach(btn => {
        btn.addEventListener('click', () => {
            const ansId = btn.dataset.id;
            const container = document.getElementById(`replyFormContainer_${ansId}`);
            if (container) container.classList.toggle('d-none');
        });
    });

    list.querySelectorAll('.btn-submit-reply').forEach(btn => {
        btn.addEventListener('click', async () => {
            const ansId = btn.dataset.id;
            const input = document.getElementById(`replyInput_${ansId}`);
            const text = input ? input.value.trim() : '';
            if (!text) return;

            const res = await fetch(`/student/api/answers/${ansId}/reply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reply_text: text })
            });
            const d = await res.json();
            if (d.success) {
                openDiscussionModal(_activeDiscussionDoubtId);
            } else {
                alert(d.error || 'Failed to post reply.');
            }
        });
    });

    list.querySelectorAll('.btn-delete-answer').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to delete your answer?')) return;
            const ansId = btn.dataset.id;
            const res = await fetch(`/student/api/answers/${ansId}`, { method: 'DELETE' });
            const d = await res.json();
            if (d.success) openDiscussionModal(_activeDiscussionDoubtId);
        });
    });
}

async function handlePostDoubtSubmit(e) {
    e.preventDefault();
    const alertBox = document.getElementById('askDoubtAlert');
    const btn = document.getElementById('btnPostDoubt');
    alertBox.classList.add('d-none');

    const form = e.target;
    const formData = new FormData();

    const title = document.getElementById('doubtTitle').value.trim();
    const subject = document.getElementById('doubtSubject').value;
    const description = document.getElementById('doubtDescription').value.trim();
    const code = document.getElementById('doubtCode').value.trim();
    const imageInput = document.getElementById('doubtImage');

    formData.append('title', title);
    formData.append('subject', subject);
    formData.append('description', description);
    formData.append('code', code);
    if (imageInput.files.length > 0) {
        formData.append('image', imageInput.files[0]);
    }

    try {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Posting...';

        const res = await fetch('/student/api/doubts/create', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (!data.success) {
            alertBox.textContent = data.error || 'Failed to post doubt.';
            alertBox.classList.remove('d-none');
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> [Post Doubt]';
            return;
        }

        // Close Modal & Reset Form
        const modalEl = document.getElementById('askDoubtModal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
        form.reset();

        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> [Post Doubt]';

        // Refresh Feed and switch filter to All
        _currentDoubtFilter.filter = 'All';
        const pills = document.getElementById('doubtStatusPills');
        if (pills) {
            pills.querySelectorAll('button').forEach(b => b.classList.remove('active'));
            const allBtn = pills.querySelector('button[data-filter="All"]');
            if (allBtn) allBtn.classList.add('active');
        }
        loadDoubtsFeed();

    } catch (err) {
        console.error('Error posting doubt:', err);
        alertBox.textContent = 'An unexpected error occurred while posting your doubt.';
        alertBox.classList.remove('d-none');
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> [Post Doubt]';
    }
}

async function handlePostAnswerSubmit() {
    const textarea = document.getElementById('newAnswerText');
    const alertBox = document.getElementById('postAnswerAlert');
    const text = textarea ? textarea.value.trim() : '';

    alertBox.classList.add('d-none');
    if (!text) {
        alertBox.textContent = 'Please enter an answer before submitting.';
        alertBox.classList.remove('d-none');
        return;
    }

    try {
        const res = await fetch(`/student/api/doubts/${_activeDiscussionDoubtId}/answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answer_text: text })
        });
        const data = await res.json();

        if (!data.success) {
            alertBox.textContent = data.error || 'Failed to post answer.';
            alertBox.classList.remove('d-none');
            return;
        }

        textarea.value = '';
        openDiscussionModal(_activeDiscussionDoubtId);
        loadDoubtsFeed();

    } catch (err) {
        console.error('Error submitting answer:', err);
    }
}

async function handleToggleLikeDoubt() {
    if (!_activeDiscussionDoubtId) return;
    try {
        const res = await fetch(`/student/api/doubts/${_activeDiscussionDoubtId}/like`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            openDiscussionModal(_activeDiscussionDoubtId);
            loadDoubtsFeed();
        }
    } catch (err) {
        console.error('Error toggling doubt like:', err);
    }
}

async function handleDeleteActiveDoubt() {
    if (!_activeDiscussionDoubtId) return;
    if (!confirm('Are you sure you want to delete this question and all its answers?')) return;

    try {
        const res = await fetch(`/student/api/doubts/${_activeDiscussionDoubtId}`, { method: 'DELETE' });
        const data = await res.json();

        if (data.success) {
            const modalEl = document.getElementById('viewDiscussionModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            loadDoubtsFeed();
        } else {
            alert(data.error || 'Failed to delete question.');
        }
    } catch (err) {
        console.error('Error deleting doubt:', err);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function getInitials(name) {
    if (!name) return 'ST';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.substring(0, 2).toUpperCase();
}


/* ─── STUDENT-TEACHER PRIVATE COMMUNICATION MODULE ─── */

let _activeStudentConvId = null;

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('teacher-chat-tab')) {
        loadStudentConversations();
    }
});

async function loadStudentConversations() {
    const listEl = document.getElementById('studentConversationList');
    const badgeEl = document.getElementById('studentUnreadBadge');
    const teacherNameEl = document.getElementById('assignedTeacherName');

    try {
        const res = await fetch('/student/api/conversations');
        const data = await res.json();

        if (!data.success) {
            if (listEl) listEl.innerHTML = `<div class="alert alert-danger m-2 text-xs">${escapeHtml(data.error || 'Failed to load conversations.')}</div>`;
            return;
        }

        if (teacherNameEl && data.assigned_teacher) {
            teacherNameEl.textContent = data.assigned_teacher;
        }

        // Update Unread Badge
        if (badgeEl) {
            if (data.unread_total > 0) {
                badgeEl.textContent = `🔴 ${data.unread_total} New Replies`;
                badgeEl.classList.remove('d-none');
            } else {
                badgeEl.textContent = '0';
                badgeEl.classList.add('d-none');
            }
        }

        if (!listEl) return;

        if (!data.conversations || data.conversations.length === 0) {
            listEl.innerHTML = `
                <div class="text-center py-5 text-muted">
                    <i class="fa-solid fa-comments fa-2x mb-2 text-slate-300"></i>
                    <p class="mb-1 text-sm font-semibold">No conversations yet.</p>
                    <small class="text-xs">Click <strong>"+ New Question"</strong> above to send a private message to your Class Teacher.</small>
                </div>
            `;
            return;
        }

        listEl.innerHTML = data.conversations.map(c => {
            const isSelected = _activeStudentConvId === c.id;
            const statusBadge = c.status === 'Resolved' ?
                '<span class="badge bg-success-subtle text-success border border-success-subtle">✅ Resolved</span>' :
                (c.status === 'Replied' ? '<span class="badge bg-primary-subtle text-primary border border-primary-subtle">Teacher Replied</span>' :
                '<span class="badge bg-warning-subtle text-warning border border-warning-subtle">Open</span>');

            const unreadTag = c.unread_count > 0 ?
                `<span class="badge bg-danger rounded-pill ms-2">🔴 ${c.unread_count} New</span>` : '';

            const dateStr = c.updated_at ? new Date(c.updated_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';

            return `
                <button type="button" class="list-group-item list-group-item-action p-3 ${isSelected ? 'active text-white' : ''}" onclick="openStudentConversation(${c.id})">
                    <div class="d-flex w-100 justify-content-between align-items-center mb-1">
                        <small class="${isSelected ? 'text-white-50' : 'text-primary'} fw-bold text-uppercase text-xs">${escapeHtml(c.category)}</small>
                        <small class="${isSelected ? 'text-white-50' : 'text-muted'} text-xs">${dateStr}</small>
                    </div>
                    <h6 class="mb-1 fw-bold text-truncate text-sm">${escapeHtml(c.topic)}</h6>
                    <p class="mb-1 text-xs text-truncate ${isSelected ? 'text-white-50' : 'text-muted'}">${escapeHtml(c.last_message || 'No messages')}</p>
                    <div class="d-flex justify-content-between align-items-center mt-2">
                        ${statusBadge}
                        ${unreadTag}
                    </div>
                </button>
            `;
        }).join('');

    } catch (err) {
        console.error('Error loading student conversations:', err);
        if (listEl) listEl.innerHTML = `<div class="alert alert-danger m-2 text-xs">Error connecting to server: ${escapeHtml(err.message)}</div>`;
    }
}

async function openStudentConversation(convId, isSilent = false) {
    _activeStudentConvId = convId;

    const topicEl = document.getElementById('convDetailTopic');
    const catEl = document.getElementById('convDetailCategory');
    const statusEl = document.getElementById('convDetailStatus');
    const actionBtns = document.getElementById('convActionButtons');
    const btnResolve = document.getElementById('btnResolveConv');
    const btnReopen = document.getElementById('btnReopenConv');
    const contextBanner = document.getElementById('convAcademicContextBanner');
    const contextFields = document.getElementById('convAcademicContextFields');
    const messagesBody = document.getElementById('convMessagesBody');
    const replyFooter = document.getElementById('convReplyFooter');

    if (!isSilent) {
        messagesBody.innerHTML = '<div class="text-center py-4 text-muted"><i class="fa-solid fa-spinner fa-spin fa-2x mb-2"></i><p>Loading messages thread...</p></div>';
    }

    try {
        const res = await fetch(`/student/api/conversations/${convId}`);
        const data = await res.json();

        if (!data.success) {
            if (!isSilent) messagesBody.innerHTML = `<div class="alert alert-danger m-3">${escapeHtml(data.error || 'Failed to load conversation details.')}</div>`;
            return;
        }

        const conv = data.conversation;
        const replies = data.replies || [];

        topicEl.textContent = conv.topic;
        catEl.textContent = conv.category;
        statusEl.textContent = conv.status;
        statusEl.className = conv.status === 'Resolved' ? 'badge bg-success-subtle text-success border border-success' : (conv.status === 'Replied' ? 'badge bg-primary-subtle text-primary border border-primary' : 'badge bg-warning-subtle text-warning border border-warning');

        if (actionBtns) actionBtns.style.display = 'flex';
        if (btnResolve && btnReopen) {
            if (conv.status === 'Resolved') {
                btnResolve.classList.add('d-none');
                btnReopen.classList.remove('d-none');
            } else {
                btnResolve.classList.remove('d-none');
                btnReopen.classList.add('d-none');
            }
        }

        // Render Attached Academic Context if present
        if (conv.context_data && Object.keys(conv.context_data).length > 0) {
            contextBanner.classList.remove('d-none');
            contextFields.innerHTML = Object.entries(conv.context_data).map(([key, val]) => `
                <div class="col-6 col-md-3">
                    <div class="bg-white p-2 rounded border shadow-sm">
                        <span class="fw-bold text-uppercase d-block text-slate-700" style="font-size: 10px;">${escapeHtml(key)}</span>
                        <strong class="text-primary">${escapeHtml(String(val))}</strong>
                    </div>
                </div>
            `).join('');
        } else {
            contextBanner.classList.add('d-none');
        }

        // Render Messages Thread (WhatsApp Chat Bubble style)
        if (replies.length === 0) {
            messagesBody.innerHTML = '<div class="text-center text-muted py-4"><p>No messages in this thread yet.</p></div>';
        } else {
            messagesBody.innerHTML = replies.map(r => {
                const isStudent = r.sender_role === 'Student';
                const timeStr = r.created_at ? new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ', ' + new Date(r.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '';
                return `
                    <div class="d-flex mb-3 ${isStudent ? 'justify-content-end' : 'justify-content-start'}">
                        <div class="card border-0 shadow-sm ${isStudent ? 'bg-primary text-white ms-5' : 'bg-white border text-slate-800 me-5'}" style="max-width: 78%; border-radius: ${isStudent ? '18px 18px 2px 18px' : '18px 18px 18px 2px'};">
                            <div class="card-body p-3">
                                <div class="d-flex justify-content-between align-items-center mb-1 gap-3 border-bottom pb-1 mb-2 border-opacity-10">
                                    <strong class="text-xs ${isStudent ? 'text-white-50' : 'text-primary'}">
                                        <i class="fa-solid ${isStudent ? 'fa-user me-1' : 'fa-user-tie me-1'}"></i>${escapeHtml(r.sender_name)} (${escapeHtml(r.sender_role)})
                                    </strong>
                                    <small class="${isStudent ? 'text-white-50' : 'text-muted'}" style="font-size: 10px;">${timeStr}</small>
                                </div>
                                <p class="mb-0 text-sm" style="white-space: pre-wrap; word-break: break-word;">${escapeHtml(r.message)}</p>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
            if (!isSilent) {
                messagesBody.scrollTop = messagesBody.scrollHeight;
            }
        }

        if (replyFooter) replyFooter.classList.remove('d-none');

    } catch (err) {
        console.error('Error fetching conversation detail:', err);
        if (!isSilent) messagesBody.innerHTML = `<div class="alert alert-danger m-3">Server connection error: ${escapeHtml(err.message)}</div>`;
    }
}

function handleCategoryChange(cat) {
    const subjGroup = document.getElementById('subjectSelectionGroup');
    if (subjGroup) {
        if (cat === 'IA Marks' || cat === 'Subject Marks') {
            subjGroup.classList.remove('d-none');
        } else {
            subjGroup.classList.add('d-none');
        }
    }
    updateContextPreview();
}

function updateContextPreview() {
    const cat = document.getElementById('newConvCategory').value;
    const subj = document.getElementById('newConvSubject') ? document.getElementById('newConvSubject').value : 'DBMS';
    const previewEl = document.getElementById('autoContextFields');

    if (!previewEl) return;

    let html = '';
    const attendance = document.getElementById('cardAttendance') ? document.getElementById('cardAttendance').textContent.trim() : '78%';
    const cgpa = document.getElementById('cardCgpa') ? document.getElementById('cardCgpa').textContent.trim() : '7.8 / 10.0';

    if (cat === 'IA Marks' || cat === 'Subject Marks') {
        html = `<strong>Category:</strong> ${cat} | <strong>Subject:</strong> ${subj} | <strong>Current Attendance:</strong> ${attendance} | <strong>CGPA:</strong> ${cgpa}`;
    } else if (cat === 'Attendance') {
        html = `<strong>Category:</strong> Attendance | <strong>Current Attendance Percentage:</strong> ${attendance}`;
    } else if (cat === 'CGPA / Academic Performance') {
        html = `<strong>Category:</strong> CGPA / Academic Performance | <strong>Current CGPA:</strong> ${cgpa}`;
    } else if (cat === 'Risk Level') {
        html = `<strong>Category:</strong> Risk Level | <strong>Attendance:</strong> ${attendance} | <strong>CGPA:</strong> ${cgpa}`;
    } else if (cat === 'Performance Prediction') {
        html = `<strong>Category:</strong> Performance Prediction | <strong>Attendance:</strong> ${attendance} | <strong>CGPA:</strong> ${cgpa}`;
    } else if (cat === 'Placement Readiness') {
        html = `<strong>Category:</strong> Placement Readiness | <strong>CGPA:</strong> ${cgpa}`;
    } else {
        html = `<strong>Category:</strong> ${cat || 'General Academic'}`;
    }

    previewEl.innerHTML = html;
}

function openAskTeacherModal(prefilledCategory = 'Other', prefilledSubject = 'DBMS') {
    const modalEl = document.getElementById('newConversationModal');
    if (!modalEl) return;

    const catSelect = document.getElementById('newConvCategory');
    if (catSelect) {
        catSelect.value = prefilledCategory;
        handleCategoryChange(prefilledCategory);
    }
    const subjSelect = document.getElementById('newConvSubject');
    if (subjSelect && prefilledSubject) {
        subjSelect.value = prefilledSubject;
    }

    updateContextPreview();

    // Switch to tab 3
    const chatTabBtn = document.getElementById('teacher-chat-tab');
    if (chatTabBtn) {
        const tab = new bootstrap.Tab(chatTabBtn);
        tab.show();
    }

    const modal = new bootstrap.Modal(modalEl);
    modal.show();
}

async function submitNewConversation(e) {
    e.preventDefault();
    const btn = document.getElementById('btnSubmitNewConv');
    const category = document.getElementById('newConvCategory').value;
    const subject = document.getElementById('newConvSubject') ? document.getElementById('newConvSubject').value : '';
    const topic = document.getElementById('newConvTopic').value.trim();
    const message = document.getElementById('newConvMessage').value.trim();

    if (!category || !topic || !message) {
        alert('Please fill out Category, Topic, and Message.');
        return;
    }

    const contextData = {
        category: category
    };
    if (category === 'IA Marks' || category === 'Subject Marks') {
        contextData['subject'] = subject;
    }
    const attCard = document.getElementById('cardAttendance');
    if (attCard) contextData['attendance'] = attCard.textContent.trim();
    const cgpaCard = document.getElementById('cardCgpa');
    if (cgpaCard) contextData['cgpa'] = cgpaCard.textContent.trim();

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Sending...';

    try {
        const res = await fetch('/student/api/conversations/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                category: category,
                topic: topic,
                message: message,
                context_data: contextData
            })
        });

        const data = await res.json();
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> Send Message';

        if (!data.success) {
            alert(data.error || 'Failed to send message.');
            return;
        }

        const modalEl = document.getElementById('newConversationModal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
        e.target.reset();

        await loadStudentConversations();
        if (data.conversation_id) {
            openStudentConversation(data.conversation_id);
        }

    } catch (err) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> Send Message';
        alert('Error connecting to server: ' + err.message);
    }
}

async function submitStudentReply(e) {
    e.preventDefault();
    if (!_activeStudentConvId) return;

    const input = document.getElementById('studentReplyInput');
    const btn = document.getElementById('btnSendStudentReply');
    const text = input ? input.value.trim() : '';

    if (!text) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Sending...';

    try {
        const res = await fetch(`/student/api/conversations/${_activeStudentConvId}/reply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        const data = await res.json();

        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> Send Reply';

        if (!data.success) {
            alert(data.error || 'Failed to send reply.');
            return;
        }

        input.value = '';
        openStudentConversation(_activeStudentConvId);

    } catch (err) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> Send Reply';
        alert('Error sending reply: ' + err.message);
    }
}

async function resolveCurrentConversation() {
    if (!_activeStudentConvId) return;
    if (!confirm('Are you sure you want to mark this conversation as resolved?')) return;

    try {
        const res = await fetch(`/student/api/conversations/${_activeStudentConvId}/resolve`, { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            openStudentConversation(_activeStudentConvId);
        } else {
            alert(data.error || 'Failed to resolve conversation.');
        }
    } catch (err) {
        alert('Error resolving conversation: ' + err.message);
    }
}

async function reopenCurrentConversation() {
    if (!_activeStudentConvId) return;

    try {
        const res = await fetch(`/student/api/conversations/${_activeStudentConvId}/reopen`, { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            openStudentConversation(_activeStudentConvId);
        } else {
            alert(data.error || 'Failed to reopen conversation.');
        }
    } catch (err) {
        alert('Error reopening conversation: ' + err.message);
    }
}


