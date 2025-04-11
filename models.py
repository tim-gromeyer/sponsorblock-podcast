from dataclasses import dataclass
from typing import Set

def clean_thumbnail_url(url):
    """Remove query parameters from thumbnail URLs."""
    if not url:
        return ''
    return url.split('?')[0]

@dataclass
class Video:
    id: str
    title: str
    description: str
    thumbnail_url: str
    duration: int  # Duration in seconds
    upload_date: str = ''

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
            thumbnail_url=data.get('thumbnail_url', ''),
            duration=data.get('duration', 0),
            upload_date=data.get('upload_date', '19700101'),  # YYYYMMDD format
        )
    
    @classmethod
    def from_yt_info(cls, info: dict) -> 'Video':
        thumbnails = info.get('thumbnails', [])
        thumbnail_url = ''
        for thumb in reversed(thumbnails):
            url = thumb.get('url', '').lower()
            if any(ext in url for ext in ('.png', '.jpg', '.jpeg')):
                thumbnail_url = thumb.get('url', '')
                break

        return cls(
            id=info.get('id', ''),
            title=info.get('title', f"Video {info.get('id', '')}"),
            description=info.get('description', "No description available"),
            thumbnail_url=clean_thumbnail_url(thumbnail_url),
            duration=info.get('duration', 0),
            upload_date=info.get('upload_date', '19700101'), # YYYYMMDD format
        )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'thumbnail_url': self.thumbnail_url,
            'duration': self.duration,
            'upload_date': self.upload_date,
        }

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