import os
import logging
import random
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─────────────────────────────
# ✅ 로깅 설정
# ─────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("uvicorn")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# ─────────────────────────────
# ✅ [Mock DB] 데이터
# ─────────────────────────────
ALLOWED_USERS_DB = ["admin", "test", "samsung", "engineer", "user1"]
VERIFICATION_CODES = {}
REGISTERED_USERS = {"admin": "1234"}

# 더미 문서 풀 (랜덤 추출용)
DUMMY_DOCS_POOL = [
    {"file": "24년_3라인_설비이상_보고서.pdf", "path": "\\\\NAS\\Line3\\Report_2403.pdf", "grade": "B"},
    {"file": "연신설비_유지보수_매뉴얼_v2.docx", "path": "\\\\NAS\\Manual\\Stretching_v2.docx", "grade": "A"},
    {"file": "23년_하반기_안전교육_자료.pptx", "path": "\\\\NAS\\Safety\\Edu_2023H2.pptx", "grade": "C"},
    {"file": "냉각수_펌프_교체_이력.xlsx", "path": "\\\\NAS\\Maintenance\\Pump_Log.xlsx", "grade": "B"},
    {"file": "클린룸_미세먼지_측정값.csv", "path": "\\\\NAS\\Env\\Dust_2024.csv", "grade": "B"},
    {"file": "공정_수율_분석_1분기.pdf", "path": "\\\\NAS\\Yield\\Q1_Analysis.pdf", "grade": "A"},
    {"file": "신규_장비_입고_리스트.xlsx", "path": "\\\\NAS\\Asset\\New_Equipment.xlsx", "grade": "C"},
]

# ─────────────────────────────
# ✅ 데이터 모델
# ─────────────────────────────
class AuthRequest(BaseModel):
    user_id: str

class RegisterRequest(BaseModel):
    user_id: str
    code: str
    password: str

class LoginRequest(BaseModel):
    user_id: str
    password: str

# ─────────────────────────────
# ✅ 메인 페이지
# ─────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ─────────────────────────────
# ✅ [API] 인증 로직 (기존 동일)
# ─────────────────────────────
@app.post("/auth/request-code")
async def request_code(req: AuthRequest):
    user_id = req.user_id.strip()
    if user_id not in ALLOWED_USERS_DB:
        return JSONResponse(status_code=400, content={"error": "❌ 명단에 없는 아이디입니다."})
    if user_id in REGISTERED_USERS and user_id != "admin":
        return JSONResponse(status_code=400, content={"error": "⚠️ 이미 가입된 아이디입니다."})

    code = str(random.randint(100000, 999999))
    VERIFICATION_CODES[user_id] = code
    print(f"\n{'='*50}\n📧 [메일 발송] 수신자: {user_id}@cnhxo.com\n🔑 인증 코드: [{code}]\n{'='*50}\n")
    return {"message": "인증 코드가 발송되었습니다."}

@app.post("/auth/register")
async def register_user(req: RegisterRequest):
    user_id = req.user_id.strip()
    saved_code = VERIFICATION_CODES.get(user_id)
    if not saved_code or saved_code != req.code:
        return JSONResponse(status_code=400, content={"error": "❌ 인증 코드가 틀렸습니다."})
    
    REGISTERED_USERS[user_id] = req.password
    del VERIFICATION_CODES[user_id]
    return {"message": "가입 완료!"}

@app.post("/auth/login")
async def login(req: LoginRequest):
    user_id = req.user_id.strip()
    if user_id in REGISTERED_USERS and REGISTERED_USERS[user_id] == req.password:
        return {"success": True}
    return {"success": False, "message": "아이디 또는 비밀번호 오류"}

# ─────────────────────────────
# ✅ [API] 검색 (랜덤 문서 반환)
# ─────────────────────────────
@app.post("/search/documents")
async def document_search(request: Request):
    data = await request.json()
    question = data.get('question', '')
    
    # 2~4개의 랜덤 문서 추출 (질문마다 결과가 달라짐을 보여주기 위함)
    selected_docs = random.sample(DUMMY_DOCS_POOL, k=random.randint(2, 4))
    
    # 문서 포맷팅
    formatted_docs = []
    for doc in selected_docs:
        formatted_docs.append({
            "file_name": doc['file'],
            "date": "2024-05-20", # 예시 날짜
            "path": doc['path'],
            "grade": doc['grade'],
            "accuracy": f"{random.randint(85, 99)}.{random.randint(0,9)}%"
        })

    # 질문에 따라 약간 다른 답변 (더미)
    llm_answer = f"'{question}'에 대한 분석 결과입니다.\n\n해당 설비의 주요 이슈는 3라인 냉각 계통 압력 저하로 확인됩니다. 관련된 유지보수 매뉴얼과 최근 3개월간의 점검 리스트를 우측 문서 패널에서 확인하실 수 있습니다.\n\n추가적으로 궁금한 사항이 있다면 질문해 주세요."

    return {
        "result_count": len(formatted_docs),
        "llm_response": llm_answer,
        "documents": formatted_docs
    }

@app.get("/history/list")
async def get_history():
    # 사이드바 초기 더미 데이터
    return {"history": []}
