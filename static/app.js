/**
 * app.js - Data Insight Builder Client Application
 * (순수 바닐라 자바스크립트 & Chart.js 연동)
 *
 * 규약된 프론트엔드 콘솔 로그 태그:
 * [PAGE], [UPLOAD], [INSPECT], [SUGGEST], [RUN], [CHART], [EXPLAIN], [ERROR]
 */

let selectedFile = null;
let currentInspectData = null;
let currentSelectedTool = null;
let currentRunResult = null;
let activeChartInstance = null;
let currentReportMarkdown = "";
let chatHistory = [];

// 도구 기본 설명 및 필요 파라미터 맵
const TOOL_CONFIG = {
    "reshape_wide_to_long": { name: "연도 열 행으로 접기", params: [] },
    "quality_report": { name: "데이터 품질 진단 리포트", params: [] },
    "year_coverage": { name: "연도별 충실도 & 권장 기준연도", params: [] },
    "detect_aggregates": { name: "World/소득군 등 집계 행 탐지", params: [] },
    "describe_numeric": { name: "기술통계 요약", params: ["reference_period"] },
    "trend_line": { name: "연도별 시계열 추이 (선 차트)", params: ["entities", "start_year", "end_year"] },
    "top_bottom_n": { name: "상위·하위 N개 국가 (수평 막대)", params: ["reference_period", "n"] },
    "group_summary": { name: "그룹(대륙/소득군)별 평균 비교 (막대)", params: ["reference_period", "group_column"] },
    "change_rate": { name: "두 시점 사이 증가폭·변화율 (막대)", params: ["reference_period", "base_period", "n"] },
    "distribution": { name: "값 구간별 빈도 분포 (히스토그램)", params: ["reference_period", "bins"] },
    "correlation_scatter": { name: "두 시점 간 상관계수 (산점도)", params: ["reference_period", "compare_period"] },
    "compare_one_vs_all": { name: "특정 국가 vs 전체 평균·순위 (강조 막대)", params: ["reference_period", "target_entity"] }
};

document.addEventListener("DOMContentLoaded", () => {
    console.log("[PAGE] 페이지 로드 완료");
    initUploadEvents();
    initActionEvents();
});

// -------------------------------------------------------------
// 1. 파일 업로드 및 드래그앤드롭 이벤트
// -------------------------------------------------------------
function initUploadEvents() {
    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("fileInput");
    const browseBtn = document.getElementById("browseBtn");
    const selectedFileName = document.getElementById("selectedFileName");
    const inspectBtn = document.getElementById("inspectBtn");

    browseBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        fileInput.click();
    });

    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFileSelection(e.target.files[0]);
        }
    });

    function handleFileSelection(file) {
        if (!file.name.endsWith(".csv")) {
            alert("CSV 파일(.csv)만 업로드할 수 있습니다.");
            return;
        }
        selectedFile = file;
        const sizeKb = (file.size / 1024).toFixed(1);
        selectedFileName.textContent = `선택된 파일: ${file.name} (${sizeKb} KB)`;
        inspectBtn.disabled = false;
        console.log(`[UPLOAD] 파일 선택 (${file.name}, ${file.size} bytes)`);
    }
}

// -------------------------------------------------------------
// 2. 주요 버튼 액션 이벤트
// -------------------------------------------------------------
function initActionEvents() {
    const inspectBtn = document.getElementById("inspectBtn");
    const suggestBtn = document.getElementById("suggestBtn");
    const runToolBtn = document.getElementById("runToolBtn");
    const explainBtn = document.getElementById("explainBtn");

    inspectBtn.addEventListener("click", handleInspect);
    suggestBtn.addEventListener("click", handleSuggest);
    runToolBtn.addEventListener("click", handleRunTool);
    explainBtn.addEventListener("click", handleExplain);

    // Q&A 추천 질문 칩 클릭 이벤트 바인딩
    document.querySelectorAll(".chip-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const question = btn.getAttribute("data-q");
            if (question) {
                sendFollowUpQuestion(question);
            }
        });
    });

    // Q&A 수동 입력창 이벤트
    const chatInput = document.getElementById("chatInput");
    const chatSendBtn = document.getElementById("chatSendBtn");

    if (chatSendBtn && chatInput) {
        chatSendBtn.addEventListener("click", () => {
            const q = chatInput.value.trim();
            if (q) {
                chatInput.value = "";
                sendFollowUpQuestion(q);
            }
        });

        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                const q = chatInput.value.trim();
                if (q) {
                    chatInput.value = "";
                    sendFollowUpQuestion(q);
                }
            }
        });
    }
}


// -------------------------------------------------------------
// 3. /inspect 진단 요청
// -------------------------------------------------------------
async function handleInspect() {
    if (!selectedFile) return;

    const spinner = document.getElementById("inspectSpinner");
    const btn = document.getElementById("inspectBtn");

    try {
        btn.disabled = true;
        spinner.classList.remove("hidden");
        console.log("[INSPECT] 진단 요청 시작");

        const formData = new FormData();
        formData.append("file", selectedFile);

        const res = await fetch("/inspect", {
            method: "POST",
            body: formData
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "진단 실패");

        currentInspectData = data;
        console.log(`[INSPECT] 응답 수신 (행 수: ${data.row_count}, 열 수: ${data.column_count}, 경고 수: ${data.aggregates.aggregate_row_count}개 집계행 감지)`);

        renderInspectResults(data);

    } catch (err) {
        console.error(`[ERROR] 진단 중 오류 발생: ${err.message}`);
        alert(`진단 오류: ${err.message}`);
    } finally {
        btn.disabled = false;
        spinner.classList.add("hidden");
    }
}

function renderInspectResults(data) {
    const card = document.getElementById("inspectResultCard");
    const grid = document.getElementById("metricsGrid");
    const recYear = data.year_analysis?.recommended_year || "없음";

    grid.innerHTML = `
        <div class="metric-box">
            <div class="metric-label">총 데이터 행 수</div>
            <div class="metric-val">${data.row_count.toLocaleString()}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">총 열 개수</div>
            <div class="metric-val">${data.column_count}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">전체 결측률</div>
            <div class="metric-val">${data.quality.null_percentage}%</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">감지된 집계 행</div>
            <div class="metric-val" style="color: #b45309;">${data.aggregates.aggregate_row_count}건</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">순수 개별 국가</div>
            <div class="metric-val" style="color: #10b981;">${data.aggregates.individual_country_count}개국</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">권장 기준연도</div>
            <div class="metric-val" style="color: #2563eb;">${recYear}년</div>
        </div>
    `;

    // 미리보기 테이블 렌더링
    renderPreviewTable(data.columns, data.preview);
    card.classList.remove("hidden");
    card.scrollIntoView({ behavior: "smooth" });
}

function renderPreviewTable(columns, previewRows) {
    const table = document.getElementById("previewTable");
    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");

    // 컬럼이 너무 많으면 앞쪽 주요 컬럼 8개만 표시
    const displayCols = columns.slice(0, 8);

    thead.innerHTML = `<tr>${displayCols.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
    tbody.innerHTML = previewRows.map(row => `
        <tr>${displayCols.map(c => `<td>${escapeHtml(String(row[c] !== null && row[c] !== undefined ? row[c] : "-"))}</td>`).join("")}</tr>
    `).join("");
}

// -------------------------------------------------------------
// 4. /suggest AI 제안 요청
// -------------------------------------------------------------
async function handleSuggest() {
    if (!currentInspectData) return;

    const btn = document.getElementById("suggestBtn");
    const spinner = document.getElementById("suggestSpinner");

    try {
        btn.disabled = true;
        spinner.classList.remove("hidden");
        console.log("[SUGGEST] 제안 요청 시작");

        const res = await fetch("/suggest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(currentInspectData)
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "제안 요청 실패");

        const suggestions = data.suggestions || [];
        console.log(`[SUGGEST] 응답 수신 (제안 개수: ${suggestions.length}개)`);

        renderSuggestions(suggestions);

    } catch (err) {
        console.error(`[ERROR] 제안 중 오류 발생: ${err.message}`);
        alert(`제안 오류: ${err.message}`);
    } finally {
        btn.disabled = false;
        spinner.classList.add("hidden");
    }
}

function renderSuggestions(suggestions) {
    const card = document.getElementById("suggestionsCard");
    const grid = document.getElementById("suggestionsGrid");

    grid.innerHTML = suggestions.map((s, idx) => {
        const toolTitle = TOOL_CONFIG[s.tool]?.name || s.tool;
        return `
            <div class="suggestion-card">
                <div>
                    <span class="sugg-tool-badge">${escapeHtml(s.tool)}</span>
                    <h3 style="font-size: 1rem; margin-bottom: 0.5rem;">${escapeHtml(toolTitle)}</h3>
                    <p class="sugg-why">🎯 <strong>추천 이유:</strong> ${escapeHtml(s.why)}</p>
                    <p class="sugg-caution">⚠️ <strong>주의사항:</strong> ${escapeHtml(s.caution)}</p>
                </div>
                <button type="button" class="btn btn-primary" onclick="selectSuggestion(${idx})">
                    이 분석 선택 및 설정
                </button>
            </div>
        `;
    }).join("");

    window._loadedSuggestions = suggestions;
    card.classList.remove("hidden");
    card.scrollIntoView({ behavior: "smooth" });
}

window.selectSuggestion = function(idx) {
    const sugg = window._loadedSuggestions[idx];
    if (!sugg) return;
    openToolExecution(sugg.tool, sugg.params, sugg.why);
};

// -------------------------------------------------------------
// 5. 도구 파라미터 제어 폼 및 실행
// -------------------------------------------------------------
function openToolExecution(toolName, initialParams = {}, reason = "") {
    currentSelectedTool = toolName;
    const card = document.getElementById("toolExecCard");
    const nameEl = document.getElementById("currentToolName");
    const descEl = document.getElementById("currentToolDesc");
    const formEl = document.getElementById("paramsForm");

    const toolMeta = TOOL_CONFIG[toolName] || { name: toolName, params: [] };
    nameEl.textContent = toolName;
    descEl.textContent = `${toolMeta.name} ${reason ? `— (${reason})` : ""}`;

    const defaultYear = initialParams.reference_period || currentInspectData?.year_analysis?.recommended_year || "2024";

    let fieldsHtml = "";
    // 기준 시점 (reference_period)
    if (["describe_numeric", "top_bottom_n", "group_summary", "change_rate", "distribution", "correlation_scatter", "compare_one_vs_all"].includes(toolName)) {
        fieldsHtml += `
            <div class="param-group">
                <label>기준 시점 (reference_period) *필수</label>
                <input type="text" id="param_reference_period" value="${escapeHtml(defaultYear)}" placeholder="예: 2024">
            </div>
        `;
    }

    // N 개수
    if (["top_bottom_n", "change_rate"].includes(toolName)) {
        fieldsHtml += `
            <div class="param-group">
                <label>상위/하위 표시 개수 (N)</label>
                <input type="number" id="param_n" value="${initialParams.n || 10}" min="3" max="50">
            </div>
        `;
    }

    // 비교 연도 (base_period / compare_period)
    if (["change_rate", "correlation_scatter"].includes(toolName)) {
        const baseYear = initialParams.base_period || initialParams.compare_period || "2014";
        fieldsHtml += `
            <div class="param-group">
                <label>비교 대상 연도 (과거 시점)</label>
                <input type="text" id="param_base_period" value="${escapeHtml(baseYear)}" placeholder="예: 2014">
            </div>
        `;
    }

    // 그룹 컬럼
    if (toolName === "group_summary") {
        fieldsHtml += `
            <div class="param-group">
                <label>그룹화 기준 열</label>
                <select id="param_group_column">
                    <option value="Region" selected>Region (대륙별)</option>
                    <option value="IncomeGroup">IncomeGroup (소득수준별)</option>
                </select>
            </div>
        `;
    }

    // 히스토그램 bins
    if (toolName === "distribution") {
        fieldsHtml += `
            <div class="param-group">
                <label>구간 개수 (Bins)</label>
                <input type="number" id="param_bins" value="${initialParams.bins || 10}" min="3" max="30">
            </div>
        `;
    }

    // 대상 국가 (compare_one_vs_all)
    if (toolName === "compare_one_vs_all") {
        fieldsHtml += `
            <div class="param-group">
                <label>비교 대상 국가명</label>
                <input type="text" id="param_target_entity" value="${escapeHtml(initialParams.target_entity || 'Korea, Rep.')}" placeholder="예: Korea, Rep.">
            </div>
        `;
    }

    // 집계 행 제외 체크박스
    fieldsHtml += `
        <div class="param-group" style="justify-content: flex-end;">
            <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="checkbox" id="param_exclude_aggregates" checked>
                <span>통계 왜곡 방지: 집계 행(World, 소득군 등) 제외</span>
            </label>
        </div>
    `;

    formEl.innerHTML = fieldsHtml;
    card.classList.remove("hidden");
    card.scrollIntoView({ behavior: "smooth" });
}

// -------------------------------------------------------------
// 6. /run 도구 실행 및 Chart.js 시각화
// -------------------------------------------------------------
async function handleRunTool() {
    if (!currentSelectedTool) return;

    const btn = document.getElementById("runToolBtn");
    const spinner = document.getElementById("runSpinner");

    // 파라미터 수집
    const params = {};
    const refInput = document.getElementById("param_reference_period");
    if (refInput) params.reference_period = refInput.value.trim();

    const nInput = document.getElementById("param_n");
    if (nInput) params.n = parseInt(nInput.value, 10);

    const baseInput = document.getElementById("param_base_period");
    if (baseInput) {
        params.base_period = baseInput.value.trim();
        params.compare_period = baseInput.value.trim();
    }

    const groupInput = document.getElementById("param_group_column");
    if (groupInput) params.group_column = groupInput.value;

    const binsInput = document.getElementById("param_bins");
    if (binsInput) params.bins = parseInt(binsInput.value, 10);

    const targetInput = document.getElementById("param_target_entity");
    if (targetInput) params.target_entity = targetInput.value.trim();

    const aggInput = document.getElementById("param_exclude_aggregates");
    if (aggInput) params.exclude_aggregates = aggInput.checked;

    try {
        btn.disabled = true;
        spinner.classList.remove("hidden");
        console.log(`[RUN] 도구 실행 시작 (${currentSelectedTool}, 기준시점: ${params.reference_period || '전체'})`);

        const res = await fetch("/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tool: currentSelectedTool,
                params: params
            })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "실행 오류");

        currentRunResult = data;
        console.log(`[RUN] 결과 수신: 사용 행 수 ${data.used_rows}건, 제외 행 수 ${data.excluded_rows}건`);

        renderChartAndResults(data);

    } catch (err) {
        console.error(`[ERROR] 도구 실행 중 오류: ${err.message}`);
        alert(`실행 오류: ${err.message}`);
    } finally {
        btn.disabled = false;
        spinner.classList.add("hidden");
    }
}

function renderChartAndResults(data) {
    const card = document.getElementById("chartCard");
    const banner = document.getElementById("transparencyBanner");
    const cautionsBox = document.getElementById("cautionsBox");

    // 투명성 배너
    banner.innerHTML = `
        <div><strong>⏱️ 기준 시점:</strong> ${escapeHtml(String(data.reference_period))}</div>
        <div><strong>✅ 계산에 사용된 행:</strong> ${data.used_rows.toLocaleString()}건</div>
        <div><strong>❌ 제외된 행:</strong> ${data.excluded_rows.toLocaleString()}건 (${escapeHtml(data.excluded_reason)})</div>
    `;

    // 주의사항
    if (data.cautions && data.cautions.length > 0) {
        cautionsBox.innerHTML = `<strong>⚠️ 주의사항:</strong> ` + data.cautions.map(c => `<div>• ${escapeHtml(c)}</div>`).join("");
        cautionsBox.classList.remove("hidden");
    } else {
        cautionsBox.classList.add("hidden");
    }

    // Chart.js 시각화 렌더링
    renderChart(data.result);

    card.classList.remove("hidden");
    card.scrollIntoView({ behavior: "smooth" });
}

function renderChart(result) {
    const ctx = document.getElementById("analysisChart").getContext("2d");

    if (activeChartInstance) {
        activeChartInstance.destroy();
    }

    const chartType = result.chart_type || "bar";
    let config = null;

    if (chartType === "horizontalBar") {
        const topItems = result.top_n || [];
        config = {
            type: "bar",
            data: {
                labels: topItems.map(d => d.label),
                datasets: [{
                    label: `상위 순위 (${result.reference_period}년)`,
                    data: topItems.map(d => d.value),
                    backgroundColor: "#3b82f6"
                }]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false
            }
        };
    } else if (chartType === "line") {
        config = {
            type: "line",
            data: {
                labels: result.labels,
                datasets: result.datasets.map((ds, i) => ({
                    label: ds.label,
                    data: ds.data,
                    borderColor: ["#2563eb", "#7c3aed", "#10b981", "#f59e0b"][i % 4],
                    fill: false,
                    tension: 0.1
                }))
            },
            options: { responsive: true, maintainAspectRatio: false }
        };
    } else if (chartType === "scatter") {
        config = {
            type: "scatter",
            data: {
                datasets: [{
                    label: `${result.x_label} vs ${result.y_label}`,
                    data: (result.points || []).map(p => ({ x: p.x, y: p.y })),
                    backgroundColor: "#7c3aed"
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { title: { display: true, text: result.x_label } },
                    y: { title: { display: true, text: result.y_label } }
                }
            }
        };
    } else {
        // 일반 막대 차트 (group_summary, distribution, compare_one_vs_all 등)
        config = {
            type: "bar",
            data: {
                labels: result.labels || [],
                datasets: (result.datasets && result.datasets.length > 0) ? result.datasets.map(ds => ({
                    label: ds.label,
                    data: ds.data,
                    backgroundColor: "#3b82f6"
                })) : [{
                    label: "수치",
                    data: [],
                    backgroundColor: "#3b82f6"
                }]
            },
            options: { responsive: true, maintainAspectRatio: false }
        };
    }

    activeChartInstance = new Chart(ctx, config);
    console.log(`[CHART] 차트 렌더 완료 (${chartType})`);
}

// -------------------------------------------------------------
// 7. /explain AI 해석 보고서 요청
// -------------------------------------------------------------
async function handleExplain() {
    if (!currentRunResult) {
        alert("먼저 분석 도구를 실행(/run)해 주세요.");
        return;
    }

    const btn = document.getElementById("explainBtn");
    const spinner = document.getElementById("explainSpinner");
    const mode = document.querySelector('input[name="explainMode"]:checked').value;

    try {
        btn.disabled = true;
        spinner.classList.remove("hidden");
        console.log(`[EXPLAIN] 해석 요청 시작 (모드 ${mode})`);

        const res = await fetch("/explain", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mode: mode,
                run_result: currentRunResult
            })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "해석 요청 실패");

        console.log(`[EXPLAIN] 응답 수신 (모드: ${data.mode})`);
        renderExplainReport(data.mode, data.explanation);

    } catch (err) {
        console.error(`[ERROR] AI 해석 중 오류: ${err.message}`);
        alert(`해석 오류: ${err.message}`);
    } finally {
        btn.disabled = false;
        spinner.classList.add("hidden");
    }
}

function renderExplainReport(mode, markdownText) {
    const card = document.getElementById("reportCard");
    const badge = document.getElementById("reportModeBadge");
    const content = document.getElementById("reportContent");
    const chatCard = document.getElementById("chatCard");

    currentReportMarkdown = markdownText;
    badge.textContent = mode === "B" ? "모드 B (정식 리포트)" : "모드 A (비교용 요약)";
    badge.style.background = mode === "B" ? "#7c3aed" : "#64748b";

    // marked 라이브러리를 통한 마크다운 HTML 파싱
    content.innerHTML = typeof marked !== "undefined" ? marked.parse(markdownText) : markdownText;

    card.classList.remove("hidden");
    if (chatCard) {
        chatCard.classList.remove("hidden");
    }
    card.scrollIntoView({ behavior: "smooth" });
}

// -------------------------------------------------------------
// 8. 후속 Q&A 대화 전송 및 응답 처리
// -------------------------------------------------------------
async function sendFollowUpQuestion(question) {
    const messagesContainer = document.getElementById("chatMessages");
    const spinner = document.getElementById("chatSpinner");
    const sendBtn = document.getElementById("chatSendBtn");

    // 1. 사용자 메시지 버블 추가
    const userMsgEl = document.createElement("div");
    userMsgEl.className = "chat-msg user-msg";
    userMsgEl.innerHTML = `<div class="msg-content">${escapeHtml(question)}</div>`;
    messagesContainer.appendChild(userMsgEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    // 히스토리 기록
    chatHistory.push({ role: "user", content: question });

    // 2. AI 로딩 상태 표시
    if (sendBtn) sendBtn.disabled = true;
    if (spinner) spinner.classList.remove("hidden");

    try {
        console.log(`[CHAT] 후속 질문 전송: "${question}"`);
        const res = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: question,
                chat_history: chatHistory,
                report_context: currentReportMarkdown,
                run_result: currentRunResult
            })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "답변 수신 실패");

        const aiAnswer = data.answer || "";
        chatHistory.push({ role: "model", content: aiAnswer });

        // 3. AI 답변 메시지 버블 추가
        const aiMsgEl = document.createElement("div");
        aiMsgEl.className = "chat-msg ai-msg";
        const parsedContent = typeof marked !== "undefined" ? marked.parse(aiAnswer) : escapeHtml(aiAnswer);
        aiMsgEl.innerHTML = `
            <div class="msg-avatar">🤖</div>
            <div class="msg-content">${parsedContent}</div>
        `;
        messagesContainer.appendChild(aiMsgEl);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        console.log("[CHAT] 후속 질문 답변 완료");

    } catch (err) {
        console.error(`[ERROR] 후속 질문 처리 중 오류: ${err.message}`);
        const errMsgEl = document.createElement("div");
        errMsgEl.className = "chat-msg ai-msg";
        errMsgEl.innerHTML = `
            <div class="msg-avatar">⚠️</div>
            <div class="msg-content" style="color: #ef4444;">답변 생성 중 오류가 발생했습니다: ${escapeHtml(err.message)}</div>
        `;
        messagesContainer.appendChild(errMsgEl);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    } finally {
        if (sendBtn) sendBtn.disabled = false;
        if (spinner) spinner.classList.add("hidden");
    }
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

