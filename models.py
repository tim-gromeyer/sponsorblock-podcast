from dataclasses import dataclass
from typing import List, Optional, Set
from datetime import timedelta

@dataclass
class Video:
    id: str
    title: str
    description: str
    thumbnail_url: str
    duration: int  # Duration in seconds

    @property
    def youtube_url(self) -> str:
        return f'https://www.youtube.com/watch?v={self.id}'

    @property
    def estimated_size(self) -> int:
        return self.duration * 24000 if self.duration else 0

    @classmethod
    def from_dict(cls, video_id: str, data: dict) -> 'Video':
        return cls(
            id=video_id,
            title=data.get('title', f"Video {video_id}"),
            description=data.get('description', "No description available"),
            thumbnail_url=data.get('thumbnail', ''),
            duration=data.get('duration', 0)
        )

@dataclass
class Playlist:
    title: str
    description: str
    author: str
    thumbnail_url: str
    video_ids: Set[str]

    @classmethod
    def from_yt_info(cls, info: dict) -> 'Playlist':
        thumbnails = info.get('thumbnails', [])
        thumbnail_url = thumbnails[-1]['url'] if thumbnails else ''
        
        return cls(
            title=info.get('title', 'Sponsor-Free Podcast'),
            description=info.get('description', 'A podcast feed with sponsor segments removed'),
            author=info.get('uploader', 'Unknown'),
            thumbnail_url=thumbnail_url,
            video_ids={v['id'] for v in info.get('entries', [])}
        )