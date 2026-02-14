# yt-dlp gui

a simple gui wrapper around yt-dlp that handles common download issues like 404 errors, region blocks, and bot detection. it auto-retries with hls fallback when direct links fail.

## what it does

- uses browser cookies to bypass bot detection
- spoofs user-agent and referer headers
- geo-bypass and ssl bypass built in
- auto fallback to hls (m3u8) format on 404/412 errors
- merges video+audio into mp4

## install

you need python 3.8+ and yt-dlp installed on your system.

```
pip install -r requirements.txt
```

make sure yt-dlp is also available:

```
pip install yt-dlp
```

or install it through your package manager.

## run

```
python main.py
```

## usage

1. paste a video url
2. pick which browser to grab cookies from (firefox by default, works with zen browser too since its firefox based)
3. choose output folder if you want something other than ~/Downloads
4. hit download

if the download gets a 404 or 412 error, it automatically retries using hls streaming format.

## notes

- "none" in the browser dropdown skips cookie usage
- the format field defaults to "bv*+ba/b" which grabs best video + best audio
- you can change it to whatever yt-dlp format string you want
- logs show the raw yt-dlp output at the bottom

## dependencies

- yt-dlp
- customtkinter
