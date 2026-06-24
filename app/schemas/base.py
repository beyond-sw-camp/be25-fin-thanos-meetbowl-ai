from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class UtcDatetimeModel(ApiModel):
    @model_validator(mode="after")
    def validate_utc_datetimes(self) -> "UtcDatetimeModel":
        for field_name in self.__class__.model_fields:
            value = getattr(self, field_name)
            if field_name.endswith(("_at", "_time")) and isinstance(value, datetime):
                if value.utcoffset() != timezone.utc.utcoffset(value):
                    raise ValueError(f"{field_name} must use UTC")
        return self
