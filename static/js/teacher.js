/**
 * Student Performance Analyzer & Marks Prediction System Teacher Dashboard JavaScript
 * Handles Approval Workflow, Student Record Editing, CSV Upload, & Analytics Visualizations
 */

let chartPassFail = null;
let chartSubjectMarks = null;
let chartSemTrend = null;
let chartAttendanceDist = null;
let chartRiskDist = null;
let chartWeakSubjects = null;
let editModal = null;
let csvModal = null;

function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

document.addEventListener('DOMContentLoaded', () => {
    loadPendingStudents();
    loadTeacherAnalytics();
    loadManageStudents();

    const editModalEl = document.getElementById('editStudentModal');
    if (editModalEl) editModal = new bootstrap.Modal(editModalEl);

    const csvModalEl = document.getElementById('csvImportModal');
    if (csvModalEl) csvModal = new bootstrap.Modal(csvModalEl);

    const filterForm = document.getElementById('filterForm');
    if (filterForm) {
        filterForm.addEventListener('submit', (e) => {
            e.preventDefault();
            loadTeacherAnalytics();
        });
    }

    const teacherEditForm = document.getElementById('teacherEditForm');
    if (teacherEditForm) teacherEditForm.addEventListener('submit', handleTeacherEditSubmit);

    const csvUploadForm = document.getElementById('csvUploadForm');
    if (csvUploadForm) csvUploadForm.addEventListener('submit', handleCsvUploadSubmit);

    const msgTabBtn = document.getElementById('messages-tab');
    if (msgTabBtn) {
        msgTabBtn.addEventListener('shown.bs.tab', () => {
            loadTeacherConversations();
        });
    }
    loadTeacherConversations();

    // Real-time background polling for new student messages (every 4s)
    setInterval(() => {
        loadTeacherConversations();
        if (typeof _activeTeacherConvId !== 'undefined' && _activeTeacherConvId) {
            openTeacherConversation(_activeTeacherConvId, true);
        }
    }, 4000);
});

function downloadClassPDF() {
    const dept = document.getElementById('filterDept') ? document.getElementById('filterDept').value : 'All';
    const sem = document.getElementById('filterSem') ? document.getElementById('filterSem').value : 'All';
    const sec = document.getElementById('filterSec') ? document.getElementById('filterSec').value : 'All';

    window.location.href = `/report/class-pdf?department=${encodeURIComponent(dept)}&semester=${encodeURIComponent(sem)}&section=${encodeURIComponent(sec)}`;
}

async function handleCsvUploadSubmit(e) {
    e.preventDefault();
    const fileInput = document.getElementById('csvFileInput');
    const alertBox = document.getElementById('csvUploadAlert');
    const btn = document.getElementById('btnCsvSubmit');

    if (!fileInput.files || fileInput.files.length === 0) {
        alert('Please select a CSV file.');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-1"></i> Processing Upload...`;
    alertBox.classList.add('d-none');

    try {
        const res = await fetch('/teacher/api/upload-csv', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-upload me-1"></i> Process Batch Upload`;

        if (data.success) {
            alertBox.className = 'alert alert-success text-xs mt-2';
            alertBox.textContent = data.message;
            alertBox.classList.remove('d-none');
            setTimeout(() => {
                if (csvModal) csvModal.hide();
                loadTeacherAnalytics();
                loadManageStudents();
            }, 2000);
        } else {
            alertBox.className = 'alert alert-danger text-xs mt-2';
            alertBox.textContent = data.error || 'Upload failed.';
            alertBox.classList.remove('d-none');
        }
    } catch (err) {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-upload me-1"></i> Process Batch Upload`;
        alertBox.className = 'alert alert-danger text-xs mt-2';
        alertBox.textContent = 'Server connection error: ' + err.message;
        alertBox.classList.remove('d-none');
    }
}

async function loadPendingStudents() {
    const tbody = document.getElementById('pendingStudentsTable');
    if (!tbody) return;

    try {
        const res = await fetch('/teacher/api/pending-students');
        const data = await res.json();
        tbody.innerHTML = '';

        const pending = data.pending_students || [];
        document.getElementById('pendingCountBadge').textContent = pending.length;

        if (pending.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-muted">No student registrations pending approval. 🎉</td></tr>`;
            return;
        }

        pending.forEach(s => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="fw-bold text-primary">${s.usn || 'N/A'}</td>
                <td class="fw-semibold">${s.name}</td>
                <td>${s.email}</td>
                <td>${s.department || 'CSE'}</td>
                <td>Sem ${s.current_semester || s.semester || 5}</td>
                <td>${s.attendance}%</td>
                <td>${s.cgpa || 7.5}</td>
                <td class="text-xs text-muted">${s.created_at || 'Recently'}</td>
                <td>
                    <div class="d-flex gap-2">
                        <button class="btn btn-success btn-sm rounded-pill px-3" onclick="processApproval(${s.id}, 'approve')">
                            <i class="fa-solid fa-check me-1"></i> Approve
                        </button>
                        <button class="btn btn-outline-danger btn-sm rounded-pill px-3" onclick="processApproval(${s.id}, 'reject')">
                            <i class="fa-solid fa-xmark me-1"></i> Reject
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Failed to load pending students:', err);
    }
}

async function processApproval(studentId, action) {
    if (!confirm(`Are you sure you want to ${action} this student account?`)) return;

    try {
        const res = await fetch(`/teacher/api/approve-student/${studentId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        const data = await res.json();
        if (data.success) {
            alert(data.message);
            loadPendingStudents();
            loadTeacherAnalytics();
            loadManageStudents();
        } else {
            alert('Approval action failed: ' + data.error);
        }
    } catch (err) {
        alert('Server error: ' + err.message);
    }
}

async function loadManageStudents() {
    const tbody = document.getElementById('manageStudentsTable');
    if (!tbody) return;

    try {
        const res = await fetch('/records');
        const records = await res.json();
        tbody.innerHTML = '';

        if (!records || records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center py-4 text-muted">No approved student records found.</td></tr>`;
            return;
        }

        records.forEach(r => {
            const tr = document.createElement('tr');
            const resBadge = r.result === 'Pass' ? 'bg-success' : 'bg-danger';
            const riskBadge = r.risk === 'High' ? 'bg-danger' : (r.risk === 'Medium' ? 'bg-warning text-dark' : 'bg-success');

            tr.innerHTML = `
                <td class="fw-bold text-primary">${r.usn || '#' + r.id}</td>
                <td class="fw-semibold">${r.name}</td>
                <td>${r.department || 'CSE'}</td>
                <td>Sem ${r.semester || 5}</td>
                <td>${r.attendance}%</td>
                <td>${r.dbms_marks}</td>
                <td>${r.java_marks}</td>
                <td><span class="badge ${resBadge}">${r.result}</span></td>
                <td><span class="badge ${riskBadge}">${r.risk}</span></td>
                <td class="text-xs text-muted">${r.teacher_remarks || 'None'}</td>
                <td>
                    <button class="btn btn-primary btn-sm rounded-pill px-3" onclick="openEditModal(${r.id}, '${escapeHtml(r.name)}', ${r.attendance}, ${r.dbms_marks}, ${r.java_marks}, ${r.subject3_marks || 70}, ${r.subject4_marks || 70}, '${r.result}', '${r.risk}', '${escapeHtml(r.teacher_remarks || '')}')">
                        <i class="fa-solid fa-pen-to-square me-1"></i> Edit
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Failed to load manage students:', err);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, "&quot;");
}

function openEditModal(id, name, att, s1, s2, s3, s4, result, risk, remarks) {
    document.getElementById('editStudentId').value = id;
    document.getElementById('editStudentName').value = name;
    document.getElementById('editAttendance').value = att;
    document.getElementById('editSubject1').value = s1;
    document.getElementById('editSubject2').value = s2;
    document.getElementById('editSubject3').value = s3;
    document.getElementById('editSubject4').value = s4;
    document.getElementById('editResult').value = result;
    document.getElementById('editRiskLevel').value = risk;
    document.getElementById('editTeacherRemarks').value = remarks;

    if (editModal) editModal.show();
}

async function handleTeacherEditSubmit(e) {
    e.preventDefault();
    const studentId = document.getElementById('editStudentId').value;
    const payload = {
        attendance: document.getElementById('editAttendance').value,
        subject1_marks: document.getElementById('editSubject1').value,
        subject2_marks: document.getElementById('editSubject2').value,
        subject3_marks: document.getElementById('editSubject3').value,
        subject4_marks: document.getElementById('editSubject4').value,
        predicted_result: document.getElementById('editResult').value,
        risk_level: document.getElementById('editRiskLevel').value,
        teacher_remarks: document.getElementById('editTeacherRemarks').value
    };

    try {
        const res = await fetch(`/teacher/api/update-student/${studentId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            alert(data.message);
            if (editModal) editModal.hide();
            loadManageStudents();
            loadTeacherAnalytics();
        } else {
            alert('Update failed: ' + data.error);
        }
    } catch (err) {
        alert('Server error: ' + err.message);
    }
}

async function loadTeacherAnalytics() {
    const dept = document.getElementById('filterDept').value;
    const sem = document.getElementById('filterSem').value;
    const sec = document.getElementById('filterSec').value;
    const year = document.getElementById('filterYear').value;

    const url = `/teacher/api/analytics?department=${encodeURIComponent(dept)}&semester=${encodeURIComponent(sem)}&section=${encodeURIComponent(sec)}&academic_year=${encodeURIComponent(year)}`;

    try {
        const response = await fetch(url);
        const data = await response.json();

        updateCards(data.cards);
        renderTeacherCharts(data.charts);
    } catch (err) {
        console.error('Failed to load teacher analytics:', err);
    }
}

function updateCards(cards) {
    if (!cards) return;
    document.getElementById('cardTotal').textContent = cards.total_students || 0;
    document.getElementById('cardAvgCGPA').textContent = cards.avg_cgpa || '0.0';
    document.getElementById('cardAvgAtt').textContent = `${cards.avg_attendance || 0}%`;
    document.getElementById('cardPassPct').textContent = `${cards.pass_pct || 0}%`;
    document.getElementById('cardFailPct').textContent = `${cards.fail_pct || 0}%`;
    document.getElementById('cardHighRisk').textContent = cards.high_risk_count || 0;
    document.getElementById('cardExcellent').textContent = cards.excellent_count || 0;
}

function renderTeacherCharts(charts) {
    if (!charts) return;

    if (charts.pass_fail) {
        const ctx1 = document.getElementById('chartPassFail').getContext('2d');
        if (chartPassFail) chartPassFail.destroy();
        chartPassFail = new Chart(ctx1, {
            type: 'pie',
            data: {
                labels: charts.pass_fail.labels,
                datasets: [{
                    data: charts.pass_fail.data,
                    backgroundColor: ['#10B981', '#EF4444']
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }

    if (charts.subject_marks) {
        const ctx2 = document.getElementById('chartSubjectMarks').getContext('2d');
        if (chartSubjectMarks) chartSubjectMarks.destroy();
        chartSubjectMarks = new Chart(ctx2, {
            type: 'bar',
            data: {
                labels: charts.subject_marks.labels,
                datasets: [{
                    label: 'Avg Marks',
                    data: charts.subject_marks.data,
                    backgroundColor: '#2563EB',
                    borderRadius: 6
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100 } } }
        });
    }

    if (charts.sem_trend) {
        const ctx3 = document.getElementById('chartSemTrend').getContext('2d');
        if (chartSemTrend) chartSemTrend.destroy();
        chartSemTrend = new Chart(ctx3, {
            type: 'line',
            data: {
                labels: charts.sem_trend.labels,
                datasets: [{
                    label: 'Average CGPA',
                    data: charts.sem_trend.data,
                    borderColor: '#0284C7',
                    backgroundColor: 'rgba(2, 132, 199, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }

    if (charts.attendance_dist) {
        const ctx4 = document.getElementById('chartAttendanceDist').getContext('2d');
        if (chartAttendanceDist) chartAttendanceDist.destroy();
        chartAttendanceDist = new Chart(ctx4, {
            type: 'bar',
            data: {
                labels: charts.attendance_dist.labels,
                datasets: [{
                    label: 'Students Count',
                    data: charts.attendance_dist.data,
                    backgroundColor: ['#EF4444', '#F59E0B', '#3B82F6', '#10B981'],
                    borderRadius: 6
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }

    if (charts.risk_dist) {
        const ctx5 = document.getElementById('chartRiskDist').getContext('2d');
        if (chartRiskDist) chartRiskDist.destroy();
        chartRiskDist = new Chart(ctx5, {
            type: 'doughnut',
            data: {
                labels: charts.risk_dist.labels,
                datasets: [{
                    data: charts.risk_dist.data,
                    backgroundColor: ['#10B981', '#F59E0B', '#EF4444']
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }

    if (charts.weak_subjects) {
        const ctx6 = document.getElementById('chartWeakSubjects').getContext('2d');
        if (chartWeakSubjects) chartWeakSubjects.destroy();
        chartWeakSubjects = new Chart(ctx6, {
            type: 'bar',
            data: {
                labels: charts.weak_subjects.labels,
                datasets: [{
                    label: 'Students Below Threshold (<50)',
                    data: charts.weak_subjects.data,
                    backgroundColor: '#64748B',
                    borderRadius: 6
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }
}


/* ─── TEACHER-STUDENT PRIVATE COMMUNICATION MODULE ─── */

let _activeTeacherConvId = null;
let _currentMsgStatusFilter = 'All';

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('messages-tab')) {
        loadTeacherConversations();
    }
});

function filterTeacherMessages(status, btn) {
    _currentMsgStatusFilter = status;
    const filterBtns = document.getElementById('msgStatusFilterBtns');
    if (filterBtns) {
        filterBtns.querySelectorAll('button').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
    }
    loadTeacherConversations();
}

async function loadTeacherConversations() {
    const listEl = document.getElementById('teacherConversationList');
    const badgeEl = document.getElementById('teacherUnreadBadge');
    const headerBadgeEl = document.getElementById('teacherHeaderUnreadBadge');

    try {
        const res = await fetch(`/teacher/api/conversations?status=${encodeURIComponent(_currentMsgStatusFilter)}`);
        const data = await res.json();

        if (!data.success) {
            if (listEl) listEl.innerHTML = `<div class="alert alert-danger m-2 text-xs">${escapeHtml(data.error || 'Failed to load messages.')}</div>`;
            return;
        }

        // Update Unread Badges
        const unreadTotal = data.unread_total || 0;
        if (badgeEl) {
            if (unreadTotal > 0) {
                badgeEl.textContent = `${unreadTotal}`;
                badgeEl.classList.remove('d-none');
            } else {
                badgeEl.textContent = '0';
                badgeEl.classList.add('d-none');
            }
        }
        if (headerBadgeEl) {
            if (unreadTotal > 0) {
                headerBadgeEl.textContent = `🔴 ${unreadTotal} New`;
                headerBadgeEl.classList.remove('d-none');
            } else {
                headerBadgeEl.classList.add('d-none');
            }
        }

        if (!listEl) return;

        if (!data.conversations || data.conversations.length === 0) {
            listEl.innerHTML = `
                <div class="text-center py-5 text-muted">
                    <i class="fa-solid fa-inbox fa-2x mb-2 text-slate-300"></i>
                    <p class="mb-1 text-sm font-semibold">No student messages matching filter.</p>
                    <small class="text-xs">Messages sent by assigned students will appear here.</small>
                </div>
            `;
            return;
        }

        listEl.innerHTML = data.conversations.map(c => {
            const isSelected = _activeTeacherConvId === c.id;
            const statusBadge = c.status === 'Resolved' ?
                '<span class="badge bg-success-subtle text-success border border-success-subtle">✅ Resolved</span>' :
                (c.status === 'Replied' ? '<span class="badge bg-secondary-subtle text-secondary border">Replied</span>' :
                '<span class="badge bg-warning-subtle text-warning border border-warning-subtle">Open</span>');

            const unreadTag = c.unread_count > 0 ?
                `<span class="badge bg-danger rounded-pill ms-2">🔴 ${c.unread_count} New</span>` : '';

            const dateStr = c.updated_at ? new Date(c.updated_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';

            return `
                <button type="button" class="list-group-item list-group-item-action p-3 ${isSelected ? 'active text-white' : ''}" onclick="openTeacherConversation(${c.id})">
                    <div class="d-flex w-100 justify-content-between align-items-center mb-1">
                        <span class="fw-bold ${isSelected ? 'text-white' : 'text-primary'} text-sm">${escapeHtml(c.student_name)} <small class="${isSelected ? 'text-white-50' : 'text-muted'}">(${escapeHtml(c.usn)})</small></span>
                        <small class="${isSelected ? 'text-white-50' : 'text-muted'} text-xs">${dateStr}</small>
                    </div>
                    <div class="d-flex align-items-center gap-2 mb-1">
                        <span class="badge ${isSelected ? 'bg-light text-dark' : 'bg-secondary'} text-uppercase" style="font-size: 9px;">${escapeHtml(c.category)}</span>
                        <span class="fw-semibold text-truncate text-xs ${isSelected ? 'text-white-50' : 'text-slate-700'}">${escapeHtml(c.topic)}</span>
                    </div>
                    <p class="mb-1 text-xs text-truncate ${isSelected ? 'text-white-50' : 'text-muted'}">${escapeHtml(c.last_message || 'No messages')}</p>
                    <div class="d-flex justify-content-between align-items-center mt-2">
                        ${statusBadge}
                        ${unreadTag}
                    </div>
                </button>
            `;
        }).join('');

    } catch (err) {
        console.error('Error loading teacher conversations:', err);
        if (listEl) listEl.innerHTML = `<div class="alert alert-danger m-2 text-xs">Error connecting to server: ${escapeHtml(err.message)}</div>`;
    }
}

async function openTeacherConversation(convId, isSilent = false) {
    _activeTeacherConvId = convId;

    const nameEl = document.getElementById('tConvStudentName');
    const usnEl = document.getElementById('tConvStudentUsn');
    const metaEl = document.getElementById('tConvStudentMeta');
    const topicEl = document.getElementById('tConvTopic');
    const catEl = document.getElementById('tConvCategory');
    const statusEl = document.getElementById('tConvStatus');
    const actionsHeader = document.getElementById('tConvHeaderActions');
    const contextBox = document.getElementById('tConvAcademicContext');
    const messagesBody = document.getElementById('tConvMessagesBody');
    const replyFooter = document.getElementById('tConvReplyFooter');

    if (!isSilent) {
        messagesBody.innerHTML = '<div class="text-center py-4 text-muted"><i class="fa-solid fa-spinner fa-spin fa-2x mb-2"></i><p>Loading student thread...</p></div>';
    }

    try {
        const res = await fetch(`/teacher/api/conversations/${convId}`);
        const data = await res.json();

        if (!data.success) {
            if (!isSilent) messagesBody.innerHTML = `<div class="alert alert-danger m-3">${escapeHtml(data.error || 'Failed to load conversation details.')}</div>`;
            return;
        }

        const conv = data.conversation;
        const student = data.student || {};
        const replies = data.replies || [];

        nameEl.textContent = student.name || 'Student';
        usnEl.textContent = student.usn || 'USN';
        metaEl.textContent = `${student.department || 'CSE'} | Sem ${student.semester || 6} (Sec ${student.section || 'A'})`;
        topicEl.textContent = conv.topic;
        catEl.textContent = conv.category;
        statusEl.textContent = conv.status;
        statusEl.className = conv.status === 'Resolved' ? 'badge bg-success-subtle text-success border border-success' : (conv.status === 'Replied' ? 'badge bg-secondary-subtle text-secondary border' : 'badge bg-warning-subtle text-warning border border-warning');

        if (actionsHeader) actionsHeader.classList.remove('d-none');

        // Render Academic Context Card
        if (contextBox) {
            contextBox.classList.remove('d-none');
            let ctxHtml = `<div class="row g-2">
                <div class="col-4"><strong>Attendance:</strong> ${student.attendance}%</div>
                <div class="col-4"><strong>Overall CGPA:</strong> ${student.cgpa}</div>
                <div class="col-4"><strong>ML Risk:</strong> ${student.risk_level}</div>
            </div>`;
            if (conv.context_data && Object.keys(conv.context_data).length > 0) {
                ctxHtml += `<div class="mt-2 pt-2 border-top"><strong>Student Attached Context:</strong> ${Object.entries(conv.context_data).map(([k, v]) => `${k}: <span class="text-primary">${v}</span>`).join(' | ')}</div>`;
            }
            contextBox.innerHTML = ctxHtml;
        }

        // Render Message Stream (WhatsApp Chat Bubble style)
        if (replies.length === 0) {
            messagesBody.innerHTML = '<div class="text-center text-muted py-4"><p>No messages in this thread yet.</p></div>';
        } else {
            messagesBody.innerHTML = replies.map(r => {
                const isTeacher = r.sender_role === 'Teacher';
                const timeStr = r.created_at ? new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ', ' + new Date(r.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '';
                return `
                    <div class="d-flex mb-3 ${isTeacher ? 'justify-content-end' : 'justify-content-start'}">
                        <div class="card border-0 shadow-sm ${isTeacher ? 'bg-primary text-white ms-5' : 'bg-white border text-slate-800 me-5'}" style="max-width: 78%; border-radius: ${isTeacher ? '18px 18px 2px 18px' : '18px 18px 18px 2px'};">
                            <div class="card-body p-3">
                                <div class="d-flex justify-content-between align-items-center mb-1 gap-3 border-bottom pb-1 mb-2 border-opacity-10">
                                    <strong class="text-xs ${isTeacher ? 'text-white-50' : 'text-primary'}">
                                        <i class="fa-solid ${isTeacher ? 'fa-user-tie me-1' : 'fa-user me-1'}"></i>${escapeHtml(r.sender_name)} (${escapeHtml(r.sender_role)})
                                    </strong>
                                    <small class="${isTeacher ? 'text-white-50' : 'text-muted'}" style="font-size: 10px;">${timeStr}</small>
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
        console.error('Error fetching teacher conversation detail:', err);
        if (!isSilent) messagesBody.innerHTML = `<div class="alert alert-danger m-3">Server connection error: ${escapeHtml(err.message)}</div>`;
    }
}

async function submitTeacherReply(e) {
    e.preventDefault();
    if (!_activeTeacherConvId) return;

    const input = document.getElementById('teacherReplyInput');
    const btn = document.getElementById('btnSendTeacherReply');
    const text = input ? input.value.trim() : '';

    if (!text) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Replying...';

    try {
        const res = await fetch(`/teacher/api/conversations/${_activeTeacherConvId}/reply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        const data = await res.json();
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> Reply';

        if (!data.success) {
            alert(data.error || 'Failed to send reply.');
            return;
        }

        input.value = '';
        openTeacherConversation(_activeTeacherConvId);

    } catch (err) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> Reply';
        alert('Error sending reply: ' + err.message);
    }
}

async function resolveTeacherConversation() {
    if (!_activeTeacherConvId) return;
    if (!confirm('Mark this student conversation as resolved?')) return;

    try {
        const res = await fetch(`/teacher/api/conversations/${_activeTeacherConvId}/resolve`, { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            openTeacherConversation(_activeTeacherConvId);
        } else {
            alert(data.error || 'Failed to resolve conversation.');
        }
    } catch (err) {
        alert('Error resolving conversation: ' + err.message);
    }
}

