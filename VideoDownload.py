from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


TITLE_NOISE = (
    "(2x Bass Pedal Expert+)",
    "(2x Bass Pedal)",
    "(RB3 version)",
    "RB3",
    "(Rh)",
)


def find_songs_folder(base: Path) -> Path | None:
    """Find the Clone Hero Songs folder from the run directory or its parent."""
    base = base.resolve()

    if base.is_dir() and base.name.lower() == "songs":
        return base

    search_roots = [base]
    if base.parent != base:
        search_roots.append(base.parent)

    for root in search_roots:
        for name in ("Songs", "songs"):
            candidate = root / name
            if candidate.is_dir():
                return candidate.resolve()

    return None


def read_song_metadata(song_ini: Path) -> tuple[str | None, str | None]:
    """Read artist/name from song.ini without rewriting or normalizing the whole file."""
    try:
        text = song_ini.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None, None

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//", "[")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key in {"artist", "name"} and value:
            values[key] = value

    return values.get("artist"), values.get("name")


def clean_folder_title(folder_name: str) -> str:
    title = folder_name.strip()
    title = re.sub(r"^\s*\d+\s*[.\-_)]+\s*", "", title)
    title = re.sub(r"\s*\[[^\]]+\]\s*$", "", title)
    for noise in TITLE_NOISE:
        title = title.replace(noise, "")
    return re.sub(r"\s{2,}", " ", title).strip(" -")


def build_search_query(song_ini: Path) -> str:
    artist, name = read_song_metadata(song_ini)
    if artist and name:
        base = f"{artist} - {name}"
    elif name:
        base = name
    else:
        base = clean_folder_title(song_ini.parent.name)
    return f"{base} official music video"


def search_youtube(query: str, limit: int = 5) -> list[dict[str, str]]:
    """Search YouTube through yt-dlp."""
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed")

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

    entries = (info or {}).get("entries") or []
    results: list[dict[str, str]] = []

    for entry in entries:
        if not entry:
            continue
        video_id = entry.get("id")
        url = entry.get("webpage_url") or entry.get("url")
        if video_id and (not url or not str(url).startswith(("http://", "https://"))):
            url = f"https://www.youtube.com/watch?v={video_id}"
        if not url:
            continue
        results.append(
            {
                "url": str(url),
                "title": str(entry.get("title") or video_id or url),
            }
        )

    return results


def _format_selector(quality: str) -> str:
    """Pick broadly available formats while limiting resolution."""
    max_height = 720 if quality == "720p" else 1080
    return (
        f"bv*[height<=?{max_height}]+ba/"
        f"b[height<=?{max_height}]/"
        "bv*+ba/b"
    )


def _cleanup_temp_files(song_dir: Path) -> None:
    for path in song_dir.glob(".__chvd_tmp__*"):
        try:
            path.unlink()
        except OSError:
            pass


def download_candidate(song_dir: Path, url: str, quality: str) -> None:
    """Download one candidate, merge/remux to MP4, then replace video.mp4."""
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed")

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError(
            "FFmpeg/ffprobe are required. Install them with: "
            "winget install --id Gyan.FFmpeg -e"
        )

    _cleanup_temp_files(song_dir)

    options: dict[str, Any] = {
        "outtmpl": str(song_dir / ".__chvd_tmp__.%(ext)s"),
        "format": _format_selector(quality),
        "format_sort": [
            "vcodec:h264",
            "acodec:aac",
            "lang",
            "quality",
            "res",
            "fps",
            "hdr:12",
        ],
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoRemuxer",
                "preferedformat": "mp4",
            }
        ],
        "noplaylist": True,
        "overwrites": True,
        "retries": 3,
        "fragment_retries": 3,
        "quiet": False,
        "no_warnings": False,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        temp_mp4 = song_dir / ".__chvd_tmp__.mp4"
        if not temp_mp4.exists():
            candidates = sorted(song_dir.glob(".__chvd_tmp__*"))
            raise RuntimeError(
                "yt-dlp completed but did not produce an MP4 file. "
                f"Temporary outputs: {[p.name for p in candidates]}"
            )

        os.replace(temp_mp4, song_dir / "video.mp4")
    finally:
        _cleanup_temp_files(song_dir)


def set_video_start_time(song_ini: Path, milliseconds: int = -3000) -> bool:
    """Update only video_start_time while preserving the rest of song.ini as-is."""
    try:
        text = song_ini.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return False

    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    pattern = re.compile(r"^(\s*video_start_time\s*=\s*).*$", re.IGNORECASE)

    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            lines[index] = f"{match.group(1)}{milliseconds}"
            break
    else:
        insert_at = None
        for index, line in enumerate(lines):
            if line.strip().lower() == "[song]":
                insert_at = index + 1
                break
        if insert_at is None:
            return False
        lines.insert(insert_at, f"video_start_time = {milliseconds}")

    try:
        song_ini.write_text(newline.join(lines) + newline, encoding="utf-8")
        return True
    except OSError:
        return False


def dependency_hints() -> list[str]:
    hints: list[str] = []
    if shutil.which("deno") is None:
        hints.append(
            "Deno was not found. Modern yt-dlp needs a supported JavaScript runtime "
            "for full YouTube support."
        )
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        hints.append(
            "FFmpeg/ffprobe were not found. Install them with: "
            "winget install --id Gyan.FFmpeg -e"
        )
    return hints


def explain_youtube_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "sign in" in lowered or "precondition check failed" in lowered or "bot" in lowered:
        return (
            f"{message}\n"
            "YouTube rejected the request. Update yt-dlp[default] and make sure Deno "
            "is installed and available in PATH."
        )
    if "requested format is not available" in lowered:
        return (
            f"{message}\n"
            "The video did not expose a compatible format with the current selector. "
            "Make sure this repo is up to date and FFmpeg is installed."
        )
    return message


def choose_mode() -> tuple[str, bool] | None:
    print(
        "Type the number to pick from the following options:\n"
        "1. Default quality (up to 720p)\n"
        "2. Best quality (up to 1080p, where available)\n"
        "3. Replace existing videos with up to 1080p\n"
    )
    choice = input("Pick between 1-3: ").strip()
    if choice == "1":
        return "720p", False
    if choice == "2":
        return "1080p", False
    if choice == "3":
        return "1080p", True
    print("You must choose between 1-3.")
    return None


def main() -> int:
    if yt_dlp is None or tqdm is None:
        print("Missing Python dependencies. Run: python -m pip install -U -r requirements.txt")
        return 2

    print(f"yt-dlp version: {getattr(getattr(yt_dlp, 'version', None), '__version__', 'unknown')}")
    for hint in dependency_hints():
        print(f"WARNING: {hint}")

    print("Checking for Songs folder...")
    songs_folder = find_songs_folder(Path.cwd())
    if songs_folder is None:
        print(
            "Did not detect a 'Songs' folder. Run this from the Clone Hero drive root "
            "or from the CloneHeroVideoDownloader folder beside Songs."
        )
        return 2

    print(f"Songs folder: {songs_folder}")

    mode = choose_mode()
    if mode is None:
        return 2
    quality, replace_existing = mode

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print(
            "This version requires FFmpeg for reliable YouTube format handling.\n"
            "Install it with:\n"
            "  winget install --id Gyan.FFmpeg -e\n"
            "Then close/reopen PowerShell and run the downloader again."
        )
        return 2

    song_files = list(songs_folder.rglob("song.ini"))
    pending = [
        song_ini
        for song_ini in song_files
        if replace_existing or not (song_ini.parent / "video.mp4").exists()
    ]

    print(f"Found {len(song_files)} songs; {len(pending)} need video work.")
    errors: list[tuple[str, str]] = []

    with tqdm(total=len(pending), unit="videos") as progress:
        for song_ini in pending:
            song_name = song_ini.parent.name
            query = build_search_query(song_ini)
            print(f"\nLooking on YouTube for: {query}")

            try:
                results = search_youtube(query, limit=5)
            except Exception as exc:
                error = explain_youtube_error(exc)
                errors.append((song_name, error))
                print(f"Search failed for {song_name}: {error}")
                progress.update(1)
                continue

            if not results:
                message = "No YouTube search results were returned."
                errors.append((song_name, message))
                print(f"{message} Skipping {song_name}.")
                progress.update(1)
                continue

            success = False
            last_error = "No candidate succeeded."

            for result in results[:3]:
                print(f"Trying: {result['title']}")
                try:
                    download_candidate(song_ini.parent, result["url"], quality)
                    set_video_start_time(song_ini, -3000)
                    print("Song ready.")
                    success = True
                    break
                except Exception as exc:
                    last_error = explain_youtube_error(exc)
                    print(f"Candidate failed: {last_error}")

            if not success:
                errors.append((song_name, last_error))
                print(f"Error downloading song: {song_name}. Skipping.")

            progress.update(1)

    if errors:
        print("\nCompleted with errors:")
        for song_name, error in errors:
            print(f"- {song_name}: {error}")
    else:
        print("\nAll requested videos completed successfully.")

    print(f"Checked {len(song_files)} songs total.")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
