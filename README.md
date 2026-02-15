# yt-dlp gui

a simple gui wrapper around yt-dlp that handles common download issues like 404 errors, region blocks, and bot detection. auto-retries with multiple fallback strategies when direct links fail.

## what it does

- uses browser cookies to bypass bot detection
- spoofs user-agent, referer, origin and browser headers
- geo-bypass and ssl bypass built in
- 4-stage retry chain: default, hls, ffmpeg downloader, hls+ffmpeg+throttle
- merges video+audio into mp4

## dependencies

- python 3.8+
- yt-dlp
- ffmpeg (used as fallback downloader)
- tkinter (python-tk on linux)

### linux

on arch/manjaro:

```
sudo pacman -S python yt-dlp ffmpeg tk
```

on ubuntu/debian:

```
sudo apt install python3 python3-tk ffmpeg
pip install yt-dlp
```

on fedora:

```
sudo dnf install python3 python3-tkinter ffmpeg
pip install yt-dlp
```

then install the python deps:

```
pip install -r requirements.txt
```

### windows

1. install python from https://python.org (check "add to PATH" during install)

2. get yt-dlp.exe from https://github.com/yt-dlp/yt-dlp/releases/latest
   - download `yt-dlp.exe`
   - either drop it in the same folder as this app, or put it somewhere and add that folder to PATH

3. get ffmpeg from https://www.gyan.dev/ffmpeg/builds/
   - download the "essentials" build
   - extract it somewhere like `C:\ffmpeg`
   - add `C:\ffmpeg\bin` to your system PATH

4. to add something to PATH:
   - open settings > system > about > advanced system settings
   - click "environment variables"
   - under system variables, find "Path", click edit
   - click "new" and add the folder that has yt-dlp.exe (or ffmpeg.exe)
   - click ok and restart your terminal/app

5. install python deps:

```
pip install -r requirements.txt
```

the app also checks common locations automatically:
- same folder as the script
- `%LOCALAPPDATA%\yt-dlp\`
- `%USERPROFILE%\Downloads\`
- `C:\yt-dlp\`
- `C:\ffmpeg\bin\`

so if you just put yt-dlp.exe next to main.py, it should work without touching PATH.

important: make sure the file is actually named `yt-dlp.exe`, not `yt-dlp (1).exe` or anything like that.

if you installed yt-dlp via pip (`pip install yt-dlp`) instead of using the standalone exe, that works too. pip puts it in your python scripts folder which is usually already in PATH.

## run

```
python main.py
```

## usage

1. paste a video url
2. pick which browser to grab cookies from (firefox by default, works with zen browser too since its firefox based)
3. choose output folder if you want something other than ~/Downloads
4. hit download

if the download fails with 404 or 412, it automatically cycles through fallback strategies (hls format, ffmpeg downloader, throttled requests) until one works.

## notes

- "none" in the browser dropdown skips cookie usage
- the format field defaults to "bv*+ba/b" which grabs best video + best audio
- you can change it to whatever yt-dlp format string you want
- logs show the raw yt-dlp output at the bottom
- referer and origin are set to match the target site automatically
