from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class User(BaseModel):
    urn: str
    first_name: str
    last_name: str
    headline: Optional[str] = None
    profile_url: Optional[str] = None


class MediaItem(BaseModel):
    type: str  # "image", "video", "article"
    url: str
    title: Optional[str] = None


class Post(BaseModel):
    urn: str
    text: str
    author: Optional[User] = None
    likes: int = 0
    comments: int = 0
    reposts: int = 0
    impressions: int = 0
    media: list[MediaItem] = []
    created_at: Optional[datetime] = None
    share_urn: Optional[str] = None
    thread_urn: Optional[str] = None
