"""日時の扱い（#95）。

DB には **UTC の時刻を、タイムゾーンの印を付けずに** 保存する（これまでのデータと同じ形）。
api コンテナの時計は UTC なので datetime.now() でも同じ値になるが、
実行環境のタイムゾーンに左右されないよう、保存する時刻は必ず utcnow() で作る。

API で返すときは UtcDatetime 型で末尾に Z を付け、UTC であることを示す。
付けないと、画面の new Date() が印の無い日時を日本時間として読み、
9 時間前の時刻で表示していた。
"""
from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def utcnow() -> datetime:
    """今の UTC の時刻（タイムゾーンの印なし。DB に保存する形）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_utc_iso(value: datetime) -> str:
    """印の無い日時は UTC とみなし、末尾に Z を付けた ISO 8601 にする。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# 応答スキーマの日時はすべてこの型にする
UtcDatetime = Annotated[
    datetime, PlainSerializer(_to_utc_iso, return_type=str, when_used="json-unless-none")
]
