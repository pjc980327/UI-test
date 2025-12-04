// ✅ 날짜 포맷 함수 (YYYY-MM-DD → YYYY년 M월 D일)
function formatDateKorean(dateStr) {
    if (!dateStr) return "";
    const parts = dateStr.split("-");
    if (parts.length !== 3) return dateStr;

    const year = parts[0];
    const month = String(parseInt(parts[1], 10));
    const day = String(parseInt(parts[2], 10));

    return `${year}년 ${month}월 ${day}일`;
}

function toSortableDateNum(dateStr) {
    if (!dateStr) return 0;
    let digits = dateStr.replace(/\D/g, "");
    if (digits.length === 6) {
        const year = digits.slice(0, 4);
        const month = digits.slice(4, 5).padStart(2, "0");
        const day = digits.slice(5).padStart(2, "0");
        digits = year + month + day;
    } else if (digits.length === 7) {
        const year = digits.slice(0, 4);
        const month = digits.slice(4, 5).padStart(2, "0");
        const day = digits.slice(5).padStart(2, "0");
        digits = year + month + day;
    }
    return digits.length >= 8 ? parseInt(digits.slice(0, 8), 10) : 0;
}


function copyPath(path) {
    // path가 undefined/null일 때 방어
    if (!path) {
        showToast("❌ 복사할 경로가 없습니다.");
        return;
    }
    navigator.clipboard.writeText(path)
        .then(() => showToast("📋 경로가 복사되었습니다!"))
        .catch(err => {
            console.error("복사 실패:", err);
            showToast("❌ 복사 실패");
        });
}

function showToast(msg) {
    let toast = document.getElementById("toast");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "toast";
        toast.className = "toast";
        Object.assign(toast.style, {
            position: "fixed",
            top: "25%",                // 🔹 화면 상단에서 약 25% 지점
            left: "50%",
            transform: "translateX(-50%) translateY(-20px)",
            background: "rgba(0, 0, 0, 0.85)",
            color: "#fff",
            padding: "12px 24px",
            borderRadius: "10px",
            fontSize: "15px",
            fontWeight: "500",
            zIndex: "9999",
            opacity: "0",
            transition: "opacity 0.3s ease, transform 0.3s ease",
            pointerEvents: "none",
            boxShadow: "0 4px 10px rgba(0,0,0,0.25)"
        });
        document.body.appendChild(toast);
    }

    toast.textContent = msg;

    // 부드럽게 등장
    requestAnimationFrame(() => {
        toast.style.opacity = "1";
        toast.style.transform = "translateX(-50%) translateY(0)";
    });

    // 1.8초 뒤 부드럽게 사라짐
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(-50%) translateY(-20px)";
    }, 1800);
}






// ✅ 검색 함수
async function search() {
    const question = document.getElementById('questionInput').value;
    const resultDiv = document.getElementById('result');
    resultDiv.innerHTML = '⏳ 검색 중...';

    try {
        const response = await fetch("/search/documents", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question })
        });

        const data = await response.json();

        if (data.error) {
            resultDiv.innerHTML = `<p style="color:red;">❌ ${data.error}</p>`;
            return;
        }

        // 🔹 정확도 순으로 정렬
        data.documents.sort((a, b) => parseFloat(b.accuracy) - parseFloat(a.accuracy));

        let html = `<p>🔎 총 ${data.result_count}건 검색됨</p>`;

        for (const [index, doc] of data.documents.entries()) {
            const safeId = `summary_${index}`;

            html += `
            <div class="result-card">
                <div class="result-content">
                    <div class="result-title">📄 ${doc.file_name || "파일명 없음"}</div>
                    <div class="result-meta">
                        📅 ${formatDateKorean(doc.date)} | 🏷️ 보안 등급: ${doc.grade || "미지정"}
                    </div>
                    <div class="result-meta">
                        📁 경로: 
                        <span class="clickable-path" data-path="${doc.path}">
                            ${doc.path}
                        </span>
                    </div>
                            
           
                    <div class="result-accuracy">🎯 정확도: ${doc.accuracy}</div>

                   
                    <div id="${safeId}"></div>
                </div>
            </div>
        `;
        //    <div class="result-buttons">
        //                 <button 
        //                     data-content="${encodeURIComponent(JSON.stringify(doc))}" 
        //                     data-target="${safeId}" 
        //                     onclick="summarizeFromButton(this)">
        //                     요약보기
        //                 </button>
        //             </div>


        }

        resultDiv.innerHTML = html || "<p>검색 결과가 없습니다.</p>";

         document.querySelectorAll(".clickable-path").forEach(span => {
            span.addEventListener("click", () => {
                copyPath(span.dataset.path);
            });
        });
    } catch (err) {
        resultDiv.innerHTML = `<p style="color:red;">❌ 오류 발생: ${err.message}</p>`;
    }
}

// ✅ 버튼 클릭 시 요약 실행
function summarizeFromButton(button) {
    button.disabled = true;
    button.innerText = "요약 중...";
    button.style.opacity = "0.6";
    button.style.cursor = "not-allowed";

    const docData = JSON.parse(decodeURIComponent(button.dataset.content));
    const targetId = button.dataset.target;

    summarize(docData, targetId);
}

// ✅ 요약 요청 함수 데이터 전처리 정상화 후 재가동예정
/* async function summarize(docData, targetId) {
    const targetDiv = document.getElementById(targetId);
    targetDiv.className = "summary-box";
    targetDiv.innerText = "🧠 문서 내용 요약 중...";

    try {
        const response = await fetch("/summarize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                content: docData.file_name || "",
                question: document.getElementById('questionInput').value
            })
        });

        const data = await response.json();

        if (data.summary) {
            // ✅ 타자 효과 출력
            targetDiv.innerHTML = "📄 ";
            let i = 0;
            const text = data.summary;

            function typeWriter() {
                if (i < text.length) {
                    const char = text.charAt(i);
                    targetDiv.innerHTML += (char === " " ? "&nbsp;" : char);
                    i++;
                    setTimeout(typeWriter, 15);
                }
            }
            typeWriter();
        } else {
            targetDiv.innerText = "❌ 요약 실패 또는 본문 없음";
        }
    } catch (err) {
        targetDiv.innerText = `❌ 요약 중 오류: ${err.message}`;
    }
}*/

function summarize(docData, targetId) {
    alert("⚠️ 요약 기능은 현재 비활성화되어 있습니다.");
}

// ✅ HTML의 onclick 연결
window.search = search;
window.summarizeFromButton = summarizeFromButton;
