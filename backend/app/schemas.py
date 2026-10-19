from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class OptionInput(Input):
    text: str = Field(min_length=1, max_length=200)
    is_correct: bool = False


class QuestionInput(Input):
    category_id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=1200)
    explanation: str = Field(min_length=1, max_length=1200)
    company: Literal["svyazkom", "sensory_hub", "systematics", "galaxy"] | None = None
    difficulty: int = Field(default=1, ge=1, le=5)
    time_limit_seconds: int | None = Field(default=None, ge=1, le=3600)
    is_active: bool = True
    options: list[OptionInput] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def one_correct(self):
        if sum(o.is_correct for o in self.options) != 1:
            raise ValueError("Нужен ровно один правильный вариант")
        if len({o.text for o in self.options}) != len(self.options):
            raise ValueError("Варианты не должны повторяться")
        return self


class CategoryInput(Input):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=1000)


class RoomInput(Input):
    title: str = Field(min_length=1, max_length=255)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    questions_count: int | None = Field(default=None, ge=1, le=100)
    question_time_limit_seconds: int | None = Field(default=None, ge=1, le=3600)
    max_points_per_question: int | None = Field(default=None, ge=1, le=10000)
    min_correct_points: int | None = Field(default=None, ge=0, le=10000)


class RoomPatch(RoomInput):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class RoomQuestionsInput(Input):
    question_ids: list[int] = Field(default_factory=list, max_length=10000)
    category_ids: list[int] = Field(default_factory=list, max_length=100)
