import gc
import torch
import re
from typing import List, Tuple, Dict, Set
from concurrent.futures import ThreadPoolExecutor
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import MatchValue, MatchAny, Filter, FieldCondition
from sklearn.metrics.pairwise import cosine_similarity


# ✅ Qdrant 설정
qdrant_client = QdrantClient(host="localhost", port=6333)
collection_name = "docs_test_all"

# ✅ SentenceTransformer (KURE_v1)
model = SentenceTransformer("/home/hmo/Embedding_Models/KURE_v1")


def encode_and_clear(texts, **kwargs):
    vectors = model.encode(texts, **kwargs)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        gc.collect()
    return vectors


# ✅ 공통 점수 보정 함수 (날짜 여부 무관)
def apply_keyword_bonus(results, text_keywords, top_k):
    """검색 결과에 키워드 교집합 기반 점수 보너스 적용"""
    reranked = []
    for hit in results:
        payload = hit.payload
        score = float(hit.score)
        doc_keywords = payload.get("keywords", [])

        matched_keywords = []
        for kw in text_keywords:
            if kw in (payload.get("sFileName") or "") or kw in doc_keywords:
                matched_keywords.append(kw)

        # ✅ 교집합 보너스 (0.05, 0.04, 0.03, ...)
        for i, _ in enumerate(matched_keywords):
            score += max(0.05 - i * 0.01, 0.01)

        if matched_keywords:
            print(f"\n📄 {payload.get('sFileName', '')}")
            print(f"   🔹 문서 keywords: {doc_keywords}")
            print(f"   🔹 매칭: {matched_keywords} → 최종 score={round(score,5)}")

        reranked.append({
            "id": hit.id,
            "문서ID": payload.get("doc_id", ""),
            "파일명": payload.get("sFileName", ""),
            "날짜": f"{payload.get('year', '----')}-{payload.get('month', '--')}-{payload.get('day', '--')}",
            "경로": payload.get("sFilePath", ""),
            "보안등급": payload.get("sGrade", ""),
            "score": round(score, 5),
        })

    reranked.sort(key=lambda x: x["score"], reverse=True)
    return reranked[:top_k]


# ✅ 단일 키워드 검색
def keyword_search_single(keyword: str, top_k: int = 30) -> Tuple[Set, Dict, str]:
    keyword_type = "none"
    query_filter = None

    if re.fullmatch(r"\d{4}", keyword):  # 연도
        keyword_type = "year"
        query_filter = Filter(must=[FieldCondition(key="year", match=MatchValue(value=int(keyword)))])
    elif keyword.isdigit() and 1 <= int(keyword) <= 12:  # 월
        keyword_type = "month"
        query_filter = Filter(must=[FieldCondition(key="month", match=MatchValue(value=int(keyword)))])
    elif keyword.isdigit() and 1 <= int(keyword) <= 31:  # 일
        keyword_type = "day"
        query_filter = Filter(must=[FieldCondition(key="day", match=MatchValue(value=int(keyword)))])
    else:  # 텍스트 키워드
        keyword_type = "text"
        query_filter = Filter(should=[
            FieldCondition(key="sFileName", match=MatchValue(value=keyword)),
            FieldCondition(key="keywords", match=MatchAny(any=[keyword])),
        ])

    result = qdrant_client.query_points(
        collection_name=collection_name,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
        with_vectors=True,
    )

    ids = {p.id for p in result.points}
    payloads = {p.id: {"payload": p.payload, "vector": p.vector} for p in result.points}
    return ids, payloads, keyword_type


# ✅ 병렬 키워드 검색
def search_qdrant_metadata_parallel(keywords: List[str], top_k_per_keyword: int = 50) -> Tuple[Dict, Dict, Dict]:
    all_payloads = {}
    keyword_results = {}
    keyword_types = {}

    if not keywords:
        return {}, {}, {}

    with ThreadPoolExecutor(max_workers=max(1, len(keywords))) as executor:
        futures = {executor.submit(keyword_search_single, kw, top_k_per_keyword): kw for kw in keywords}
        for future in futures:
            ids, payloads, kw_type = future.result()
            kw = futures[future]
            keyword_results[kw] = ids
            keyword_types[kw] = kw_type
            all_payloads.update(payloads)

    return keyword_results, all_payloads, keyword_types


# ✅ 날짜 + 키워드 결합 검색
def keyword_then_semantic_rerank(question: str, keywords: List[str], top_k: int = 5):
    print("\n" + "=" * 80)
    print(f"🧩 [keyword_then_semantic_rerank] 검색 요청 시작")
    print(f"📥 질문: {question}")
    print(f"🔑 키워드 리스트: {keywords}")
    print("=" * 80)

    keyword_results, all_payloads, keyword_types = search_qdrant_metadata_parallel(keywords, top_k_per_keyword=200)
    date_keywords = [kw for kw, t in keyword_types.items() if t in ("year", "month", "day")]
    text_keywords = [kw for kw, t in keyword_types.items() if t == "text"]

    print(f"📅 날짜 키워드: {date_keywords if date_keywords else '없음'}")
    print(f"💬 텍스트 키워드: {text_keywords if text_keywords else '없음'}")

    # 날짜가 포함된 경우
    if date_keywords:
        print("\n⚡ [1단계] 날짜 + 키워드 결합 → Qdrant 검색 실행")
        query_vector = encode_and_clear([question])[0]

        must_conditions = []
        for kw in date_keywords:
            kw_type = keyword_types[kw]
            if kw_type == "year":
                must_conditions.append(FieldCondition(key="year", match=MatchValue(value=int(kw))))
            elif kw_type == "month":
                must_conditions.append(FieldCondition(key="month", match=MatchValue(value=int(kw))))
            elif kw_type == "day":
                must_conditions.append(FieldCondition(key="day", match=MatchValue(value=int(kw))))

        if text_keywords:
            should_conditions = []
            for kw in text_keywords:
                should_conditions.extend([
                    FieldCondition(key="sFileName", match=MatchValue(value=kw)),
                    FieldCondition(key="keywords", match=MatchAny(any=[kw])),
                    FieldCondition(key="keywords", match={"text": kw}),
                ])
            must_conditions.append(Filter(should=should_conditions))

        filter_query = Filter(must=must_conditions)
        results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=filter_query,
            limit=top_k * 10,
            with_payload=True
        )

        # ✅ 결과 없을 경우 → 의미검색 fallback
        if not results:
            print("⚠️ [1단계] 검색 결과 0건 → 의미검색 fallback 실행")
            return semantic_vector_search(question, top_k)

       # print(f"📊 Qdrant 검색 결과: {len(results)}건\n")
        return apply_keyword_bonus(results, text_keywords, top_k)

    # 키워드만 있을 경우
    elif text_keywords:
        print("\n🔤 [2단계] 키워드 기반 검색 실행")
        query_vector = encode_and_clear([question])[0]
        should_conditions = []
        for kw in text_keywords:
            should_conditions.extend([
                FieldCondition(key="sFileName", match=MatchValue(value=kw)),
                FieldCondition(key="keywords", match=MatchAny(any=[kw])),
                FieldCondition(key="keywords", match={"text": kw}),
            ])
        filter_query = Filter(should=should_conditions)
        results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=filter_query,
            limit=top_k * 10,
            with_payload=True
        )

        # ✅ 결과 없을 경우 → 의미검색 fallback
        if not results:
            print("⚠️ [2단계] 검색 결과 0건 → 의미검색 fallback 실행")
            return semantic_vector_search(question, top_k)

        #print(f"📊 Qdrant 검색 결과: {len(results)}건\n")
        return apply_keyword_bonus(results, text_keywords, top_k)

    # 아무것도 없을 경우 → 의미검색 fallback
    else:
        print("\n⚠️ [3단계] 필터 없음 → 전체 의미검색 fallback")
        results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=encode_and_clear([question])[0],
            limit=top_k * 10,
            with_payload=True
        )
        return apply_keyword_bonus(results, keywords, top_k)


# ✅ 의미검색 fallback (단순 벡터검색)
def semantic_vector_search(question: str, top_k: int = 30):
    query_vector = encode_and_clear([question])[0]
    results = qdrant_client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=top_k,
        with_payload=True
    )
    return [
        {
            "id": hit.id,
            "문서ID": hit.payload.get("doc_id", ""),
            "페이지": hit.payload.get("nPage", ""),
            "파일명": hit.payload.get("sFileName", ""),
            "날짜": f"{hit.payload.get('year', '----')}-{hit.payload.get('month', '--')}-{hit.payload.get('day', '--')}",
            "경로": hit.payload.get("sFilePath", ""),
            "보안등급": hit.payload.get("sGrade", ""),
            "score": round(hit.score, 5),
        }
        for hit in results
    ]
