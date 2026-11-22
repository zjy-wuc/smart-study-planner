
from dataclasses import dataclass

from pydantic import BaseModel, Field

#表示这个对象在创建后，不能通过普通属性赋值修改字段
@dataclass(frozen=True)#是 Python 标准库提供的装饰器，可以自动为类生成初始化方法等常用方法。
class NoteSnapshot:
    note_id: int
    title: str
    content_md: str
    version: str


class SummaryOutput(BaseModel):
    overview: str = Field(min_length=1)
    key_points: str = Field(min_length=1)
    outline: str = Field(min_length=1)
