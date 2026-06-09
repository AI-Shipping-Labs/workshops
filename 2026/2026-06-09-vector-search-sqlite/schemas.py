from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class ToolCall(BaseModel):
    name: str
    arguments: dict


class AskResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCall]
