from typing import Dict, Any, Optional
from yt_dlp.utils import download_range_func

def get_ydl_opts(
    output_path: str,
    progress_hook: Any,
    start_seconds: Optional[int] = None,
    duration_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """Get yt-dlp options with optional time range."""
    opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'force_keyframes_at_cuts': True,
        'progress_hooks': [progress_hook],
        'force_generic_extractor': False,
        'fragment_retries': 10,
        'ignoreerrors': False,
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls']
            }
        },
        'postprocessor_args': [
            '-avoid_negative_ts', 'make_zero'
        ]
    }

    if start_seconds is not None and duration_seconds is not None:
        opts['download_ranges'] = download_range_func(
            [], [[start_seconds, start_seconds + duration_seconds]]
        )

    return opts

# Constants for file handling
TEMP_DIR = "temp"
MAX_DIRECT_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB

# Upload configuration
UPLOAD_CONFIG = {
    'max_retries': 3,
    'retry_delay': 5,  # seconds
    'upload_url': 'https://temp.sh/upload'
}
