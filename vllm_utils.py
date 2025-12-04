import requests
import re

# ✅ vLLM API 서버 (Qwen32B 기반)
VLLM_API_URL = "http://localhost:8000/v1/completions"  # ← 실제 포트 확인 필요
MODEL_ID = "/model"  # 도커 내 Qwen3-32B 경로 (vLLM 기본값)

# ✅ 시스템 프롬프트 (think 차단 + 한국어 응답 고정)
SYSTEM_PROMPT = """
당신은 한국어로 대화하는 전문 AI 어시스턴트입니다.
- 모든 답변은 자연스러운 한국어로 작성하세요.
- 필요할 때 영어 기술 용어(GPU, Docker, API 등)는 그대로 사용해도 됩니다.
- <think>나 reasoning 등의 내부 사고 과정을 출력하지 마세요.
- 그러나 사용자가 요청한 답이나 문장, 목록, 요약은 반드시 출력해야 합니다.
"""


# ✅ 1️⃣ vLLM API 호출 함수
def call_vllm(prompt, max_tokens=256, stop=None):
    try:
        # 🔹 요청 JSON 구성
        payload = {
            "model": MODEL_ID,
            "prompt": prompt.strip(),
            "max_tokens": max_tokens,
            "temperature": 0.4,
        }
        if stop:
            payload["stop"] = stop

        response = requests.post(
            VLLM_API_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60
        )

        response.raise_for_status()
        result = response.json()

        # 🔹 LLM 응답 추출
        choices = result.get("choices", [])
        if choices and "text" in choices[0]:
            text = choices[0].get("text", "").strip()
            # ✅ think / system / reasoning 필터링
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            text = re.sub(r"(?i)(reasoning|analysis|step[- ]?by[- ]?step).*", "", text)
            return text.strip()

        return "[⚠️ LLM 응답에 텍스트 없음]"

    except requests.RequestException as e:
        print(f"[❌ vLLM 호출 실패]: {e}")
        return "[❌ LLM 서버 연결 실패]"

# ✅ 2️⃣ 문서 검색용 키워드 생성 함수
def call_vllm_generate_search_condition(user_question):
    prompt = f"""
너는 한국어 문서를 검색하기 위한 키워드 생성 전문가야.
다음 규칙을 철저히 지켜서 쉼표(,)로 구분된 핵심 단어만 출력해.
설명, 문장, 불릿, <think> 같은 내부 문장은 절대 쓰면 안 돼.

규칙:
1. 연도가 포함되면 반드시 숫자 4자리로 포함 (예: "23년도" → "2023").
2. 월, 일 단위는 반드시 숫자만 포함 (예: "1월" → "1", "12월" → "12", "15일" → "15").
3. **붙어 있는 복합 명사(예: "설비기술그룹", "품질보증팀", "공정관리파트")는 절대 분리하지 말 것.**
4. 띄어쓰기 기준으로 단어를 자르지 말고, 실제 의미 단위(명사 단어)를 그대로 유지.
5. 단어 사이에는 쉼표(,)만 사용하고, 공백이나 설명을 추가하지 말 것.
6. 특수문자, 따옴표, 마침표, 개행, HTML 태그는 금지.
7. "키워드:"나 불필요한 접두어/접미어 없이 키워드만 출력.

예시:
- 입력: "2024년 1월 설비기술그룹 활동 일지"
  출력: 2024,1,설비기술그룹,활동,일지
- 입력: "2023년 3월 15일 고장 이력"
  출력: 2023,3,15,고장,이력
- 입력: "설비고장 이력"
  출력: 설비고장,이력

질문: {user_question}

키워드:
"""
    return call_vllm(prompt, max_tokens=64, stop=["\n"])


# ✅ 3️⃣ 키워드 후처리
def clean_llm_keywords(raw_text: str) -> list:
    first_line = raw_text.strip().split("\n")[0]
    cleaned = re.sub(r"<[^>]+>", "", first_line)
    cleaned = re.sub(r"(?i)(키워드|질문)\s*:.*", "", cleaned)
    cleaned = re.sub(r"[\r\n\t]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # ✅ think나 오류 메시지 제거
    if "LLM 서버 연결 실패" in cleaned or "think" in cleaned.lower():
        return []
    return [kw.strip() for kw in cleaned.split(",") if kw.strip()]

# ✅ 4️⃣ 기사 요약 함수
def call_vllm_summarize_article(article_text, user_question=None):
    cleaned_text = clean_article_text(article_text)

    # ✅ 1️⃣ 내용 유효성 검사 (파일명/확장자/너무 짧은 본문 등)
    if not cleaned_text.strip():
        return "내용없음"
    if re.match(r"^[\w\W]*\.(pptx|xlsx|docx|pdf)[\w\W]*$", cleaned_text):
        return "내용없음"
    if len(cleaned_text) < 30:  # 본문이 너무 짧은 경우 (예: 파일명 리스트 등)
        return "내용없음"

    # ✅ 2️⃣ 요약 프롬프트
    prompt = f"""
다음은 기술 문서 또는 기록표입니다.
핵심 내용을 3문장 이내로 간결하게 정리하세요.

조건:
- "요약"이라는 단어는 사용하지 마세요.
- 동일한 사실이나 숫자를 반복하지 마세요.
- 반드시 한국어로 자연스럽게 작성하세요.
- 본문이 비어 있거나 의미가 없으면 "내용없음"이라고만 대답하세요.

[본문]
{cleaned_text}
"""
    raw_summary = call_vllm(prompt, max_tokens=512)
    return clean_sentences_preserve_meaning(raw_summary)


# ✅ 5️⃣ 문장 정제
def clean_sentences_preserve_meaning(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[\r\n\t]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ✅ 6️⃣ 본문 정제
def clean_article_text(text: str) -> str:
    text = text.replace("\n", " ").replace("\r", " ")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = re.sub(r"\([^)]{0,30}\)", "", text)
    text = re.sub(r"[•★☆▶▲▼→※]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
