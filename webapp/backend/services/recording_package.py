"""録音ツールの収録パッケージ（.zip）の読み込み（#12）。

録音ツール（webapp/frontend/src/recorder-tool/）が保存する zip の中身:
  manifest.json … 形式・バージョン・名前・収録モード・各テイクの情報
  takes/NN.wav  … ノイズ除去済みの音声（16kHz・モノラル・16bit）

利用者の手元で作られたファイルを受け取るため、中身は信用せずに検証する。
  - manifest に書かれた決まった名前のファイルだけを読み、zip 内のパスをそのまま
    ディスクへ展開しない（パス・トラバーサル対策）
  - 展開後の大きさを、読む前に確認する（zip 爆弾対策）
  - 各テイクは ffmpeg で 16kHz WAV に変換し直す（壊れたファイル・想定外の形式を弾く）
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from services.audio_utils import convert_to_mono_16k
from services.voice_corpus import MAX_SESSION_ITEMS, SUPPORTED_MODES

# 録音ツールの recordingPackage.js と同じ値にすること
PACKAGE_FORMAT = "ai-mov-studio/voice-recording"
SUPPORTED_VERSIONS = (1,)

MAX_PACKAGE_BYTES = 50 * 1024 * 1024    # zip 全体の上限
MAX_MANIFEST_BYTES = 256 * 1024         # manifest.json の上限（展開後）
MAX_TAKE_BYTES = 10 * 1024 * 1024       # 1 テイクの上限（展開後）。16kHz・16bit で約 5 分
MAX_NAME_LENGTH = 100                   # 収録音声の名前の上限（文字数）
TAKE_FILE_PATTERN = re.compile(r"^takes/\d{2}\.wav$")
_COPY_CHUNK = 1024 * 1024


class PackageError(ValueError):
    """収録パッケージの内容に問題がある。利用者に伝えて、ファイルを選び直してもらう。"""


@dataclass
class RecordingPackage:
    """検証済みの収録パッケージ。"""
    name: str               # 収録音声の名前
    mode: str               # 収録モード（voice_corpus.SUPPORTED_MODES のいずれか）
    take_paths: list[str]   # 16kHz モノラル WAV に変換したテイク（manifest の順）


def save_upload(source: BinaryIO, destination: Path) -> None:
    """アップロードされたファイルを、上限を確かめながら保存する。"""
    written = 0
    with open(destination, "wb") as out:
        while chunk := source.read(_COPY_CHUNK):
            written += len(chunk)
            if written > MAX_PACKAGE_BYTES:
                raise PackageError(
                    f"ファイルが大きすぎます（上限 {MAX_PACKAGE_BYTES // (1024 * 1024)}MB）。"
                    "録音ツールで保存したファイルを選んでください。"
                )
            out.write(chunk)


def _read_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        info = zf.getinfo("manifest.json")
    except KeyError:
        raise PackageError("収録データではありません（manifest.json がありません）。録音ツールで保存した zip を選んでください。")
    if info.file_size > MAX_MANIFEST_BYTES:
        raise PackageError("manifest.json が大きすぎます。録音ツールで保存した zip を選んでください。")
    try:
        manifest = json.loads(zf.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PackageError("manifest.json を読めません。ファイルが壊れている可能性があります。")
    if not isinstance(manifest, dict) or manifest.get("format") != PACKAGE_FORMAT:
        raise PackageError("録音ツールの収録データではありません。")
    if manifest.get("version") not in SUPPORTED_VERSIONS:
        raise PackageError(
            f"対応していない形式のバージョンです（{manifest.get('version')}）。"
            "設定画面から録音ツールをダウンロードし直して、録音し直してください。"
        )
    return manifest


def _resolve_name(requested: str, manifest: dict) -> str:
    """画面で入力された名前を優先し、空なら録音ツールで付けた名前を使う。"""
    manifest_name = manifest.get("name")
    name = (requested or "").strip() or (manifest_name.strip() if isinstance(manifest_name, str) else "")
    if not name:
        raise PackageError("収録音声の名前を入力してください。")
    if len(name) > MAX_NAME_LENGTH:
        raise PackageError(f"収録音声の名前は {MAX_NAME_LENGTH} 文字以内にしてください。")
    return name


def _take_files(manifest: dict) -> list[str]:
    """manifest からテイクのファイル名を取り出し、決まった形かを確かめる。"""
    takes = manifest.get("takes")
    if not isinstance(takes, list) or not 1 <= len(takes) <= MAX_SESSION_ITEMS:
        raise PackageError(f"テイクの数が正しくありません（1〜{MAX_SESSION_ITEMS} 本）。")
    files: list[str] = []
    for take in takes:
        file_name = take.get("file") if isinstance(take, dict) else None
        if not isinstance(file_name, str) or not TAKE_FILE_PATTERN.match(file_name):
            raise PackageError("テイクのファイル名が正しくありません。録音ツールで保存した zip を選んでください。")
        if file_name in files:
            raise PackageError(f"同じテイクが重複しています: {file_name}")
        files.append(file_name)
    return files


def extract_package(package_path: Path, work_dir: Path, requested_name: str = "") -> RecordingPackage:
    """収録パッケージを検証し、各テイクを work_dir に 16kHz モノラル WAV として書き出す。

    問題があれば PackageError（利用者が直せる問題）を送出する。
    """
    try:
        zf = zipfile.ZipFile(package_path)
    except zipfile.BadZipFile:
        raise PackageError("zip ファイルとして読めません。録音ツールで保存したファイルを選んでください。")

    with zf:
        manifest = _read_manifest(zf)
        name = _resolve_name(requested_name, manifest)
        mode = manifest.get("mode")
        if mode not in SUPPORTED_MODES:
            raise PackageError(f"対応していない収録モードです: {mode}")

        take_paths: list[str] = []
        for number, file_name in enumerate(_take_files(manifest), start=1):
            try:
                info = zf.getinfo(file_name)
            except KeyError:
                raise PackageError(f"テイクのファイルがありません: {file_name}")
            if info.file_size > MAX_TAKE_BYTES:
                raise PackageError(f"テイクが長すぎます: {file_name}")

            # zip 内の名前は使わず、こちらで決めた名前で書き出す
            raw_path = work_dir / f"take_{number:02d}.input"
            wav_path = work_dir / f"take_{number:02d}.wav"
            try:
                with zf.open(info) as src, open(raw_path, "wb") as dst:
                    shutil.copyfileobj(src, dst, _COPY_CHUNK)
            # BadZipFile: CRC 不一致など / RuntimeError: 暗号化されている /
            # NotImplementedError: 対応していない圧縮方式
            except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError) as e:
                raise PackageError(f"テイクを取り出せません（ファイルが壊れている可能性があります）: {file_name} ({e})")
            try:
                convert_to_mono_16k(str(raw_path), str(wav_path))
            except Exception:
                raise PackageError(f"テイクを音声として読めません: {file_name}")
            finally:
                raw_path.unlink(missing_ok=True)
            take_paths.append(str(wav_path))

    return RecordingPackage(name=name, mode=mode, take_paths=take_paths)
