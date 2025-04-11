from flask import Flask, Response, send_from_directory
from urllib.parse import unquote
import os
from podgen import Podcast, Episode, Media, Person
from datetime import timedelta
from video_processor import (
    get_youtube_url,
    get_playlist_info,
    get_video_info,
    process_video,
    EPISODES_DIR,
    BASE_URL,
    logger
)
from filelock import FileLock, Timeout
import os.path

# Add near top of file with other imports
LOCK_DIR = 'cache'
os.makedirs(LOCK_DIR, exist_ok=True)

app = Flask(__name__)

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
            # Set publication_date to a datetime object parsed from the string with format YYYYMMDD
            publication_date=f"{video.upload_date}T00:00:00+00:00",
        ))
        logger.info(f"Added episode {video.id} to RSS feed")

    try:
        rss_xml = podcast.rss_str()
        logger.info("RSS generation complete")
        return Response(rss_xml, mimetype='application/rss+xml')
    except ValueError as e:
        logger.error(f"RSS generation failed: {str(e)}")
        return Response(f"Error generating RSS feed: {str(e)}", status=500)

@app.route('/episodes/<filename>')
def serve_episode(filename):
    if not filename.endswith('_clean.mp3'):
        return Response("Invalid file format requested", status=400)

    video_id = filename.replace('_clean.mp3', '')
    lock_path = os.path.join(LOCK_DIR, f'{video_id}.lock')
    
    # Check both possible file formats
    clean_mp3 = os.path.join(EPISODES_DIR, f'{video_id}_clean.mp3')
    clean_m4a = os.path.join(EPISODES_DIR, f'{video_id}_clean.m4a')
    
    # Prefer MP3 if exists, fall back to M4A
    if os.path.exists(clean_mp3) and os.path.getsize(clean_mp3) > 0:
        return send_from_directory(EPISODES_DIR, filename)
    elif os.path.exists(clean_m4a) and os.path.getsize(clean_m4a) > 0:
        return send_from_directory(EPISODES_DIR, f'{video_id}_clean.m4a')

    # Process if neither exists
    lock = FileLock(lock_path, timeout=300)  # Wait up to 5 minutes
    try:
        with lock:
            # Double-check after acquiring lock
            if os.path.exists(clean_mp3) and os.path.getsize(clean_mp3) > 0:
                return send_from_directory(EPISODES_DIR, filename)
            elif os.path.exists(clean_m4a) and os.path.getsize(clean_m4a) > 0:
                return send_from_directory(EPISODES_DIR, f'{video_id}_clean.m4a')
            
            logger.info(f"Audio for {video_id} not found, processing now")
            audio_path = process_video(video_id)
            if not audio_path:
                return Response(f"Error processing audio for {video_id}", status=500)
            
            # Return whichever format was created
            return send_from_directory(EPISODES_DIR, os.path.basename(audio_path))
    except Timeout:
        return Response("Timed out waiting for file processing to complete", status=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)