from typing import Any

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


class TiptapNode(ApiModel):
    type: str = Field(min_length=1)
    attrs: dict[str, Any] | None = Field(default=None, exclude_if=lambda value: value is None)
    content: list["TiptapNode"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    text: str | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_text_node(self) -> "TiptapNode":
        if self.type == "text" and not self.text:
            raise ValueError("text node requires text")
        return self


class TiptapDocument(ApiModel):
    type: str = Field(pattern="^doc$")
    content: list[TiptapNode] = Field(default_factory=list)
