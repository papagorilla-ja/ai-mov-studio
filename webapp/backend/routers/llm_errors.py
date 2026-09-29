"""LLM に頼む処理の失敗を、画面に出す HTTP のエラーにする（#99）。

以前はサービス層（services/llm_service.py）が HTTPException を直接投げており、
関数ごとにエラーの番号や文言がばらばらだった。サービスはふつうの例外で返し、
ここで一か所で HTTP のエラーに直す。
"""
from fastapi import HTTPException


def llm_error(e: Exception, action: str) -> HTTPException:
    """action（例: 「画像プロンプトの生成」）に失敗したことを知らせるエラー。

    ValueError   … 引き直しても JSON として読めなかった（もう一度試せば通ることが多い）
    それ以外     … LLM に届かなかった（サーバーが止まっているなど）
    """
    if isinstance(e, ValueError):
        return HTTPException(
            status_code=502,
            detail=f"{action}に失敗しました。AI の応答を読み取れませんでした。もう一度お試しください。（{e}）",
        )
    return HTTPException(
        status_code=503,
        detail=f"{action}に失敗しました。ローカル LLM に接続できません。起動状態を確認してください。（{e}）",
    )
