# 🎙️ sponsorblock-podcast

**Turn YouTube playlists into sponsor-free podcasts. Zero config. No YouTube API key.**

## 🚀 What is this?

`sponsorblock-podcast` is a lightweight Flask-based tool that:
- Downloads audio from YouTube playlists or channels
- Automatically removes sponsored segments using the SponsorBlock API
- Generates an RSS feed to use in any podcast player

All of this **without requiring any API keys**, manual playlist setup, or complex configuration.

## 🧠 Why it’s special

Most tools that deal with YouTube:
- Require Google API keys or authentication
- Need manual editing to remove unwanted content
- Aren't podcast-player-friendly

This project is:
- 🔌 Plug & Play — drop a YouTube playlist URL into your RSS reader
- 🧼 Sponsor-free — powered by the SponsorBlock community
- 🐳 Dockerized — run everything with a single command

## 🛠️ Usage

### 1. Clone the repo
```bash
git clone https://github.com/yourname/sponsorblock-podcast.git
cd sponsorblock-podcast
```

### 2. Run with Docker Compose
```bash
docker-compose up
```

### 3. Access your feed
Navigate to:
```
http://localhost:5000/<YOUTUBE_PLAYLIST_OR_CHANNEL_URL_ENCODED>/podcast.rss
```
Example:
```
http://localhost:5000/https%3A%2F%2Fwww.youtube.com%2Fplaylist%3Flist%3DPLxyz/podcast.rss
```

## ⚠️ Disclaimer

- For personal use only. Downloading content may be subject to YouTube’s terms of service.
- Audio files and metadata are cached locally.
- Use responsibly and do not overload SponsorBlock or YouTube.

---

Happy listening, without the interruptions. 🎧
