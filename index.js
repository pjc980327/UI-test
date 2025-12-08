console.log("✅ index.js Loaded");

let currentUser = null;
let timerInterval = null;
let timeLeft = 1200;
let isSidebarCollapsed = false;

// 현재 세션의 대화 내용 저장 [ {id, question, answer, docs, timestamp, sessionId}, ... ]
let currentSessionData = [];
let chatCounter = 0; // 질문 ID 생성용
let currentSessionId = Date.now(); // 🕒 현재 활성 세션의 고유 ID (Timestamp 기반)
let isHistoryLoaded = false; // 🚩 현재 세션이 히스토리에서 로드된 상태인지 추적
let isThinkingOrTyping = false; // 🚩 AI가 처리 중인지 확인하는 상태

// 세션을 저장할 Mock DB (실제는 서버/DB 사용)
let MOCK_HISTORY_DB = {}; 

// 🚩 [수정 강화] 컨트롤 상태 관리 함수: 입력창 비활성화/활성화 및 포커스 관리
function setControlsDisabled(disabled) {
    const input = document.getElementById('mainInput');
    const sendBtn = document.querySelector('.send-btn');
    isThinkingOrTyping = disabled;
    
    // ✅ CRITICAL: 입력 필드와 버튼의 disabled 속성을 명확히 설정
    input.disabled = disabled; 
    sendBtn.disabled = disabled; 
    
    // 스타일 변경 (비활성화 상태 시 시각적 피드백 제공)
    input.style.cursor = disabled ? 'not-allowed' : 'text';
    input.style.backgroundColor = disabled ? '#e0e0e0' : ''; // 👈 [강화] 비활성화 시 배경색 변경
    sendBtn.style.opacity = disabled ? '0.5' : '1';
    sendBtn.style.cursor = disabled ? 'not-allowed' : 'pointer';

    // ✅ 활성화 시 자동으로 입력 필드에 포커스 유지
    if (!disabled) {
        // 짧은 지연을 주어 포커스가 확실히 잡히도록 보장
        setTimeout(() => input.focus(), 10); 
    }
}

// ==========================================
// 1. 인증 및 기본 UI 로직 (기존과 동일/유사)
// ==========================================
function showSignup() {
    document.getElementById('login-box').classList.add('hidden');
    document.getElementById('signup-box').classList.remove('hidden');
}
function showLogin() {
    document.getElementById('signup-box').classList.add('hidden');
    document.getElementById('login-box').classList.remove('hidden');
}

async function checkLogin() {
    const id = document.getElementById('loginId').value;
    const pw = document.getElementById('loginPw').value;
    if (!id || !pw) return alert("정보를 입력하세요.");

    try {
        const res = await fetch("/auth/login", {
            method: "POST", headers: {"Content-Type":"application/json"},
            body: JSON.stringify({user_id: id, password: pw})
        });
        const data = await res.json();
        if (data.success) {
            currentUser = id;
            document.getElementById('auth-layer').classList.add('hidden');
            document.getElementById('main-app').classList.remove('hidden');
            document.getElementById('display-username').innerText = id;
            document.getElementById('full-email').innerText = id + "@cnhxo.com";
            startTimer();
            resetChat();
        } else {
            alert("❌ " + data.message);
        }
    } catch(e) { alert("서버 오류"); }
}

async function reqCode() {
    const id = document.getElementById('signupId').value;
    if(!id) return alert("아이디 입력 필요");
    try {
        const res = await fetch("/auth/request-code", {
            method: "POST", headers: {"Content-Type":"application/json"},
            body: JSON.stringify({user_id:id})
        });
        if(res.ok) { alert("인증코드 발송됨"); document.getElementById('verify-area').classList.remove('hidden'); }
        else alert("오류 발생");
    } catch(e) { alert("통신 오류"); }
}

async function doRegister() {
    const id = document.getElementById('signupId').value;
    const code = document.getElementById('verifyCode').value;
    const pw = document.getElementById('newPw').value;
    try {
        const res = await fetch("/auth/register", {
            method: "POST", headers: {"Content-Type":"application/json"},
            body: JSON.stringify({user_id:id, code, password:pw})
        });
        if(res.ok) { alert("가입 완료"); showLogin(); }
        else alert("가입 실패");
    } catch(e) { alert("통신 오류"); }
}

function startTimer() {
    timeLeft = 1200; updateTimer();
    if(timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        timeLeft--; updateTimer();
        if(timeLeft<=0) { alert("시간초과 로그아웃"); logout(); }
    }, 1000);
    window.addEventListener('mousemove', resetTimer);
    window.addEventListener('keydown', resetTimer);
}
function stopTimer() { clearInterval(timerInterval); window.removeEventListener('mousemove',resetTimer); window.removeEventListener('keydown',resetTimer); }
function resetTimer() { 
    timeLeft = 1200; updateTimer(); 
    // resetTimer가 호출되어도 타이핑 중이라면 컨트롤을 활성화시키지 않음.
    if (!isThinkingOrTyping) {
        setControlsDisabled(false);
    }
}
function updateTimer() {
    const m = Math.floor(timeLeft/60); const s = timeLeft%60;
    document.getElementById('timer').innerText = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}
function logout() {
    currentUser = null; stopTimer();
    document.getElementById('main-app').classList.add('hidden');
    document.getElementById('auth-layer').classList.remove('hidden');
    document.getElementById('loginId').value=""; document.getElementById('loginPw').value="";
    resetChat();
}

// ==========================================
// 2. 채팅 & 검색 로직
// ==========================================

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById('mainInput').addEventListener('keydown', (e) => {
        // ✅ [강화] 키다운 시에도 현재 AI 처리 중인지 확인
        if (e.key === 'Enter') {
            if (isThinkingOrTyping) {
                e.preventDefault(); // Enter 키 입력 자체를 막음
                return;
            }
            performSearch();
        }
    });
});

async function performSearch() {
    // 🚩 [1차 방어] 이미 처리 중이면 바로 종료
    if (isThinkingOrTyping) return; 

    const input = document.getElementById('mainInput');
    const query = input.value.trim();
    if(!query) return;
    
    input.value = ""; 
    
    // 2. 🚩 [핵심] 질문 접수 즉시 컨트롤 비활성화 (타이핑 완료 시까지 유지)
    setControlsDisabled(true); 
    
    const chatContainer = document.getElementById('chat-container');
    const welcome = document.getElementById('welcome-msg');
    if(welcome) welcome.remove();

    // 2. 질문 말풍선 추가
    const qId = chatCounter++;
    const now = new Date();
    const timeString = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

    const userBubble = document.createElement('div');
    userBubble.className = "chat-message user";
    userBubble.setAttribute('data-id', qId);
    userBubble.onclick = () => restoreDocs(qId);
    userBubble.innerHTML = `
        <div class="msg-label">User • ${timeString} (클릭하여 문서 보기)</div>
        <div class="msg-text">${query}</div>
    `;
    chatContainer.appendChild(userBubble);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // 3. 🚩 AI 답변 처리 중 모션 추가
    const thinkingBubbleId = `thinking-${qId}`;
    const thinkingBubble = document.createElement('div');
    thinkingBubble.className = "chat-message thinking";
    thinkingBubble.id = thinkingBubbleId;
    thinkingBubble.innerHTML = `
        <div class="typing-dots">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
        </div>
    `;
    chatContainer.appendChild(thinkingBubble);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // 4. 🚩 더미 지연 시간 설정 (1000ms ~ 5000ms)
    const dummyDelay = Math.floor(Math.random() * 4000) + 1000;
    
    let data;
    try {
        const [apiResponse] = await Promise.all([
            fetch("/search/documents", {
                method: "POST", headers: {"Content-Type":"application/json"},
                body: JSON.stringify({question: query})
            }).then(res => res.json()),
            new Promise(resolve => setTimeout(resolve, dummyDelay))
        ]);
        data = apiResponse;
        
    } catch(e) {
        console.error(e);
        const thinkingElement = document.getElementById(thinkingBubbleId);
        if (thinkingElement) thinkingElement.remove();
        
        const aiBubble = document.createElement('div');
        aiBubble.className = "chat-message ai";
        aiBubble.id = `ai-msg-${qId}`;
        aiBubble.innerHTML = `
            <div class="ai-header" style="color:#e74c3c;"><i class="fas fa-times-circle"></i> AI 답변 (오류)</div>
            <div class="ai-content">통신 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.</div>
        `;
        chatContainer.appendChild(aiBubble);
        setControlsDisabled(false); // 오류 시 컨트롤 활성화
        return;
    }
    
    // 6. 더미 지연 및 서버 요청 완료 후 모션 제거
    const thinkingElement = document.getElementById(thinkingBubbleId);
    if (thinkingElement) thinkingElement.remove();

    // 7. AI 답변 준비 (빈 상태로 추가)
    const aiBubble = document.createElement('div');
    aiBubble.className = "chat-message ai";
    aiBubble.id = `ai-msg-${qId}`;
    aiBubble.innerHTML = `
        <div class="ai-header"><i class="fas fa-star-of-life"></i> AI 답변</div>
        <div class="ai-content"><span class="cursor"></span></div>
    `;
    chatContainer.appendChild(aiBubble);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    
    // 8. 데이터 저장
    const sessionItem = {
        id: qId,
        question: query,
        answer: data.llm_response,
        docs: data.documents,
        timestamp: now,
        sessionId: currentSessionId
    };
    currentSessionData.push(sessionItem);

    // 9. 타이핑 효과 시작 (완료되면 setControlsDisabled(false) 호출)
    const contentDiv = aiBubble.querySelector('.ai-content');
    typeWriter(data.llm_response, contentDiv, 0);

    // 10. 문서 패널 업데이트 및 히스토리 갱신
    renderDocs(data.documents);
    if (currentSessionData.length === 1 && !isHistoryLoaded) {
        MOCK_HISTORY_DB[currentSessionId] = currentSessionData;
        addToSidebar(currentSessionData, currentSessionId);
    } else if (currentSessionData.length > 1 || isHistoryLoaded) {
        MOCK_HISTORY_DB[currentSessionId] = currentSessionData;
        updateSidebarItem(currentSessionId, currentSessionData);
    }
}

// ✅ [최종] 불규칙 타이핑 효과 + 완료 시 컨트롤 활성화
function typeWriter(text, element, index) { 
    if (index < text.length) {
        element.innerHTML = text.substring(0, index + 1) + '<span class="cursor"></span>';
        const randomDelay = Math.floor(Math.random() * 90) + 10;
        
        setTimeout(() => {
            typeWriter(text, element, index + 1);
            const container = document.getElementById('chat-container');
            container.scrollTop = container.scrollHeight;
        }, randomDelay);
    } else {
        // 🚩 [핵심] 타이핑 완료: 커서 제거 후 컨트롤 활성화
        element.innerHTML = text; // 커서 제거
        setControlsDisabled(false); 
    }
}

function renderDocs(docs) {
    const docDiv = document.getElementById('doc-results');
    if(!docs || docs.length === 0) {
        docDiv.innerHTML = "<p style='color:#888'>관련 문서가 없습니다.</p>";
        return;
    }

    let html = "";
    docs.forEach(doc => {
        html += `
        <div class="result-card">
            <div class="result-title">📄 ${doc.file_name}</div>
            <div class="result-meta">📅 ${doc.date} | 등급: ${doc.grade} | 정확도: ${doc.accuracy}</div>
            <div class="clickable-path" onclick="alert('경로 복사: ${doc.path.replace(/\\/g, '\\\\')}')">
                📂 ${doc.path}
            </div>
        </div>`;
    });
    docDiv.innerHTML = html;
}

function restoreDocs(qId) {
    const item = currentSessionData.find(d => d.id === qId);
    if(item) {
        renderDocs(item.docs);
        const docDiv = document.getElementById('doc-container');
        docDiv.style.opacity = '0.5';
        setTimeout(() => docDiv.style.opacity = '1', 200);
    }
}

// ==========================================
// 3. 새 채팅 & 히스토리 관리 로직 (자동 저장 로직 변경)
// ==========================================

function resetChat() {
    // 🚩 상태 초기화
    currentSessionData = [];
    chatCounter = 0;
    currentSessionId = Date.now();
    isHistoryLoaded = false;
    
    // UI 초기화
    document.getElementById('chat-container').innerHTML = `
        <div style="text-align:center; color:#999; margin-top:50px;" id="welcome-msg">
            <i class="fas fa-search" style="font-size:40px; margin-bottom:15px; color:#ddd;"></i><br>
            새로운 대화를 시작하세요.
        </div>`;
    document.getElementById('doc-results').innerHTML = `
        <div style="color:#888; font-size:14px; margin-top:10px;">
            질문을 입력해주세요.
        </div>`;
}

// ✅ [수정] "새 채팅" 버튼 클릭 시 동작 (자동 갱신/저장 포함)
function archiveCurrentChat() {
    // 🚩 [추가] 현재 활성 세션에 데이터가 있다면 무조건 저장/갱신
    if (currentSessionData.length > 0) {
        // 기존 세션을 MOCK_HISTORY_DB에 최종 업데이트
        MOCK_HISTORY_DB[currentSessionId] = currentSessionData;
        
        // isHistoryLoaded 상태와 관계없이 사이드바 아이템 갱신/추가
        // (isHistoryLoaded가 false이고 첫 질문 시에는 이미 performSearch에서 추가됨)
        // 이 로직은 주로 isHistoryLoaded=true인 상태에서 새 채팅을 누를 때 갱신 역할을 합니다.
        updateSidebarItem(currentSessionId, currentSessionData);
    }

    // 애니메이션 효과 (화면 축소)
    const workspace = document.getElementById('workspace');
    workspace.classList.add('shrink-animation');

    // 애니메이션 끝난 후 초기화
    setTimeout(() => {
        workspace.classList.remove('shrink-animation');
        resetChat();
    }, 800);
}

function addToSidebar(sessionData, sessionId) {
    if(!sessionData || sessionData.length === 0) return;

    const firstItem = sessionData[0];
    const lastItem = sessionData[sessionData.length - 1];
    
    const title = firstItem.question;
    const formatTime = (date) => date.toLocaleDateString() + " " + date.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
    const startTime = formatTime(firstItem.timestamp);
    const endTime = formatTime(lastItem.timestamp);
    const tooltipText = `시작: ${startTime}\n마지막: ${endTime}`;

    const listDiv = document.getElementById('history-list');
    
    // 이미 존재하는 항목인지 확인
    let div = document.getElementById(`history-item-${sessionId}`);
    if (div) {
        // 갱신: 툴팁과 제목 업데이트
        div.setAttribute('data-tooltip', tooltipText);
        div.querySelector('.item-title').innerText = title; 
        return; 
    }
    
    // 새 항목 생성
    div = document.createElement('div');
    div.className = "history-item";
    div.id = `history-item-${sessionId}`; 
    div.setAttribute('data-tooltip', tooltipText);
    div.onclick = () => loadHistorySession(sessionId); 

    // 휴지통 버튼 추가 (이전 HTML 수정본과 동일)
    div.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span class="item-content"><i class="far fa-comments"></i> <span class="item-title">${title}</span></span>
            <i class="fas fa-trash-alt delete-btn" onclick="deleteHistory(event, '${sessionId}')"></i>
        </div>
    `;

    listDiv.prepend(div);
}

function updateSidebarItem(sessionId, sessionData) {
    // 갱신 로직은 addToSidebar가 담당
    addToSidebar(sessionData, sessionId);
}


function deleteHistory(event, sessionId) { /* ... (기존과 동일) ... */
    event.stopPropagation(); 
    const itemToDelete = document.getElementById(`history-item-${sessionId}`);
    if (itemToDelete) {
        const confirmDelete = confirm("정말로 이 대화 기록을 삭제하시겠습니까?\n\n(참고: 이 기능은 프론트엔드 목업이므로 페이지 새로고침 시 복구될 수 있습니다.)");
        if (confirmDelete) {
            delete MOCK_HISTORY_DB[sessionId];
            itemToDelete.remove();
            if (currentSessionId.toString() === sessionId) {
                resetChat();
            }
            alert("✅ 기록이 삭제되었습니다.");
        }
    }
}


// ✅ [수정] 히스토리 클릭 시 로드 (이탈 시 자동 갱신 로직 추가)
function loadHistorySession(sessionId) {
    const sessionData = MOCK_HISTORY_DB[sessionId];
    if (!sessionData) return;
    
    // 🚩 현재 작업 중이던 세션이 있다면 MOCK_HISTORY_DB에 저장/갱신 (자동 저장)
    if (currentSessionData.length > 0 && currentSessionId.toString() !== sessionId) {
        MOCK_HISTORY_DB[currentSessionId] = currentSessionData;
        updateSidebarItem(currentSessionId, currentSessionData);
    }
    
    // 🚩 상태 설정
    currentSessionId = sessionId;
    isHistoryLoaded = true;
    currentSessionData = sessionData;
    
    const chatContainer = document.getElementById('chat-container');
    chatContainer.innerHTML = ""; 

    sessionData.forEach(item => {
        const timeString = item.timestamp.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        const userBubble = document.createElement('div');
        userBubble.className = "chat-message user";
        userBubble.onclick = () => restoreDocs(item.id);
        userBubble.innerHTML = `<div class="msg-label">User • ${timeString}</div><div class="msg-text">${item.question}</div>`;
        chatContainer.appendChild(userBubble);

        const aiBubble = document.createElement('div');
        aiBubble.className = "chat-message ai";
        aiBubble.innerHTML = `<div class="ai-header"><i class="fas fa-star-of-life"></i> AI 답변</div><div class="ai-content">${item.answer}</div>`;
        chatContainer.appendChild(aiBubble);
    });

    if(sessionData.length > 0) {
        renderDocs(sessionData[sessionData.length-1].docs);
    }
    chatContainer.scrollTop = chatContainer.scrollHeight;
    setControlsDisabled(false); // 로드 완료 시 컨트롤 활성화
}


// UI 유틸리티
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    isSidebarCollapsed = !isSidebarCollapsed;
    sidebar.classList.toggle('collapsed', isSidebarCollapsed);
}

function toggleTheme() {
    document.body.classList.toggle('dark');
    const icon = document.getElementById('theme-icon');
    icon.className = document.body.classList.contains('dark') ? "fas fa-sun" : "fas fa-moon";
}

function toggleUserMenu() {
    document.getElementById('user-dropdown').classList.toggle('active');
}


// 전역 할당
window.checkLogin = checkLogin;
window.showSignup = showSignup;
window.showLogin = showLogin;
window.reqCode = reqCode;
window.doRegister = doRegister;
window.logout = logout;
window.toggleSidebar = toggleSidebar;
window.toggleTheme = toggleTheme;
window.toggleUserMenu = toggleUserMenu;
window.performSearch = performSearch;
window.archiveCurrentChat = archiveCurrentChat;
window.deleteHistory = deleteHistory; // ✅ 삭제 함수 전역 등록
