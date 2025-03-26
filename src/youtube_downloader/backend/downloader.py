import os
from typing import Any, Callable, Optional

from yt_dlp import YoutubeDL


class DownloadAbortedError(Exception):
    """Exception raised when a download is aborted by the user."""
    pass


class YTDLLogger:
    """Logger class for yt-dlp to handle logging messages."""

    def __init__(self, callback: Optional[Callable[[str], None]]) -> None:
        """Initialize the logger with an optional callback function."""
        self.callback = callback

    def debug(self, msg: str) -> None:
        """Handle debug messages (currently does nothing)."""
        pass

    def info(self, msg: str) -> None:
        """Handle info messages by calling the callback with the message."""
        if self.callback is not None:
            self.callback("INFO: " + msg)

    def warning(self, msg: str) -> None:
        """Handle warning messages by calling the callback with the message."""
        if self.callback is not None:
            self.callback("WARNING: " + msg)

    def error(self, msg: str) -> None:
        """Handle error messages by calling the callback with the message."""
        if self.callback is not None:
            self.callback("ERROR: " + msg)


def download_videos(
    urls: list[str],
    download_folder: str,
    quality: str = "best",
    progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    logger_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Download videos from the provided URLs using yt-dlp.

    Args:
        urls (list[str]): List of video URLs.
        download_folder (str): Folder where videos will be saved.
        quality (str): Video quality to download. Defaults to "best".
        progress_hook (Optional[Callable[[dict[str, Any]], None]]): Callback for progress updates.
        logger_callback (Optional[Callable[[str], None]]): Callback for logging messages.
    """
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    ydl_opts: dict[str, Any] = {
        "format": quality,
        "outtmpl": os.path.join(download_folder, "%(title)s.%(ext)s"),
        "merge_output_format": "mkv",
        "noplaylist": True,
        'writesubtitles': True,
        'writethumbnail': True,
        'postprocessors': [
            {'key': 'FFmpegEmbedSubtitle'},
            {'key': 'FFmpegMetadata'},
            {'key': 'EmbedThumbnail'},
        ],
        "progress_hooks": [progress_hook] if progress_hook else [],
        "logger": YTDLLogger(logger_callback) if logger_callback else None,
    }

    with YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            title = url
            try:
                if progress_hook and hasattr(progress_hook, "__self__") and progress_hook.__self__._is_aborted:
                    ydl.params["logger"].info("Download aborted by user before starting.")
                    raise DownloadAbortedError()

                info_dict = ydl.extract_info(url, download=False)
                title = info_dict.get("title", url)
                video_path = ydl.prepare_filename(info_dict)
                basename = os.path.basename(video_path)
                part_path = video_path + ".part"

                if os.path.exists(video_path):
                    ydl.params["logger"].info(f"Skipping '{title}', already exists.")
                    continue

                if os.path.exists(part_path):
                    ydl.params["logger"].info(f"Resuming '{title}'.")

                ydl.download([url])
                if logger_callback:
                    logger_callback(f"INFO: Successfully downloaded '{title}'")
            except Exception as e:
                if isinstance(e, DownloadAbortedError):
                    ydl.params["logger"].info(f"Download of '{title}' aborted by user.")
                    raise
                msg = f"ERROR downloading '{title}': {str(e)}"
                if logger_callback:
                    logger_callback(msg)
                else:
                    raise Exception(msg)


def fetch_section(
    section_url: str, logger_callback: Optional[Callable[[str], None]] = None
) -> list[dict[str, Any]]:
    """Fetch a list of videos from a specific channel section URL using flat extraction.

    Args:
        section_url (str): The URL of the channel section.
        logger_callback (Optional[Callable[[str], None]]): Logger callback for warnings.

    Returns:
        list[dict[str, Any]]: list of video information dictionaries.
    """
    ydl_opts: dict[str, Any] = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
    }
    if logger_callback:
        ydl_opts["logger"] = YTDLLogger(logger_callback)
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(section_url, download=False)
        entries = info.get("entries", [])

    for entry in entries:
        video_id = entry.get("id") or entry.get("url", "")
        entry["full_url"] = f"https://www.youtube.com/watch?v={video_id}"
    return entries


def fetch_playlists(
    playlists_url: str, logger_callback: Optional[Callable[[str], None]] = None
) -> dict[str, list[dict[str, Any]]]:
    """Fetch playlists from a channel's playlists page and retrieve their videos.

    Args:
        playlists_url (str): The URL of the channel's playlists page.
        logger_callback (Optional[Callable[[str], None]]): Logger callback for warnings.

    Returns:
        dict[str, list[dict[str, Any]]]: Dictionary mapping playlist titles to lists of video info dictionaries.
    """
    ydl_opts: dict[str, Any] = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
    }
    if logger_callback:
        ydl_opts["logger"] = YTDLLogger(logger_callback)
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlists_url, download=False)
        playlist_entries = info.get("entries", [])

    playlists_dict: dict[str, list[dict[str, Any]]] = {}
    for playlist in playlist_entries:
        playlist_id = playlist.get("id")
        playlist_title = playlist.get("title", "Untitled Playlist")
        if not playlist_id:
            continue
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        with YoutubeDL(ydl_opts) as ydl2:
            pl_info = ydl2.extract_info(playlist_url, download=False)
            pl_entries = pl_info.get("entries", [])
        for entry in pl_entries:
            video_id = entry.get("id") or entry.get("url", "")
            entry["full_url"] = f"https://www.youtube.com/watch?v={video_id}"
        playlists_dict[playlist_title] = pl_entries
    return playlists_dict


def fetch_channel_content(
    channel_url: str, logger_callback: Optional[Callable[[str], None]] = None
) -> dict[str, Any]:
    """Fetch content from a channel URL by retrieving different sections.

    The function constructs section URLs for videos, shorts, streams (lives),
    podcasts, and playlists based on the provided channel URL.

    Args:
        channel_url (str): The base URL of the channel.
        logger_callback (Optional[Callable[[str], None]]): Logger callback for warnings.

    Returns:
        dict[str, Any]: Dictionary containing keys:
            - "videos": list of video info dictionaries from /videos.
            - "shorts": list from /shorts.
            - "lives": list from /streams.
            - "podcasts": list from /podcasts.
            - "playlists": Dictionary mapping playlist names to lists of video info dictionaries.
    """
    channel_url = channel_url.rstrip("/")
    videos_url = channel_url + "/videos"
    shorts_url = channel_url + "/shorts"
    lives_url = channel_url + "/streams"
    podcasts_url = channel_url + "/podcasts"
    playlists_url = channel_url + "/playlists"

    content: dict[str, Any] = {}
    try:
        content["videos"] = fetch_section(videos_url, logger_callback)
    except Exception as e:
        if logger_callback:
            logger_callback(f"Error fetching videos: {e}")
        content["videos"] = []
    try:
        content["shorts"] = fetch_section(shorts_url, logger_callback)
    except Exception as e:
        if logger_callback:
            logger_callback(f"Error fetching shorts: {e}")
        content["shorts"] = []
    try:
        content["lives"] = fetch_section(lives_url, logger_callback)
    except Exception as e:
        if logger_callback:
            logger_callback(f"Error fetching lives: {e}")
        content["lives"] = []
    try:
        content["podcasts"] = fetch_section(podcasts_url, logger_callback)
    except Exception as e:
        if "does not have a podcasts tab" in str(e):
            if logger_callback:
                logger_callback("Podcasts tab not available for this channel.")
        else:
            if logger_callback:
                logger_callback(f"Error fetching podcasts: {e}")
        content["podcasts"] = []
    try:
        content["playlists"] = fetch_playlists(playlists_url, logger_callback)
    except Exception as e:
        if logger_callback:
            logger_callback(f"Error fetching playlists: {e}")
        content["playlists"] = {}
    return content
