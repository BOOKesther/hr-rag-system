"""Validation contracts for durable artifacts (JSON Schema via model_json_schema)."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Evidence(BaseModel):
    model_config=ConfigDict(extra='allow')
    evidence_id:str
    element_id:str
    text:str
    page_no:int|None
    element_type:str
    bbox:list[float]|None


class Archive(BaseModel):
    model_config=ConfigDict(extra='allow')
    schema_version:Literal['1.0']
    document_id:str
    candidate_id:str
    source:dict
    profile:dict
    blocks:dict
    evidence:list[Evidence]
    assets:dict
    tables:list[dict]
    quality:dict

    @model_validator(mode='after')
    def check_references(self):
        ids={e.evidence_id for e in self.evidence}
        for block in self.blocks['semantic_blocks']:
            if not set(block['evidence_ids']) <= ids:
                raise ValueError('语义块存在无效证据引用')
        if not self.profile.get('name'):
            raise ValueError('候选人姓名不能为空')
        return self


class CleanSection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    section:str
    text:str=Field(min_length=1)


class Knowledge(BaseModel):
    model_config=ConfigDict(extra='forbid')
    knowledge_schema_version:Literal['1.0']
    knowledge_id:str
    candidate_id:str
    source_document_id:str
    version_no:int=Field(ge=1)
    status:Literal['ready']
    clean_version:str
    sections:list[CleanSection]
    clean_text:str=Field(min_length=60)
