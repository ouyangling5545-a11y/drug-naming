from __future__ import annotations
from fastapi import APIRouter, Request
from ..models.chinese import ChineseNameRequest, ChineseNameResponse, ChineseCharacterSimilarity
from ..engines.chinese_name import ChineseNameEngine

router = APIRouter()

# In-memory approved names DB (would be replaced with real data)
_APPROVED_NAMES: list[dict] = [
    {"chinese_name": "伊马替尼", "inn": "imatinib"},
    {"chinese_name": "厄洛替尼", "inn": "erlotinib"},
    {"chinese_name": "吉非替尼", "inn": "gefitinib"},
    {"chinese_name": "奥希替尼", "inn": "osimertinib"},
    {"chinese_name": "阿达木单抗", "inn": "adalimumab"},
    {"chinese_name": "曲妥珠单抗", "inn": "trastuzumab"},
    {"chinese_name": "帕博利珠单抗", "inn": "pembrolizumab"},
    {"chinese_name": "纳武利尤单抗", "inn": "nivolumab"},
    {"chinese_name": "利拉鲁肽", "inn": "liraglutide"},
    {"chinese_name": "司美格鲁肽", "inn": "semaglutide"},
]


def _get_chinese_engine(request: Request | None = None) -> ChineseNameEngine:
    registry = getattr(request.app.state, "data_registry", None) if request else None
    approved = []
    if registry:
        chinese_source = registry.get("approved_chinese_names")
        if chinese_source:
            approved = chinese_source.load()
    if not approved:
        approved = _APPROVED_NAMES
    return ChineseNameEngine(approved_names_db=approved)


@router.post("/suggest", response_model=ChineseNameResponse)
def suggest_chinese_names(request_body: ChineseNameRequest, request: Request = None) -> ChineseNameResponse:
    """Generate Chinese drug name candidates from an INN name."""
    engine = _get_chinese_engine(request)
    return engine.suggest(request_body)


@router.post("/check", response_model=ChineseCharacterSimilarity)
def check_chinese_similarity(name1: str, name2: str) -> ChineseCharacterSimilarity:
    """Check similarity between two Chinese drug names."""
    engine = ChineseNameEngine()
    return engine.check_similarity(name1, name2)
