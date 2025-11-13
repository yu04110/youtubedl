import argparse
import os
import re
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

import yt_dlp
from yt_dlp.utils import DownloadError

try:
    import whisper
except ImportError:  # pragma: no cover - whisper is optional
    whisper = None

SOURCE_FILE = Path("source.csv")
AUDIO_DIR = Path("audio")
VIDEO_DIR = Path("video")
TRANSCRIPTS_DIR = Path("transcripts")
WHISPER_MODEL = "small"

StageNames = Tuple[str, str, str]
DownloadFunc = Callable[[str], Path]


class LiveStreamDetected(Exception):
    """Raised when a live stream is detected but not allowed."""


YOUTUBE_LIVE_PATTERN = re.compile(
    r"^(?P<scheme>https?://)?(?P<sub>www\.)?youtube\.com/live/(?P<video_id>[a-zA-Z0-9_-]{11})"
)


def is_live_content(info: dict) -> bool:
    live_status = info.get("live_status")
    if live_status in {"is_live", "is_upcoming"}:
        return True
    return bool(info.get("is_live")) or bool(info.get("is_upcoming"))


def read_source_file(source_path: Path) -> List[str]:
    with source_path.open(encoding="utf-8") as src:
        return [line.strip() for line in src if line.strip()]


def ensure_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if not os.access(directory, os.W_OK):
        raise PermissionError(f"書き込み権限がありません: {directory}")


def validate_source(source_path: Path) -> List[str]:
    if not source_path.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {source_path}")
    urls = read_source_file(source_path)
    if not urls:
        raise ValueError("source.csv に処理対象の URL がありません")
    return urls


def process_urls(
    urls: Iterable[str],
    stage_names: StageNames,
    download_func: DownloadFunc,
    success_template: str,
) -> None:
    for url in urls:
        identifier = url or "<EMPTY>"
        stage_label = "未開始"
        output_file: Optional[Path] = None
        try:
            print(f"=== Processing id: {identifier} ===")

            stage_label = stage_names[0]
            print(f"[1/3] {stage_label}")
            if not url:
                print(f"[ERROR] URL が空です (id: {identifier})")
                continue

            stage_label = stage_names[1]
            print(f"[2/3] {stage_label}")
            try:
                output_file = download_func(url)
            except DownloadError:
                print(f"[ERROR] ダウンロードに失敗しました (id: {identifier})")
                continue

            stage_label = stage_names[2]
            print(f"[3/3] {stage_label}")
            if not output_file or not output_file.exists():
                print(f"[ERROR] 出力ファイルが見つかりません (id: {identifier})")
                continue

            print(success_template.format(path=output_file))
        except LiveStreamDetected:
            print(f"[WARN] ライブ配信を検出したためスキップしました (id: {identifier})")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] 予期しないエラーが発生しました (id: {identifier})")
            print(f"  stage: {stage_label}")
            print(f"  detail: {exc}")


def normalize_url(url: str) -> str:
    match = YOUTUBE_LIVE_PATTERN.match(url.strip())
    if not match:
        return url
    video_id = match.group("video_id")
    return f"https://www.youtube.com/watch?v={video_id}"


def build_audio_downloader(output_dir: Path, skip_live: bool) -> DownloadFunc:
    def _download(url: str) -> Path:
        normalized = normalize_url(url)
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(normalized, download=False)
            if skip_live and is_live_content(info):
                raise LiveStreamDetected

            expected = Path(ydl.prepare_filename(info)).with_suffix(".mp3")
            if expected.exists():
                print(f"[INFO] 既存ファイルを再利用します: {expected}")
                return expected

            result = ydl.process_ie_result(info, download=True)
            downloaded = Path(ydl.prepare_filename(result)).with_suffix(".mp3")

        return downloaded

    return _download


def build_video_downloader(output_dir: Path, skip_live: bool) -> DownloadFunc:
    def _download(url: str) -> Path:
        normalized = normalize_url(url)
        opts = {
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }
            ],
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(normalized, download=False)
            if skip_live and is_live_content(info):
                raise LiveStreamDetected

            expected = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
            if expected.exists():
                print(f"[INFO] 既存ファイルを再利用します: {expected}")
                return expected

            result = ydl.process_ie_result(info, download=True)
            downloaded = Path(ydl.prepare_filename(result)).with_suffix(".mp4")

        return downloaded

    return _download


def run_audio_command(source: Path, output_dir: Path, skip_live: bool) -> int:
    try:
        urls = validate_source(source)
        ensure_directory(output_dir)
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    process_urls(
        urls,
        ("入力ファイルのチェック", "mp3 変換処理", "出力ファイルの確認"),
        build_audio_downloader(output_dir, skip_live),
        "[OK] 変換完了: {path}",
    )
    return 0


def run_video_command(source: Path, output_dir: Path, skip_live: bool) -> int:
    try:
        urls = validate_source(source)
        ensure_directory(output_dir)
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    process_urls(
        urls,
        ("入力ファイルのチェック", "動画ダウンロード処理", "出力ファイルの確認"),
        build_video_downloader(output_dir, skip_live),
        "[OK] ダウンロード完了: {path}",
    )
    return 0


def list_mp3_files(directory: Path) -> List[Path]:
    if not directory.exists():
        raise FileNotFoundError(f"入力ディレクトリ {directory} が見つかりません")
    return sorted(p for p in directory.glob("*.mp3") if p.is_file())


def run_transcribe_command(
    audio_dir: Path,
    transcripts_dir: Path,
    model_name: str,
    verbose: bool,
) -> int:
    if whisper is None:
        print("[ERROR] whisper がインストールされていません。`pip install openai-whisper` を実行してください。")
        return 1

    print("=== Transcription start ===")
    try:
        mp3_files = list_mp3_files(audio_dir)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not mp3_files:
        print(f"[WARN] {audio_dir}/ に mp3 ファイルがありません")
        return 0

    try:
        ensure_directory(transcripts_dir)
    except PermissionError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[INFO] Whisper モデル ({model_name}) をロード中...")
    model = whisper.load_model(model_name)

    for mp3_file in mp3_files:
        stage_label = "未開始"
        transcript_path = transcripts_dir / f"{mp3_file.stem}.txt"
        try:
            print(f"=== Transcribing: {mp3_file} ===")

            stage_label = "入力ファイルの存在確認"
            print("[1/3] 入力ファイルの存在確認")
            if not mp3_file.exists():
                print(f"[ERROR] 入力ファイルが見つかりません (file: {mp3_file})")
                continue

            stage_label = "Whisper による文字起こし"
            print("[2/3] Whisper による文字起こし")
            try:
                result = model.transcribe(str(mp3_file), verbose=verbose)
                text = result.get("text", "").strip()
            except Exception:
                print(f"[ERROR] 文字起こしに失敗しました (file: {mp3_file})")
                continue

            stage_label = "出力ファイルの保存"
            print("[3/3] 出力ファイルの保存")
            try:
                transcript_path.write_text(text, encoding="utf-8")
            except Exception:
                print(f"[ERROR] 文字起こし結果の保存に失敗しました (file: {mp3_file})")
                continue

            print(f"[OK] Transcription complete: {transcript_path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] 予期しないエラーが発生しました (file: {mp3_file})")
            print(f"  stage: {stage_label}")
            print(f"  detail: {exc}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube ダウンロード / 文字起こし CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audio_parser = subparsers.add_parser("audio", help="source.csv をもとに MP3 を生成する")
    audio_parser.add_argument("--source", type=Path, default=SOURCE_FILE, help="入力 CSV のパス")
    audio_parser.add_argument("--output", type=Path, default=AUDIO_DIR, help="MP3 の出力ディレクトリ")
    audio_parser.add_argument("--skip-live", action="store_true", help="ライブ配信 URL を事前検知してスキップする")

    video_parser = subparsers.add_parser("video", help="source.csv をもとに MP4 を生成する")
    video_parser.add_argument("--source", type=Path, default=SOURCE_FILE, help="入力 CSV のパス")
    video_parser.add_argument("--output", type=Path, default=VIDEO_DIR, help="MP4 の出力ディレクトリ")
    video_parser.add_argument("--skip-live", action="store_true", help="ライブ配信 URL を事前検知してスキップする")

    transcribe_parser = subparsers.add_parser("transcribe", help="audio ディレクトリの MP3 を文字起こしする")
    transcribe_parser.add_argument("--audio-dir", type=Path, default=AUDIO_DIR, help="入力 MP3 ディレクトリ")
    transcribe_parser.add_argument("--transcripts-dir", type=Path, default=TRANSCRIPTS_DIR, help="文字起こし結果の出力ディレクトリ")
    transcribe_parser.add_argument("--model", default=WHISPER_MODEL, help="Whisper モデル名")
    transcribe_parser.add_argument("--quiet", action="store_true", help="Whisper の詳細ログを非表示にする")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "audio":
        return run_audio_command(args.source, args.output, args.skip_live)
    if args.command == "video":
        return run_video_command(args.source, args.output, args.skip_live)
    if args.command == "transcribe":
        verbose = not args.quiet
        return run_transcribe_command(args.audio_dir, args.transcripts_dir, args.model, verbose)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
