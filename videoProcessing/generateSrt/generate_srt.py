import argparse
from pathlib import Path

from colorama import init, Fore, Style

from videoProcessing.generateSrt.extract_audio import extract_audio
from videoProcessing.generateSrt.transcribe_client import transcribe_movie

init(autoreset=True)

SUPPORTED_VIDEO_EXT = {"mp4", "m4v", "mkv", "avi"}


def find_videos(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED_VIDEO_EXT
    )


def process_folder(folder: Path, host="localhost:10000", language=None):
    videos = find_videos(folder)
    todo = [v for v in videos if not v.with_suffix(".srt").exists()]
    skipped = len(videos) - len(todo)

    print(f"{Fore.CYAN}Found {len(videos)} video(s); {len(todo)} need subtitles"
          f"{f' ({skipped} already have a .srt, skipped)' if skipped else ''}.{Style.RESET_ALL}")

    failures = []
    for i, video in enumerate(todo, 1):
        print(f"\n{Fore.YELLOW}[{i}/{len(todo)}] {video.name}{Style.RESET_ALL}")
        audio_path = None
        try:
            audio_path = extract_audio(video)
            result = transcribe_movie(host, str(audio_path), language=language)
            if result.get("status") != "done":
                print(f"    {Fore.RED}Failed: {result}{Style.RESET_ALL}")
                failures.append(video)
                continue
            video.with_suffix(".srt").write_text(result["srt"], encoding="utf-8")
        except Exception as e:
            print(f"    {Fore.RED}Failed: {e}{Style.RESET_ALL}")
            failures.append(video)
        finally:
            if audio_path and Path(audio_path).exists():
                Path(audio_path).unlink()

    print(f"\n{Fore.GREEN}Done. {len(todo) - len(failures)}/{len(todo)} succeeded.{Style.RESET_ALL}")
    if failures:
        print(f"{Fore.RED}Failed:{Style.RESET_ALL}")
        for f in failures:
            print(f"  - {f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate .srt subtitles for every video in a folder (recursively) via the running CyanManager STT service."
    )
    parser.add_argument("folder", help="Folder to scan for videos")
    parser.add_argument("--host", default="localhost:10000", help="host:port of the CyanManager server")
    parser.add_argument("--language", default=None, help="Force the source language (e.g. 'de')")
    args = parser.parse_args()

    process_folder(Path(args.folder), host=args.host, language=args.language)
    input("\nPress Enter to exit...")
