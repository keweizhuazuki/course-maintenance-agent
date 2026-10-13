import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Choice(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    text: str = Field(min_length=1, max_length=1500)


class Quiz(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    prompt: str = Field(min_length=1, max_length=3000)
    choices: list[Choice] = Field(min_length=2, max_length=6)
    answer_id: str
    explanation: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def valid_answer(self):
        ids = [x.id for x in self.choices]
        if len(set(ids)) != len(ids) or self.answer_id not in ids:
            raise ValueError("Quiz needs unique choice IDs and an answer matching one choice")
        return self


class Block(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    text: str = Field(min_length=1, max_length=12000)
    image: str | None = None
    image_alt: str | None = None

    @model_validator(mode="after")
    def image_contract(self):
        if self.image and not re.fullmatch(r"assets/[a-zA-Z0-9_-]+\.(png|jpg|jpeg|webp)", self.image):
            raise ValueError("Images must be a PNG/JPEG/WebP directly inside assets/")
        if self.image and not self.image_alt:
            raise ValueError("Images require alternative text")
        return self


class Chapter(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    title: str = Field(min_length=1, max_length=200)
    blocks: list[Block] = Field(min_length=1, max_length=30)
    quizzes: list[Quiz] = Field(default_factory=list, max_length=20)


class Course(Strict):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    title: str = Field(min_length=1, max_length=200)
    language: str = Field(default="zh-CN", pattern=r"^[a-zA-Z-]{2,20}$")
    chapters: list[Chapter] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def ids(self):
        ids = []
        for ch in self.chapters:
            ids.append(ch.id)
            ids.extend(x.id for x in ch.blocks + ch.quizzes)
        if len(ids) != len(set(ids)):
            raise ValueError("Chapter, block and quiz IDs must be globally unique")
        if len(ids) > 330:
            raise ValueError("Course exceeds 300 items and 30 chapters")
        return self


def targets(course):
    found = {}
    for ch in course["chapters"]:
        for key, kind in (("blocks", "block"), ("quizzes", "quiz")):
            for obj in ch[key]:
                found[obj["id"]] = {"kind": kind, "chapter_id": ch["id"], "chapter_title": ch["title"], "value": obj, "digest": digest(obj)}
    return found


class Citation(Strict):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=15000)


class Proposal(Strict):
    target_id: str
    expected_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    replacement: dict
    rationale: str = Field(min_length=1, max_length=6000)
    citations: list[Citation] = Field(default_factory=list, max_length=8)
    requires_resolution: bool = False


class DraftRequest(Strict):
    expected_revision: int = Field(ge=0)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposals: list[Proposal] = Field(min_length=1, max_length=100)


def citation_errors(citations, source):
    lines = source.splitlines()
    if not citations:
        return ["missing_evidence"]
    errors = []
    for c in citations:
        if c["start_line"] > c["end_line"] or c["end_line"] > len(lines):
            errors.append("invalid_line_range")
        elif "\n".join(lines[c["start_line"] - 1:c["end_line"]]) != c["quote"]:
            errors.append("citation_mismatch")
    return sorted(set(errors))
