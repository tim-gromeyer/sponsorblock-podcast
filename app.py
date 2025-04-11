from flask import Flask, Response, send_from_directory
from urllib.parse import unquote
import yt_dlp
import requests
from podgen import Podcast, Episode, Media, Person
import os
import logging
import traceback
import json
from datetime import timedelta
import subprocess
from models import Video, Playlist

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
    """Process video with optimized downloading and slicing."""
    clean_audio_path = os.path.join(EPISODES_DIR, f'{video_id}_clean.mp3')
    
    if os.path.exists(clean_audio_path) and os.path.getsize(clean_audio_path) > 0:
        logger.info(f"Using existing clean audio for {video_id}")
        return clean_audio_path

    try:
        audio_path = None
        total_duration = None
        # Check for existing downloaded files
        for f in os.listdir(EPISODES_DIR):
            if f.startswith(f'{video_id}.') and not f.endswith('_clean.mp3'):
                candidate = os.path.join(EPISODES_DIR, f)
                if os.path.getsize(candidate) > 0:
                    audio_path = candidate
                    # Get duration from video metadata cache
                    cache = load_cache(VIDEO_METADATA_CACHE, {})
                    total_duration = cache.get(video_id, {}).get('duration', 0)
                    logger.info(f"Found existing audio file: {audio_path}")
                    break

        # Download if no existing file found
        if not audio_path:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(EPISODES_DIR, f'{video_id}.%(ext)s'),
                'quiet': False,
                'http_headers': {'User-Agent': 'Mozilla/5.0'},
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=True)
                audio_path = ydl.prepare_filename(info)
                total_duration = info.get('duration', 0)

        # Verify successful download
        if not audio_path or os.path.getsize(audio_path) == 0:
            raise ValueError(f"Download failed for {video_id}")

        # Get sponsor segments
        response = requests.get(
            f'https://sponsor.ajay.app/api/skipSegments?videoID={video_id}',
            timeout=10
        )
        segments = sorted(response.json(), key=lambda x: x['segment'][0]) if response.ok else []

        # Merge overlapping segments
        merged = []
        for seg in segments:
            if not merged:
                merged.append(seg)
            else:
                last = merged[-1]
                if seg['segment'][0] <= last['segment'][1]:
                    merged[-1]['segment'][1] = max(last['segment'][1], seg['segment'][1])
                else:
                    merged.append(seg)

        # Calculate keep intervals
        intervals = []
        prev_end = 0.0

        for seg in merged:
            start, end = seg['segment']
            if start > prev_end:
                intervals.append((prev_end, start))
            prev_end = max(prev_end, end)

        if prev_end < total_duration:
            intervals.append((prev_end, total_duration))

        # Process with ffmpeg
        if not intervals:
            logger.info("No segments to remove, converting to MP3")
            subprocess.run([
                'ffmpeg', '-y', '-i', audio_path,
                '-c:a', 'libmp3lame', '-q:a', '2', clean_audio_path
            ], check=True)
        else:
            filter_chain = []
            concat_inputs = []
            for i, (start, end) in enumerate(intervals):
                filter_chain.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[part{i}]")
                concat_inputs.append(f"[part{i}]")

            filter_complex = "; ".join(filter_chain) + "; " + \
                            "".join(concat_inputs) + \
                            f"concat=n={len(concat_inputs)}:v=0:a=1[out]"

            subprocess.run([
                'ffmpeg', '-y', '-i', audio_path,
                '-filter_complex', filter_complex,
                '-map', '[out]', '-c:a', 'libmp3lame', '-q:a', '2', clean_audio_path
            ], check=True)

        os.remove(audio_path, ignore_errors=True)
        logger.info(f"Successfully processed {video_id}")
        return clean_audio_path

    except Exception as e:
        logger.error(f"Error processing {video_id}: {str(e)}\n{traceback.format_exc()}")
        if audio_path and os.path.exists(audio_path):
            try: os.remove(audio_path)
            except: pass
        return None

def clean_thumbnail_url(url):
    """Remove query parameters from thumbnail URLs."""
    if not url:
        return ''
    return url.split('?')[0]

def get_playlist_info(yt_url):
    """Fetch metadata for all videos in a playlist or channel."""
    try:
        with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': False, 'skip_download': True}) as ydl:
            info = ydl.extract_info(yt_url, download=False)
            playlist = Playlist.from_yt_info(info)

            # Cache videos
            cache = load_cache(VIDEO_METADATA_CACHE, {})
            for video_entry in info.get('entries', []):
                video_id = video_entry['id']
                if video_id not in cache:
                    video_thumbnails = video_entry.get('thumbnails', [])
                    video_info = {
                        'title': video_entry.get('title', f"Video {video_id}"),
                        'description': video_entry.get('description', "No description available"),
                        'thumbnail': clean_thumbnail_url(video_thumbnails[-1]['url'] if video_thumbnails else ''),
                        'duration': video_entry.get('duration', 0)
                    }
                    cache[video_id] = video_info

            save_cache(VIDEO_METADATA_CACHE, cache)
            return playlist

    except Exception as e:
        return Playlist(
            title="Sponsor-Free Podcast",
            description="Error fetching playlist info",
            author="",
            thumbnail_url="",
            video_ids=set()
        )

def get_video_info(video_id, force_update=False) -> Video:
    """Fetch metadata for a single video with caching, including thumbnails."""
    cache = load_cache(VIDEO_METADATA_CACHE, {})
    if video_id in cache and not force_update:
        return Video.from_dict(video_id, cache[video_id])

    try:
        with yt_dlp.YoutubeDL({'quiet': False}) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
            thumbnails = info.get('thumbnails', [])
            video = Video(
                id=video_id,
                title=info.get('title', f"Video {video_id}"),
                description=info.get('description', "No description available"),
                thumbnail_url=clean_thumbnail_url(thumbnails[-1]['url'] if thumbnails else ''),
                duration=info.get('duration', 0)
            )
            
            cache[video_id] = {
                'title': video.title,
                'description': video.description,
                'thumbnail': video.thumbnail_url,
                'duration': video.duration
            }
            save_cache(VIDEO_METADATA_CACHE, cache)
            return video
            
    except Exception as e:
        logger.error(f"Error fetching info for {video_id}: {str(e)}")
        return Video(
            id=video_id,
            title=f"Video {video_id}",
            description="Error fetching description",
            thumbnail_url='',
            duration=0
        )

def get_youtube_url(identifier):
    """Convert various YouTube identifiers to full URLs."""
    identifier = identifier.strip('/')
    
    if identifier.startswith('@'):  # Channel handle
        return f'https://youtube.com/{identifier}'
    elif 'youtube.com' in identifier or 'youtu.be' in identifier:
        return identifier  # Already a full URL
    else:  # Assuming it's a playlist ID
        return f'https://youtube.com/playlist?list={identifier}'

@app.route('/<path:yt_identifier>/podcast.rss')
def generate_rss(yt_identifier):
    yt_identifier = unquote(yt_identifier)
    yt_url = get_youtube_url(yt_identifier)
    logger.info(f"Generating RSS for {yt_url}")

    playlist = get_playlist_info(yt_url)
    if not playlist.video_ids:
        return Response("Error: No videos found in playlist", status=500)

    podcast = Podcast(
        name=playlist.title,
        website=BASE_URL,
        description=playlist.description,
        explicit=False,
        image=playlist.thumbnail_url,
        authors=[Person(playlist.author)]
    )

    for video_id in playlist.video_ids:
        video = get_video_info(video_id)
        audio_url = f'{BASE_URL}episodes/{video.id}_clean.mp3'

        podcast.episodes.append(Episode(
            id=video.id,
            title=video.title,
            summary=video.description,
            image=video.thumbnail_url,
            media=Media(
                audio_url,
                video.estimated_size,
                type='audio/mpeg',
                duration=timedelta(seconds=video.duration),
            ),
            link=video.youtube_url,
        ))
        logger.info(f"Added episode {video.id} to RSS feed")

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