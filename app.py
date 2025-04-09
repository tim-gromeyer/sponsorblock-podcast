from flask import Flask, Response, send_from_directory
from urllib.parse import unquote
import yt_dlp
import requests
from pydub import AudioSegment
from podgen import Podcast, Episode, Media
import os
import logging
import traceback
import json
import time

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EPISODES_DIR = 'episodes'
CACHE_DIR = 'cache'
BASE_URL = 'http://localhost:5000/'
os.makedirs(EPISODES_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# Cache file paths
PLAYLIST_CACHE_FILE = os.path.join(CACHE_DIR, 'playlist_cache.json')
VIDEO_METADATA_CACHE = os.path.join(CACHE_DIR, 'video_metadata.json')

def load_cache(file_path, default=None):
    """Load cache from file if it exists."""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading cache {file_path}: {str(e)}")
    return default if default is not None else {}

def save_cache(file_path, data):
    """Save data to cache file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Error saving cache {file_path}: {str(e)}")

def process_video(video_id):
    """Process a video: download audio, remove sponsored segments, and save the cleaned audio."""
    clean_audio_path = os.path.join(EPISODES_DIR, f'{video_id}_clean.mp3')
    if os.path.exists(clean_audio_path) and os.path.getsize(clean_audio_path) > 0:
        logger.info(f"Using existing clean audio for {video_id}")
        return clean_audio_path

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(EPISODES_DIR, f'{video_id}.%(ext)s'),
            'quiet': False,
            'http_headers': {'User-Agent': 'Mozilla/5.0'},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
        audio_path = os.path.join(EPISODES_DIR, f'{video_id}.mp3')

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise Exception(f"Audio file for {video_id} is missing or empty")
        logger.info(f"Downloaded podcast: {audio_path}")

        response = requests.get(f'https://sponsor.ajay.app/api/skipSegments?videoID={video_id}', timeout=10)
        segments = response.json() if response.status_code == 200 else []

        logger.info(f"Beginning to remove {len(segments)} segments from audio...")
        audio = AudioSegment.from_mp3(audio_path)
        cleaned_audio = AudioSegment.empty()
        start = 0
        for segment in segments:
            end = int(segment['segment'][0] * 1000)
            if end > start:
                cleaned_audio += audio[start:end]
            start = int(segment['segment'][1] * 1000)
        if start < len(audio):
            cleaned_audio += audio[start:]

        cleaned_audio.export(clean_audio_path, format='mp3')
        os.remove(audio_path)
        logger.info(f"Successfully processed {video_id}")
        return clean_audio_path
    except Exception as e:
        logger.error(f"Error processing video {video_id}: {str(e)}\n{traceback.format_exc()}")
        return None

def get_playlist_info(yt_url):
    """Fetch metadata for all videos in a playlist or channel with caching."""
    cache = load_cache(PLAYLIST_CACHE_FILE, {})
    cached_entry = cache.get(yt_url, {})
    cached_videos = cached_entry.get('videos', [])
    physical_mental = cached_entry.get('videos', [])
    last_updated = cached_entry.get('last_updated', 0)

    try:
        with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': False}) as ydl:
            info = ydl.extract_info(yt_url, download=False)
            current_videos = info.get('entries', [])
            playlist_title = info.get('title', 'Sponsor-Free Podcast')
            playlist_description = info.get('description', 'A podcast feed with sponsor segments removed')

            # Merge cached videos with new ones
            video_ids = {v['id'] for v in current_videos}
            updated_videos = cached_videos + [v for v in current_videos if v['id'] not in {cv['id'] for cv in cached_videos}]

            cache[yt_url] = {
                'title': playlist_title,
                'description': playlist_description,
                'videos': updated_videos,
                'last_updated': int(time.time())
            }
            save_cache(PLAYLIST_CACHE_FILE, cache)
            return playlist_title, playlist_description, updated_videos
    except Exception as e:
        logger.error(f"Failed to extract info for {yt_url}: {str(e)}")
        if cached_videos:  # Fall back to cache if available
            return cached_entry.get('title', 'Sponsor-Free Podcast'), cached_entry.get('description', 'Cached podcast feed'), cached_videos
        return "Sponsor-Free Podcast", "Error fetching playlist info", []

def get_video_info(video_id):
    """Fetch metadata for a single video with caching."""
    cache = load_cache(VIDEO_METADATA_CACHE, {})
    if video_id in cache:
        return cache[video_id]

    try:
        with yt_dlp.YoutubeDL({'quiet': False}) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
            thumbnails = info.get('thumbnails', [])
            thumbnail_url = next((t['url'] for t in thumbnails if t['url'].endswith(('.jpg', '.png'))), thumbnails[0]['url'] if thumbnails else '')
            video_info = {
                'title': info.get('title', f"Video {video_id}"),
                'description': info.get('description', "No description available"),
                'thumbnail': thumbnail_url,
                'duration': info.get('duration', 0)
            }
            cache[video_id] = video_info
            save_cache(VIDEO_METADATA_CACHE, cache)
            return video_info
    except Exception as e:
        logger.error(f"Error fetching info for {video_id}: {str(e)}")
        return {
            'title': f"Video {video_id}",
            'description': "Error fetching description",
            'thumbnail': '',
            'duration': 0
        }

@app.route('/<path:yt_url>/podcast.rss')
def generate_rss(yt_url):
    yt_url = unquote(yt_url)
    logger.info(f"Generating RSS for {yt_url}")

    playlist_title, playlist_description, videos = get_playlist_info(yt_url)
    if not videos:
        return Response("Error: No videos found in playlist", status=500)

    podcast = Podcast(
        name=playlist_title,
        website=BASE_URL,
        description=playlist_description,
        explicit=False
    )

    for video in videos:
        video_id = video.get('id')
        if not video_id:
            logger.warning("Skipping video with no ID")
            continue

        video_info = get_video_info(video_id)
        audio_url = f'{BASE_URL}episodes/{video_id}_clean.mp3'
        estimated_size = video_info['duration'] * 24000 if video_info['duration'] else 0

        podcast.episodes.append(Episode(
            title=video_info['title'],
            summary=video_info['description'],
            image=video_info['thumbnail'],
            media=Media(audio_url, estimated_size, type='audio/mpeg')
        ))
        logger.info(f"Added episode {video_id} to RSS feed")

    try:
        rss_xml = podcast.rss_str()
        logger.info("RSS generation complete")
        return Response(rss_xml, mimetype='application/rss+xml')
    except ValueError as e:
        logger.error(f"RSS generation failed: {str(e)}\n{traceback.format_exc()}")
        return Response(f"Error generating RSS feed: {str(e)}", status=500)

@app.route('/episodes/<filename>')
def serve_episode(filename):
    video_id = filename.replace('_clean.mp3', '')
    clean_audio_path = os.path.join(EPISODES_DIR, f'{video_id}_clean.mp3')

    if not os.path.exists(clean_audio_path) or os.path.getsize(clean_audio_path) == 0:
        logger.info(f"Audio for {video_id} not found, processing now")
        audio_path = process_video(video_id)
        if not audio_path:
            return Response(f"Error processing audio for {video_id}", status=500)

    return send_from_directory(EPISODES_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
