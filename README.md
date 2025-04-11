# 🎧 SponsorBlock Podcast Generator

Convert YouTube playlists into sponsor-free podcasts with automated segment removal.

## 🎯 Features

- **Automatic Sponsor Removal**: Leverages the SponsorBlock API to cut out sponsored segments
- **No API Key Required**: Works without YouTube API credentials
- **Docker Ready**: Simple deployment with Docker Compose
- **Format Optimization**: Supports MP3 and M4A audio formats
- **Smart Caching**: Caches processed audio and metadata for faster delivery
- **RSS Feed Generation**: Creates podcast-compatible RSS feeds

## 🚀 Quick Start

1. Clone the repository:
```bash
git clone https://github.com/yourusername/sponsorblock-podcast.git
cd sponsorblock-podcast
```

2. Start with Docker Compose:
```bash
docker compose up -d
```

3. Access your podcast feed:
```
http://localhost:5000/YOUR_YOUTUBE_PLAYLIST_ID/podcast.rss
```

### 📝 Example URLs

- Playlist: `http://localhost:5000/PLE0hg-LdSfycrpTtMImPSqFLle4yYNzWD/podcast.rss`
- Channel: `http://localhost:5000/@ChannelName/podcast.rss`

## 🛠️ Development Setup

Requirements:
- Python 3.8+
- FFmpeg
- pip

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the development server:
```bash
python app.py
```

## 🔧 Configuration

The service uses these directories:
- `episodes/`: Processed audio files
- `cache/`: Metadata and playlist information

## ⚠️ Disclaimer

- This tool is intended for **personal use only**
- Using this tool may be subject to YouTube's Terms of Service
- Not affiliated with YouTube, Google, or SponsorBlock
- Please respect content creators' rights and YouTube's policies
- Use responsibly to avoid overloading external services

## 🔍 SEO Keywords

podcast generator, youtube to podcast, sponsor removal, sponsorblock integration, youtube playlist converter, podcast rss feed, youtube channel podcast, audio extraction, automated podcast creation, sponsor-free content

## 📄 License

MIT License - Copyright (c) 2025 Tim Gromeyer
