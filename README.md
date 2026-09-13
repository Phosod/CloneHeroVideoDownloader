# Clone Hero Video Downloader — maintained fix

This is a modernization of `stripedew/CloneHeroVideoDownloader` focused on restoring YouTube search/download support.

## Why the old version fails

The original script uses `youtube-search-python`, which was archived in 2022, and assumes every search returns at least two entries. That causes `list index out of range` when YouTube search returns fewer results.

Modern YouTube downloads also require a current `yt-dlp` setup. Current yt-dlp uses its EJS challenge solver and a supported JavaScript runtime; Deno is the recommended runtime.

## Changes in this version

- Removed `youtube-search-python`; yt-dlp now performs both search and download.
- Uses `artist` + `name` from `song.ini` for cleaner searches instead of pack numbers/charter tags in folder names.
- Handles zero, one, or many search results without crashing.
- Tries up to three search candidates before skipping a song.
- Uses `pathlib` instead of hard-coded Windows `\\songs` paths.
- Downloads replacements to a temporary file and only swaps `video.mp4` in after success, so replace mode no longer deletes a good video before a new one is ready.
- Updates only `video_start_time` rather than rewriting the entire `song.ini` through ConfigParser.
- Gives a targeted hint for current YouTube sign-in/precondition failures.

## Windows setup

Use Python 3.10 or newer.

```powershell
py -m pip install -U -r requirements.txt
```

Install Deno and make sure `deno --version` works in a new terminal. Deno is recommended by yt-dlp for current YouTube support.

1080p mode also needs the real `ffmpeg` executable in PATH. The Python `ffmpeg-python` package is not a substitute for the executable.

Then place/run this project one level above your Clone Hero `Songs` folder:

```powershell
py VideoDownload.py
```

## Troubleshooting

Check the versions visible to the same terminal that runs the script:

```powershell
py -m yt_dlp --version
deno --version
ffmpeg -version
```

If YouTube still reports that you must sign in or that a precondition check failed, update the Python packages again and confirm Deno is available in PATH.

## Attribution

Inspired by the public project `stripedew/CloneHeroVideoDownloader`. This repository contains a rewritten implementation rather than a verbatim copy of the upstream source.
