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
import os.path
from waitress import serve
import threading
import queue
import time

# Download queue and worker
download_queue = queue.Queue()
processing_set = set()

def download_worker():
    while True:
        video_id = download_queue.get()
        try:
            process_video(video_id)
        except Exception as e:
            logger.error(f"Error in download worker for {video_id}: {e}")
        finally:
            processing_set.discard(video_id)
            download_queue.task_done()

worker_thread = threading.Thread(target=download_worker, daemon=True)
worker_thread.start()

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

    # Add all videos to the download queue
    for video_id in playlist.video_ids:
        if video_id not in processing_set:
            processing_set.add(video_id)
            download_queue.put(video_id)

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
    
    clean_mp3 = os.path.normpath(os.path.join(EPISODES_DIR, f'{video_id}_clean.mp3'))
    clean_m4a = os.path.normpath(os.path.join(EPISODES_DIR, f'{video_id}_clean.m4a'))
    
    abs_episodes_dir = os.path.abspath(EPISODES_DIR)
    if not clean_mp3.startswith(abs_episodes_dir) or not clean_m4a.startswith(abs_episodes_dir):
        return Response("Invalid file path", status=400)
    
    if os.path.exists(clean_mp3) and os.path.getsize(clean_mp3) > 0:
        return send_from_directory(EPISODES_DIR, os.path.basename(clean_mp3))
    elif os.path.exists(clean_m4a) and os.path.getsize(clean_m4a) > 0:
        return send_from_directory(EPISODES_DIR, os.path.basename(clean_m4a))

    # Add to queue if not already processing
    if video_id not in processing_set:
        logger.info(f"Audio for {video_id} not found, adding to processing queue")
        processing_set.add(video_id)
        # Put at the front of the queue
        download_queue.queue.appendleft(video_id)

    # Wait for processing (with timeout)
    start_time = time.time()
    timeout = 300  # 5 minutes
    while time.time() - start_time < timeout:
        if os.path.exists(clean_mp3) and os.path.getsize(clean_mp3) > 0:
            return send_from_directory(EPISODES_DIR, os.path.basename(clean_mp3))
        elif os.path.exists(clean_m4a) and os.path.getsize(clean_m4a) > 0:
            return send_from_directory(EPISODES_DIR, os.path.basename(clean_m4a))
        time.sleep(1)

    return Response("Timed out waiting for file processing to complete", status=500)

if __name__ == '__main__':
    # Replace Flask's development server with Waitress
    serve(app, host='0.0.0.0', port=5000)