"""
HyperFrames レンダリングワーカー — HTTP サーバー (ホストネイティブ実行版)

api コンテナからのレンダリングジョブを受け取り、ホスト上で hyperframes render を
実行して MP4 を生成する。

FIX-17 で --docker を廃止しネイティブ実行に統一した。理由（すべて実測で確認）:
  - --docker はコンテナ内に GPU が無く browserGpuMode=software (SwiftShader) になり、
    さらに --experimental-fast-capture が engage せず screenshot キャプチャに落ちる
  - ネイティブ実行では captureMode が drawelement / beginframe になり大幅に高速
    （10秒コンポジションで 12.2秒 → 5.1秒）
  - hyperframes 0.7.82 の --docker は実プロジェクトで
    「Missing manifest at /usr/local/lib/core/dist/hyperframe.manifest.json」で失敗する

ホスト要件: hyperframes (npm) と ffmpeg/ffprobe (brew install ffmpeg)

エンドポイント:
  GET  /health         ヘルスチェック
  POST /render/stream  レンダリング実行。進捗を 1 行 1 件の JSON で逐次返す（api が使う）
  POST /render         レンダリング実行。終わってから結果だけを返す（手動確認用）

進捗（#96）:
  hyperframes は標準出力に「45%  Capturing frame 287/632」の形で進捗を出す。
  以前は終わってからまとめて受け取っていたため、レンダリングの間ずっと
  画面の進捗が止まっていた。/render/stream はこれを逐次読んで流す。

止め方（#96）:
  タイムアウトや、api 側の接続が切れた（生成の中止）ときは、hyperframes を
  子プロセス（Chrome）ごと終了させる。以前はタイムアウトしても止めておらず、
  Chrome が裏で動き続けてメモリを使い続けていた。
"""
import asyncio
import json
import os
import re
import shutil
import signal
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="HyperFrames Renderer", version="1.0.0")

# ─── 設定 ────────────────────────────────────────────────
PROJECTS_DIR_CONTAINER = "/app/projects"
DEFAULT_HOST_PROJECTS = str(Path(__file__).resolve().parent.parent / "projects")
PROJECTS_DIR_HOST = os.environ.get("PROJECTS_DIR_HOST", DEFAULT_HOST_PROJECTS)
HYPERFRAMES = None  # (path, bin_dir)


def find_hyperframes() -> tuple[str, str] | None:
    """(hyperframes バイナリのパス, その bin ディレクトリ) を返す。"""
    # NVM 管理下を優先探索
    nvm_versions = Path(os.environ.get("NVM_DIR", str(Path.home() / ".nvm"))) / "versions" / "node"
    if nvm_versions.exists():
        for v in sorted(nvm_versions.iterdir(), reverse=True):
            hf = v / "bin" / "hyperframes"
            if hf.exists():
                return str(hf), str(v / "bin")
    hf = shutil.which("hyperframes")
    if hf:
        return hf, str(Path(hf).parent)
    return None


def _to_host_path(p: str) -> str:
    """コンテナ絶対パス (/app/projects/...) をホスト絶対パスにマッピングする。"""
    if p.startswith(PROJECTS_DIR_CONTAINER):
        return PROJECTS_DIR_HOST + p[len(PROJECTS_DIR_CONTAINER):]
    return p


# Homebrew の既定パス。GUI から起動した場合など PATH に含まれないことがあるため明示する。
EXTRA_BIN_DIRS = ["/opt/homebrew/bin", "/usr/local/bin"]


def find_ffmpeg() -> str | None:
    """ffmpeg の場所を返す。ネイティブレンダリングの必須依存。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    # PATH に無くても Homebrew の標準位置にあれば採用する
    for d in EXTRA_BIN_DIRS:
        candidate = Path(d) / "ffmpeg"
        if candidate.exists():
            return str(candidate)
    return None


@app.on_event("startup")
async def startup():
    global HYPERFRAMES
    HYPERFRAMES = find_hyperframes()
    if HYPERFRAMES:
        print(f"hyperframes を検出: {HYPERFRAMES[0]} (bin_dir={HYPERFRAMES[1]})", flush=True)
    else:
        print("警告: hyperframes が見つかりません。レンダリングは失敗します。", flush=True)

    ff = find_ffmpeg()
    if ff:
        print(f"ffmpeg を検出: {ff}", flush=True)
    else:
        print("警告: ffmpeg が見つかりません。`brew install ffmpeg` を実行してください。", flush=True)


# ─── スキーマ ─────────────────────────────────────────────

class RenderRequest(BaseModel):
    video_dir: str       # コンテナ内絶対パス (例: /app/projects/p1/videos/v1)
    output_path: str     # video_dir からの相対パス (例: output/abc123.mp4)
    timeout: int = 3600  # レンダリングタイムアウト (秒)
    fps: int | None = None       # フレームレート（未指定なら hyperframes の既定 30）
    workers: int | None = None   # 並列ワーカー数（Chrome 1 プロセス約 256MB。未指定は auto）
    quality: str | None = None   # draft / standard / high


class RenderResponse(BaseModel):
    status: str          # "success" | "error"
    stdout: str = ""
    stderr: str = ""
    message: str = ""


# ─── レンダリングの実行 ───────────────────────────────────

# 進捗の行（例: "  ██████░░░  45%  Capturing frame 287/632 (4 workers)"）
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_PROGRESS_RE = re.compile(r"(\d{1,3})%\s+(\S.*?)\s*$")
# 終了させるとき、SIGTERM の後にこの秒数待ってから SIGKILL する
KILL_GRACE_SEC = 5
# 結果に添える出力の長さ（末尾）
OUTPUT_TAIL_CHARS = 4000


def _seconds_label(sec: int) -> str:
    """タイムアウトの秒数を文言にする（2 分未満は秒で書く）。"""
    return f"{sec} 秒" if sec < 120 else f"{sec // 60} 分"


def parse_progress(line: str) -> tuple[int, str] | None:
    """hyperframes の 1 行から (割合, 段階) を取り出す。進捗の行でなければ None。"""
    m = _PROGRESS_RE.search(_ANSI_RE.sub("", line))
    if not m:
        return None
    percent = int(m.group(1))
    return (percent, m.group(2)) if 0 <= percent <= 100 else None


def _check_ready(req: RenderRequest) -> Path:
    """レンダリングを始められるかを確かめ、ホスト側の動画フォルダを返す。"""
    host_video_dir = Path(_to_host_path(req.video_dir))
    if not host_video_dir.exists():
        raise HTTPException(status_code=400, detail=f"ディレクトリが存在しません: {host_video_dir}")
    if not HYPERFRAMES:
        raise HTTPException(status_code=503, detail="hyperframes が見つかりません。環境変数やパス設定をご確認ください。")
    if not find_ffmpeg():
        raise HTTPException(
            status_code=503,
            detail="ffmpeg が見つかりません。ホストで `brew install ffmpeg` を実行してください。",
        )
    return host_video_dir


def _build_command(req: RenderRequest) -> tuple[list[str], dict]:
    """hyperframes のコマンドと環境変数を組み立てる。"""
    hf_bin, hf_bindir = HYPERFRAMES
    # ネイティブ実行。macOS + ハードウェア GPU では fast-capture が自動で有効になり、
    # captureMode が drawelement / beginframe になって screenshot 方式より大幅に速い。
    cmd = [hf_bin, "render", "--output", req.output_path]
    if req.fps:
        cmd += ["--fps", str(req.fps)]
    if req.workers:
        # ワーカー数を明示することで Chrome プロセスの増えすぎによるメモリ逼迫を防ぐ
        cmd += ["--workers", str(req.workers)]
    if req.quality:
        cmd += ["--quality", req.quality]

    env = {**os.environ}
    # hyperframes (Node.js) と ffmpeg/ffprobe (Homebrew) の両方が見つかるよう PATH を調整。
    # Apple Silicon の Homebrew は /opt/homebrew/bin なので必ず含めること。
    env["PATH"] = ":".join(
        [hf_bindir, *EXTRA_BIN_DIRS, "/usr/bin", "/bin", "/usr/sbin", "/sbin", env.get("PATH", "")]
    )
    # hyperframes は起動時に新バージョンを検知すると、レンダリングを続けたまま
    # バックグラウンドで `npm install -g hyperframes@X` を実行する。
    # インストール中はパッケージのファイルが一時的に消えるため、実行中のレンダリングが
    # "[HyperframeRuntimeLoader] Missing manifest" で失敗する。
    # hyperframes は毎日のように更新されるため放置すると再発するので、
    # レンダリング用の子プロセスでは自己更新を無効化する。
    # （更新は start.sh が通知し、ユーザーが明示的に実行する運用にする）
    env["HYPERFRAMES_NO_UPDATE_CHECK"] = "1"
    env["HYPERFRAMES_NO_AUTO_INSTALL"] = "1"
    return cmd, env


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """hyperframes を子プロセス（Chrome）ごと終了させる。

    start_new_session で hyperframes をプロセスグループの先頭にしてあるので、
    グループごとシグナルを送れば Chrome まで届く。
    """
    if proc.returncode is not None:
        return
    for sig, wait in ((signal.SIGTERM, KILL_GRACE_SEC), (signal.SIGKILL, None)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        if wait is None:
            break
        try:
            await asyncio.wait_for(proc.wait(), timeout=wait)
            return
        except asyncio.TimeoutError:
            continue
    await proc.wait()


async def run_render(req: RenderRequest, host_video_dir: Path) -> AsyncIterator[dict]:
    """hyperframes を実行し、進捗と最後の結果を dict で順に返す。

    返すもの:
      {"type": "progress", "percent": 45, "stage": "Capturing frame 287/632"}
      {"type": "result", "status": "success" | "error", "message": ..., "stdout": ..., "stderr": ...}

    呼び出し側が途中でやめた（接続が切れた）ときは、finally で hyperframes を終了させる。
    """
    cmd, env = _build_command(req)
    print(f"[render] cwd={host_video_dir} cmd={' '.join(cmd)} timeout={req.timeout}", flush=True)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(host_video_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    # 標準エラーは詰まらないよう別に読み切る（ログが多く、読まないとパイプが一杯になって止まる）
    stderr_task = asyncio.create_task(proc.stderr.read())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + req.timeout
    stdout_parts: list[str] = []
    pending = ""
    last: tuple[int, str] | None = None
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=remaining)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            stdout_parts.append(text)
            # 進捗バーは \r で同じ行を書き換えるので、\r も行の区切りとして扱う
            *lines, pending = re.split(r"[\r\n]", pending + text)
            for line in lines:
                progress = parse_progress(line)
                if progress and progress != last:
                    last = progress
                    yield {"type": "progress", "percent": progress[0], "stage": progress[1]}

        await proc.wait()
        stdout = "".join(stdout_parts)
        stderr = (await stderr_task).decode("utf-8", errors="replace")
        print(f"[render] returncode={proc.returncode}", flush=True)
        if proc.returncode != 0:
            print(f"[render][stderr] {stderr[-500:]}", flush=True)
            yield {
                "type": "result", "status": "error",
                "message": f"hyperframes が終了コード {proc.returncode} で失敗しました",
                "stdout": stdout[-OUTPUT_TAIL_CHARS:], "stderr": stderr[-OUTPUT_TAIL_CHARS:],
            }
        else:
            yield {"type": "result", "status": "success", "message": "",
                   "stdout": stdout[-OUTPUT_TAIL_CHARS:], "stderr": ""}
    except asyncio.TimeoutError:
        await _terminate(proc)
        print(f"[render] タイムアウトしたため終了させました ({req.timeout} 秒)", flush=True)
        yield {"type": "result", "status": "error",
               "message": f"タイムアウト: レンダリングが {_seconds_label(req.timeout)}以内に完了しませんでした",
               "stdout": "".join(stdout_parts)[-OUTPUT_TAIL_CHARS:], "stderr": ""}
    finally:
        # 中止（接続が切れて、この生成器が途中で閉じられた）でもここを通る
        if proc.returncode is None:
            print("[render] 呼び出し元が切断したため終了させます", flush=True)
            await _terminate(proc)
        if not stderr_task.done():
            stderr_task.cancel()


# ─── エンドポイント ───────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "hyperframes": HYPERFRAMES[0] if HYPERFRAMES else "not found",
        "ffmpeg": find_ffmpeg() or "not found",
    }


@app.post("/render/stream")
async def render_stream(req: RenderRequest):
    """レンダリングを実行し、進捗と結果を 1 行 1 件の JSON（NDJSON）で逐次返す。"""
    host_video_dir = _check_ready(req)

    async def lines():
        async for event in run_render(req, host_video_dir):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@app.post("/render", response_model=RenderResponse)
async def render(req: RenderRequest):
    """レンダリングを実行し、終わってから結果だけを返す（手動での確認用）。"""
    host_video_dir = _check_ready(req)
    result: dict = {}
    try:
        async for event in run_render(req, host_video_dir):
            if event["type"] == "result":
                result = event
    except Exception as e:  # noqa: BLE001
        return RenderResponse(status="error", message=str(e))
    return RenderResponse(
        status=result.get("status", "error"),
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        message=result.get("message", ""),
    )


# ─── ローカル起動 ─────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("renderer_server:app", host="127.0.0.1", port=8200, reload=False)
