import os
import json
import logging
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from qdrant_utils import keyword_then_semantic_rerank
from vllm_utils import (
    call_vllm_generate_search_condition,
    clean_llm_keywords,
    call_vllm_summarize_article
)

# ─────────────────────────────
# ✅ 로깅 설정 (user_log 폴더)
# ─────────────────────────────
LOG_DIR = "user_log"
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f"search_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(message)s",
    encoding="utf-8"
)

# ─────────────────────────────
# ✅ FastAPI 기본 설정
# ─────────────────────────────
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─────────────────────────────
# ✅ 동시 접속자 추적
# ─────────────────────────────
active_connections = 0
lock = asyncio.Lock()

@app.middleware("http")
async def track_active_requests(request: Request, call_next):
    """
    모든 요청마다 동시 접속자 수를 콘솔에 출력하는 미들웨어.
    """
    global active_connections
    async with lock:
        active_connections += 1
        current = active_connections
    print(f"🌐 현재 동시 접속자 수: {current}")

    try:
        response = await call_next(request)
        return response
    finally:
        async with lock:
            active_connections -= 1
            print(f"🔻 요청 종료 → 현재 동시 접속자 수: {active_connections}")


# ─────────────────────────────
# ✅ 메인 페이지
# ─────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ─────────────────────────────
# ✅ 문서 검색 엔드포인트
# ─────────────────────────────
@app.post("/search/documents")
async def document_search(request: Request):
    data = await request.json()
    user_question = data.get("question")

    if not user_question:
        return {"error": "❌ 질문이 없습니다."}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"\n{'='*100}")
    logging.info(f"🕓 [{timestamp}] 문서 검색 요청")
    logging.info(f"{'='*100}")
    logging.info(f"📥 사용자 질문: {user_question}")

    # 🔹 1️⃣ vLLM을 이용한 키워드 생성
    raw_keywords = call_vllm_generate_search_condition(user_question)
    keywords = clean_llm_keywords(raw_keywords)

    logging.info(f"🔍 LLM 생성 키워드 (원본): {raw_keywords}")
    logging.info(f"✅ 정제된 키워드 리스트: {keywords}")

    # 🔹 2️⃣ Qdrant 검색 수행
    document_list = keyword_then_semantic_rerank(user_question, keywords, top_k=30)
    logging.info(f"📄 검색 결과 개수: {len(document_list)}")

    formatted_documents = []
    for idx, doc in enumerate(document_list, 1):
        file_name = doc.get("파일명", "")
        page = doc.get("페이지", "")
        grade = doc.get("보안등급", "")
        date = doc.get("날짜", "")
        path_str = doc.get("경로", "")
        score = doc.get("score", 0.0)

        formatted_documents.append({
            "doc_id": doc.get("문서ID", ""),
            "page": page,
            "file_name": file_name,
            "date": date,
            "path": path_str,
            "grade": grade,
            "accuracy": f"{round(score * 100, 2)}%",
        })

        # 🔹 콘솔에도 표시
      #  print(f"📄 [{idx}] {file_name} | {date} | {grade} | score={score:.4f}")

    # ─────────────────────────────
    # 📦 로그 본문 (모든 필드 포함)
    # ─────────────────────────────
    log_data = {
        "timestamp": timestamp,
        "user_question": user_question,
        "llm_keywords_raw": raw_keywords,
        "llm_keywords_clean": keywords,
        "result_count": len(formatted_documents),
        "documents": formatted_documents
    }

    logging.info(json.dumps(log_data, ensure_ascii=False, indent=2))
    logging.info(f"{'-'*100}\n")

    return {
        "result_count": len(formatted_documents),
        "documents": formatted_documents
    }


# ─────────────────────────────
# ✅ 본문 요약 엔드포인트
# ─────────────────────────────
@app.post("/summarize")
async def summarize_article(request: Request):
    data = await request.json()
    content = data.get("content", "")
    question = data.get("question", None)

    if not content:
        return {"error": "❌ 본문이 없습니다."}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"\n{'='*100}")
    logging.info(f"🧠 [{timestamp}] 요약 요청")
    logging.info(f"{'='*100}")
    logging.info(f"본문 길이: {len(content)}자")
    logging.info(f"질문: {question if question else '(없음)'}")

    summary = call_vllm_summarize_article(content, question)
    logging.info(f"요약 결과 일부: {summary[:200]}...")
    logging.info(f"{'-'*100}\n")

    return {"summary": summary}
