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