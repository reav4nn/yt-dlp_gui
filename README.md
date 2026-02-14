# yt-dlp gui

a simple gui wrapper around yt-dlp that handles common download issues like 404 errors, region blocks, and bot detection. auto-retries with multiple fallback strategies when direct links fail.

## what it does

- uses browser cookies to bypass bot detection
- spoofs user-agent, referer, origin and browser headers
- geo-bypass and ssl bypass built in
- 4-stage retry chain: default, hls, ffmpeg downloader, hls+ffmpeg+throttle
- merges video+audio into mp4

## dependencies

you need these installed on your system:

- python 3.8+
- yt-dlp
- ffmpeg (used as fallback downloader)
- tkinter (python-tk)

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
