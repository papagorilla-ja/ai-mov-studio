"""裏で動くジョブ（試聴の音声・一括生成・PPTX のナレーション生成）の状態を持つ。

状態はプロセス内のメモリに dict で持つ（"status" は processing / pending / completed / done / error）。
以前は一括生成と PPTX のジョブが消えずに溜まり続けていた（#99）。ここで期限を付ける。
"""
import time

# 終わった（またはもう読まれない）ジョブを消すまでの秒数
FINISHED_STATUSES = ("completed", "done", "error")
# 終わっていなくても、これだけ読まれていないジョブは消す（途中で止まったものなど）
MAX_IDLE_SEC = 24 * 3600


class JobStore:
    """ジョブの状態を期限付きで持つ。dict と同じように読み書きする。

    消すのは次のどちらか。新しいジョブを入れるときに片付ける。
      - 終わっていて、最後に読まれてから ttl_sec 経ったもの
      - 最後に読まれてから MAX_IDLE_SEC 経ったもの
    画面が状態を読み続けている間は消えない（長い一括生成が途中で見えなくならない）。
    """

    def __init__(self, ttl_sec: int = 3600):
        self.ttl_sec = ttl_sec
        self._jobs: dict[str, dict] = {}
        self._touched: dict[str, float] = {}

    def __setitem__(self, job_id: str, state: dict) -> None:
        self.cleanup()
        self._jobs[job_id] = state
        self._touched[job_id] = time.time()

    def __getitem__(self, job_id: str) -> dict:
        return self._jobs[job_id]

    def get(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        if job is not None:
            self._touched[job_id] = time.time()
        return job

    def cleanup(self) -> None:
        now = time.time()
        expired = [
            jid for jid, job in self._jobs.items()
            if (job.get("status") in FINISHED_STATUSES and now - self._touched[jid] > self.ttl_sec)
            or now - self._touched[jid] > MAX_IDLE_SEC
        ]
        for jid in expired:
            self._jobs.pop(jid, None)
            self._touched.pop(jid, None)


class PreviewJobStore(JobStore):
    """試聴の音声のジョブ。音声（数 MB）を持つので、期限を短くする。"""

    def __init__(self, ttl_sec: int = 600):
        super().__init__(ttl_sec)

    def register(self, job_id: str) -> None:
        self[job_id] = {"status": "pending", "audio": None, "error": None}

    def update(self, job_id: str, status: str, audio: bytes | None = None, error: str | None = None) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.update(status=status, audio=audio, error=error)


# グローバルなシングルトンインスタンスとして提供
preview_job_store = PreviewJobStore()
