"""音声の後処理。参照音声（reference.wav）の作成と、読み上げ速度の適用。

ブラウザのマイク収録は「前後に無音が入る」「録音レベルが人によってばらつく」
という癖があり、そのまま連結すると Qwen3-TTS の x-vector 抽出に入る有効な音声が
短くなったり、声質の再現が不安定になる。ここで無音トリムと音量正規化を行い、
複数テイクから均等に集めて既定 20 秒程度の参照音声に整える。

雑音対策の分担（#9）:
  - 収録セッション・録音ツールの音声 … ブラウザ側でノイズ除去済み。
    ここでは「衝撃音を無視する無音トリム＋音量正規化」だけを行う（二重処理を避ける）
  - 直接アップロードされた音声     … ブラウザを通らないため、ここで ffmpeg の
    ノイズ除去もかける（利用者が選んだときだけ）

依存は numpy / scipy / soundfile と ffmpeg（api イメージに同梱）。
"""
from __future__ import annotations

import logging
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

logger = logging.getLogger(__name__)

# 読み上げ速度の適用に使う ffmpeg フィルタ。
# atempo は音声向けに作られており、速度を変えても音の高さが変わらない。
# 1 シーン（21 秒の WAV）あたり実測 55 ミリ秒で、尺も指定どおりになる。
FFMPEG_BIN = "ffmpeg"
# 倍率がこの範囲を外れると atempo が受け付けない（1 段では 0.5〜2.0）。
SPEED_MIN, SPEED_MAX = 0.5, 2.0
# これ以下の差は等倍とみなす（無駄な再エンコードを避ける）
SPEED_EPSILON = 1e-3

TARGET_SR = 16000          # Qwen3-TTS 参照音声のサンプリングレート
DEFAULT_MAX_SEC = 20.0     # 参照音声の長さ上限
TARGET_RMS = 0.08          # 正規化後の目標 RMS（約 -22 dBFS）。小さめにして歪みを避ける
PEAK_CEILING = 0.95        # クリッピング防止のピーク上限
GAP_SEC = 0.15             # テイク間に挟む無音
SILENCE_FLOOR_RMS = 1e-4   # これ未満は「実質無音」（マイクがミュートだった等）として捨てる
_FRAME = 320               # 20ms @ 16kHz。無音判定のフレーム長

# ─── 無音トリムの判定（#10） ───────────────────────────────
# 閾値の基準にする RMS の上位パーセンタイル。最大値を基準にすると、
# 録音の端に入ったクリック音（数十 ms の大きな音）が基準になって閾値が上がり、
# 本来の発話まで無音側に判定されてしまう。上位 5% の値なら、短い衝撃音に引っ張られない。
REFERENCE_PERCENTILE = 95
# 下位 10% の RMS を背景ノイズの大きさとみなし、その NOISE_FLOOR_MARGIN 倍（約 +6dB）
# 未満は無音として扱う。空調やファンの音がある部屋では、発話に対する相対比だけだと
# 背景ノイズまで「発話」と判定され、前後の無音が削れなくなるため。
NOISE_FLOOR_PERCENTILE = 10
NOISE_FLOOR_MARGIN = 2.0
# 背景ノイズから決めた閾値の上限（発話の基準に対する比）。無音区間がほとんど無い音声では
# 下位 10% も発話になるため、上限を設けて発話の弱い部分まで削らないようにする（約 -12dB）
NOISE_THRESHOLD_CAP_RATIO = 0.25
# これより短く孤立した有声区間は衝撃音（クリック音・キー音など）とみなし、
# 発話の開始・終了の判定に使わない。日本語の 1 音節はおおむね 100ms 以上続く。
MIN_VOICED_SEC = 0.1
# 有声区間どうしの隙間がこれ以下なら、同じ発話の一部としてつなげる
# （子音や息継ぎで RMS が一瞬下がり、発話が細切れに判定されるのを防ぐ）
MERGE_GAP_SEC = 0.06

# 直接アップロードされた音声に掛けるノイズ除去（ffmpeg のフィルタ）。
#   highpass … 声より低い 70Hz 未満の振動音や空調のうなりを落とす
#   afftdn   … FFT でノイズの大きさを推定して差し引く。nr は除去量(dB)、
#               nf は想定するノイズの大きさ(dB)、tn=1 でノイズの変化に追従する
UPLOAD_DENOISE_FILTER = "highpass=f=70,afftdn=nr=12:nf=-40:tn=1"
# ffmpeg による変換の制限時間（秒）。長めの音声ファイルでも十分に収まる値
CONVERT_TIMEOUT_SEC = 120


def _to_mono(data: np.ndarray) -> np.ndarray:
    """ステレオ等の多チャンネルをモノラルに畳み込む。"""
    if data.ndim > 1:
        return data.mean(axis=1)
    return data


def _rms(data: np.ndarray) -> float:
    """音声全体の RMS（実効値）を求める。"""
    if data.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))


def _frame_rms(data: np.ndarray) -> np.ndarray:
    """_FRAME ごとの RMS を求める。端数のサンプルは判定に使わない。"""
    n_frames = data.size // _FRAME
    frames = data[:n_frames * _FRAME].reshape(n_frames, _FRAME)
    return np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))


def _voiced_runs(voiced: np.ndarray) -> list[tuple[int, int]]:
    """有声フレームの連なりを (開始フレーム, 終了フレーム（含まない）) の一覧で返す。"""
    # 前後に False を足して差分を取ると、立ち上がり(+1)と立ち下がり(-1)の位置が分かる
    edges = np.diff(np.concatenate(([0], voiced.astype(np.int8), [0])))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return list(zip(starts.tolist(), ends.tolist()))


def _merge_runs(runs: list[tuple[int, int]], max_gap: int) -> list[tuple[int, int]]:
    """隙間が max_gap フレーム以下の有声区間をつなげる。"""
    merged: list[tuple[int, int]] = []
    for start, end in runs:
        if merged and start - merged[-1][1] <= max_gap:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def trim_silence(data: np.ndarray, threshold_ratio: float = 0.06, margin_sec: float = 0.05) -> np.ndarray:
    """前後の無音と、録音の端に入った短い衝撃音（クリック音など）を落とす。

    フレームごとの RMS を求め、次の 2 つのうち大きい方を閾値として有声フレームを判定する
    （絶対閾値だと録音レベル差に弱いため、どちらもテイク内の相対値で決める）。
      - 上位パーセンタイルの RMS（発話の基準）× threshold_ratio
      - 下位パーセンタイルの RMS（背景ノイズ）× NOISE_FLOOR_MARGIN
    有声フレームの連なりのうち MIN_VOICED_SEC 以上続くものだけを発話とみなし、
    最初の発話の開始から最後の発話の終了までを切り出す。
    発話の立ち上がりが切れないよう、前後に margin_sec の余白を残す。
    """
    if data.size < _FRAME:
        return data

    rms = _frame_rms(data)
    reference = float(np.percentile(rms, REFERENCE_PERCENTILE))
    if reference <= 0:
        return data

    noise_floor = float(np.percentile(rms, NOISE_FLOOR_PERCENTILE))
    noise_threshold = min(noise_floor * NOISE_FLOOR_MARGIN, reference * NOISE_THRESHOLD_CAP_RATIO)
    threshold = max(reference * threshold_ratio, noise_threshold)

    runs = _voiced_runs(rms >= threshold)
    if not runs:
        return data

    frame_sec = _FRAME / TARGET_SR
    runs = _merge_runs(runs, max_gap=int(MERGE_GAP_SEC / frame_sec))
    min_frames = max(1, round(MIN_VOICED_SEC / frame_sec))
    speech = [(s, e) for s, e in runs if e - s >= min_frames]
    # 十分に長い区間が 1 つも無い（ごく短い発話だけ）なら、短い区間も含めて判定する
    if not speech:
        speech = runs

    margin = int(margin_sec * TARGET_SR)
    start = max(0, speech[0][0] * _FRAME - margin)
    end = min(data.size, speech[-1][1] * _FRAME + margin)
    return data[start:end]


def normalize_level(data: np.ndarray, target_rms: float = TARGET_RMS) -> np.ndarray:
    """RMS を目標値に合わせ、ピークがクリップしないように抑える。"""
    rms = _rms(data)
    if rms <= 0:
        return data

    gain = target_rms / rms
    peak = float(np.abs(data).max())
    if peak * gain > PEAK_CEILING:
        # 目標 RMS よりピーク優先（歪ませない）
        gain = PEAK_CEILING / peak
    return (data * gain).astype(np.float32)


def _read_mono_16k(path: str) -> np.ndarray:
    """16kHz の WAV をモノラルの float32 配列として読む。

    呼び出し側で 16kHz へ変換済みの前提。想定外のレートは黙って使わずに弾く
    （そのまま連結すると、再生速度と声の高さが変わった参照音声になるため）。
    """
    data, sr = sf.read(path, always_2d=False)
    if sr != TARGET_SR:
        raise ValueError(f"想定外のサンプリングレートです: {sr}Hz ({path})")
    return _to_mono(np.asarray(data, dtype=np.float32))


def _write_wav_16k(path: str, data: np.ndarray) -> None:
    """16kHz・16bit の WAV として書き出す（範囲外の値は丸める）。"""
    sf.write(path, np.clip(data, -1.0, 1.0).astype(np.float32), TARGET_SR, subtype="PCM_16")


def _clean_take(data: np.ndarray) -> np.ndarray | None:
    """1 本の音声を「無音トリム → 音量正規化」する。実質無音なら None を返す。"""
    # マイクがミュートだった等、実質無音の音声は参照音声に混ぜない
    if _rms(data) < SILENCE_FLOOR_RMS:
        return None
    data = trim_silence(data)
    if data.size == 0:
        return None
    return normalize_level(data)


def build_reference_audio(
    take_paths: list[str],
    output_path: str,
    max_sec: float = DEFAULT_MAX_SEC,
) -> tuple[float, int]:
    """複数テイクから参照音声を作って書き出す。

    各テイクを「無音トリム → 音量正規化」した上で、max_sec を
    テイク数で割った時間ずつ均等に採用して連結する。
    均等配分にすることで、感情・トーン指定モードのように
    テイクごとに声色が違う収録でも、全テイクの特徴が参照音声に入る。

    戻り値: (書き出した音声の秒数, 実際に採用したテイク数)
    """
    if not take_paths:
        raise ValueError("テイクが1つもありません")

    prepared = [
        cleaned for cleaned in (_clean_take(_read_mono_16k(path)) for path in take_paths)
        if cleaned is not None
    ]
    if not prepared:
        raise ValueError("有効な音声が含まれていません（マイクがミュートになっていた可能性があります）")

    # テイクあたりの採用秒数（均等配分）
    budget_samples = int((max_sec / len(prepared)) * TARGET_SR)
    gap = np.zeros(int(GAP_SEC * TARGET_SR), dtype=np.float32)

    chunks: list[np.ndarray] = []
    for i, data in enumerate(prepared):
        chunks.append(data[:budget_samples] if data.size > budget_samples else data)
        if i < len(prepared) - 1:
            chunks.append(gap)

    combined = np.concatenate(chunks)
    # 念のため全体でも上限を超えないように切る
    limit = int(max_sec * TARGET_SR)
    if combined.size > limit:
        combined = combined[:limit]

    _write_wav_16k(output_path, combined)
    return combined.size / TARGET_SR, len(prepared)


# ==========================================================================
# 形式変換・直接アップロードされた音声の整形
# ==========================================================================

def _resample_with_soundfile(src: str, dst: str) -> None:
    """ffmpeg が使えないときの予備。soundfile で読める形式だけを 16kHz モノラルにする。"""
    data, sr = sf.read(src, always_2d=False)
    data = _to_mono(np.asarray(data, dtype=np.float32))
    if sr != TARGET_SR:
        g = math.gcd(TARGET_SR, sr)
        data = resample_poly(data, TARGET_SR // g, sr // g)
    _write_wav_16k(dst, data)


def convert_to_mono_16k(src: str, dst: str, audio_filter: str | None = None) -> None:
    """任意形式の音声（webm / mp4 / mp3 / m4a / wav など）を 16kHz モノラル WAV に変換する。

    ブラウザや端末によって形式が変わるため、拡張子は信用せず ffmpeg に判定させる。
    audio_filter を渡すと、変換と同時に ffmpeg のフィルタ（ノイズ除去など）を掛ける。
    ffmpeg が失敗したときは soundfile で読み直す（この場合フィルタは掛からない）。
    両方とも失敗したら soundfile 側の例外をそのまま送出する。
    """
    cmd = [FFMPEG_BIN, "-v", "error", "-y", "-i", src, "-ac", "1", "-ar", str(TARGET_SR)]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += ["-c:a", "pcm_s16le", dst]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=CONVERT_TIMEOUT_SEC)
        return
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        detail = getattr(e, "stderr", b"")
        logger.warning(
            "ffmpeg での変換に失敗したため soundfile で読み直します (%s): %s",
            src, detail.decode("utf-8", "replace").strip()[-400:] if detail else e,
        )
    _resample_with_soundfile(src, dst)


def prepare_uploaded_reference(src: str, dst: str, clean: bool = True) -> float:
    """直接アップロードされた音声を、話者の参照音声として書き出す。

    clean=True  … 変換と同時にノイズ除去（UPLOAD_DENOISE_FILTER）を掛け、
                   「衝撃音を無視する無音トリム → 音量正規化」まで行う。
                   長さは削らない（収録セッションと違い、1 本の完成した音声として扱う）
    clean=False … 16kHz モノラルへの変換だけを行う（プロが録った音声などをそのまま使う）

    戻り値: 書き出した音声の秒数
    """
    convert_to_mono_16k(src, dst, UPLOAD_DENOISE_FILTER if clean else None)
    data = _read_mono_16k(dst)
    if clean:
        cleaned = _clean_take(data)
        if cleaned is None:
            raise ValueError("有効な音声が含まれていません（無音のファイルの可能性があります）")
        data = cleaned
        _write_wav_16k(dst, data)
    return data.size / TARGET_SR


# ==========================================================================
# 読み上げ速度
# ==========================================================================

def apply_speed(src: Path, dst: Path, speed: float) -> bool:
    """src の音声に読み上げ速度を掛けて dst へ書き出す。掛けたら True。

    速度を TTS のキャッシュより後段で適用しているのが要点。
    キャッシュのハッシュに速度を含めると、1 段階変えるたびに全シーンの
    音声合成をやり直すことになり（20 シーンで数分〜十数分）、
    「段階で調整する」という使い方が成り立たない。
    生の音声を等倍のままキャッシュし、ここで掛け直せば数十ミリ秒で済む。

    変換に失敗しても動画の生成は止めない。等倍のまま先へ進めた方が、
    音声が欠けた動画を出すより被害が小さいため。
    """
    dst.parent.mkdir(parents=True, exist_ok=True)

    if abs(speed - 1.0) < SPEED_EPSILON or not (SPEED_MIN <= speed <= SPEED_MAX):
        if abs(speed - 1.0) >= SPEED_EPSILON:
            logger.warning("読み上げ速度 %s は扱える範囲外のため等倍で処理します", speed)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return False

    try:
        subprocess.run(
            [FFMPEG_BIN, "-v", "error", "-y", "-i", str(src),
             "-filter:a", f"atempo={speed:g}", str(dst)],
            check=True, capture_output=True, timeout=120,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        detail = getattr(e, "stderr", b"")
        logger.warning(
            "読み上げ速度の適用に失敗したため等倍のまま使います (speed=%s): %s",
            speed, detail.decode("utf-8", "replace").strip() if detail else e,
        )
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return False
