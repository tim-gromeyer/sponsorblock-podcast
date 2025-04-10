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

def get_duration(audio_path):
    """Get audio duration using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        logger.error(f"Error getting duration: {e.stderr}")
        raise
    except ValueError:
        logger.error("Invalid duration value")
        raise

def process_video(video_id):
    """Process video with optimized downloading and slicing."""
    clean_audio_path = os.path.join(EPISODES_DIR, f'{video_id}_clean.mp3')
    
    if os.path.exists(clean_audio_path) and os.path.getsize(clean_audio_path) > 0:
        logger.info(f"Using existing clean audio for {video_id}")
        return clean_audio_path

    try:
        audio_path = None
        # Check for existing downloaded files
        for f in os.listdir(EPISODES_DIR):
            if f.startswith(f'{video_id}.') and not f.endswith('_clean.mp3'):
                candidate = os.path.join(EPISODES_DIR, f)
                if os.path.getsize(candidate) > 0:
                    audio_path = candidate
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
                
            if not os.path.exists(audio_path):
                for f in os.listdir(EPISODES_DIR):
                    if f.startswith(f'{video_id}.'):
                        audio_path = os.path.join(EPISODES_DIR, f)
                        break

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
        total_duration = get_duration(audio_path)
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

        os.remove(audio_path)
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
            current_videos = info.get('entries', [])
            playlist_title = info.get('title', 'Sponsor-Free Podcast')
            playlist_description = info.get('description', 'A podcast feed with sponsor segments removed')
            playlist_author = info.get('uploader', 'Unknown')
            thumbnails = info.get('thumbnails', [])

            # Select the highest resolution thumbnail and clean the URL
            thumbnail_url = thumbnails[-1]['url'] if thumbnails else '' # TODO: self host the thumbnail, itnues doesn't support query params, but the thumbnail URL needs them

            # Cache videos
            cache = load_cache(VIDEO_METADATA_CACHE, {})
            for video in current_videos:
                video_id = video['id']
                if video_id not in cache:
                    video_thumbnails = video.get('thumbnails', [])
                    video_info = {
                        'title': video.get('title', f"Video {video_id}"),
                        'description': video.get('description', "No description available"),
                        'thumbnail': clean_thumbnail_url(video_thumbnails[-1]['url'] if video_thumbnails else ''),
                        'duration': video.get('duration', 0)
                    }
                    cache[video_id] = video_info

            video_ids = {v['id'] for v in current_videos}
            save_cache(VIDEO_METADATA_CACHE, cache)

            return playlist_title, playlist_description, playlist_author, thumbnail_url, video_ids
    except Exception as e:
        return "Sponsor-Free Podcast", "Error fetching playlist info", "", "", []

def get_video_info(video_id, force_update=False):
    """Fetch metadata for a single video with caching, including thumbnails."""
    cache = load_cache(VIDEO_METADATA_CACHE, {})
    if video_id in cache and not force_update:
        return cache[video_id]

    try:
        with yt_dlp.YoutubeDL({'quiet': False}) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
            thumbnails = info.get('thumbnails', [])
            # Select the highest resolution thumbnail and clean the URL
            thumbnail_url = clean_thumbnail_url(thumbnails[-1]['url'] if thumbnails else '')

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

    playlist_title, playlist_description, playlist_author, playlist_thumbnail, videos_ids = get_playlist_info(yt_url)
    if len(videos_ids) == 0:
        return Response("Error: No videos found in playlist", status=500)

    podcast = Podcast(
        name=playlist_title,
        website=BASE_URL,
        description=playlist_description or "No description available",
        explicit=False,
        image=playlist_thumbnail,
        authors=[Person(playlist_author)]
    )

    for video_id in videos_ids:
        video_info = get_video_info(video_id)
        audio_url = f'{BASE_URL}episodes/{video_id}_clean.mp3'
        estimated_size = video_info['duration'] * 24000 if video_info['duration'] else 0

        podcast.episodes.append(Episode(
            id=video_id,
            title=video_info['title'],
            summary=video_info.get('description', "No description available"),
            image=video_info['thumbnail'],  # Use video-specific thumbnail
            media=Media(audio_url,
                        estimated_size,
                        type='audio/mpeg',
                        duration=timedelta(seconds=video_info.get('duration', 0)),
                        ),
            link=f'https://www.youtube.com/watch?v={video_id}',
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