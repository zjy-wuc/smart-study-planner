from pydantic import BaseModel, ConfigDict, Field


class NumericProgressUpdate(BaseModel):
    """NUMERIC 累计完成数量"""

    model_config = ConfigDict(extra="forbid")

    actual_quantity: int = Field(
        ge=0,
        le=18446744073709551615,
        strict=True,
    )