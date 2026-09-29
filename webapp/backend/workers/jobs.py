"""実行中の動画生成（#96）。

api のプロセスの中で、動画ごとに実行中の生成（asyncio のタスク）を持つ。これで次ができる。
  - 同じ動画の生成を 2 つ始めない
  - 生成を本当に止める（タスクを cancel する）
  - 「実行中の履歴なのに処理が無い」ものを見分ける（再起動で途切れたものなど）

以前は DB の印（video.status）だけで判断していた。「ステータスを強制リセット」は
印を書き換えるだけで処理は止まらず、リセットの後に同じ動画の生成をもう 1 つ始められた。
2 つの処理が同じ音声や分割レンダリングのフォルダを書き換え、壊し合っていた。
"""
import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass


@dataclass
class _Job:
    generation_id: str
    task: asyncio.Task | None = None


class RunningGenerations:
    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}

    def reserve(self, video_id: str, generation_id: str) -> None:
        """生成を始める前に、動画を押さえる。

        履歴を DB に書いてからタスクを作るまでの間も「実行中」と見なすため。
        その間に状態を問い合わせられても、処理の無い履歴として失敗にされない。
        """
        if video_id in self._jobs:
            raise RuntimeError("この動画は既に生成処理中です")
        self._jobs[video_id] = _Job(generation_id)

    def start(self, video_id: str, coro: Coroutine) -> asyncio.Task:
        """押さえた動画の生成を始める。終わったら自動で外す。"""
        job = self._jobs[video_id]
        task = asyncio.create_task(coro)
        job.task = task

        def _done(t: asyncio.Task) -> None:
            if self._jobs.get(video_id) is job:
                del self._jobs[video_id]

        task.add_done_callback(_done)
        return task

    def release(self, video_id: str) -> None:
        """始められなかったときに押さえを外す。"""
        self._jobs.pop(video_id, None)

    def is_running(self, video_id: str) -> bool:
        return video_id in self._jobs

    def current(self, video_id: str) -> str | None:
        """実行中の生成の ID。"""
        job = self._jobs.get(video_id)
        return job.generation_id if job else None

    def cancel(self, video_id: str) -> bool:
        """実行中の生成を止める。止めるものがあれば True。"""
        job = self._jobs.get(video_id)
        if job is None or job.task is None or job.task.done():
            return False
        job.task.cancel()
        return True


running_generations = RunningGenerations()
