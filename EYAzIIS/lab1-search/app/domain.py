from pydantic import BaseModel


class SearchParams(BaseModel):
    q: str = ""
    all_words: bool = True
    date_start: str = ""
    date_end: str = ""


class RelevanceRequest(BaseModel):
    params: SearchParams
    doc_id: int
    relevant: bool


class BatchRelevanceRequest(BaseModel):
    params: SearchParams
    doc_ids: list[int]
    relevant: bool