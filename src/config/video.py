"""YT-DLP configuration."""
from typing import Any, Callable, Dict, Optional, List
from dataclasses import dataclass
from yt_dlp.utils import download_range_func

@dataclass
class VideoFormat:
    """Video format settings."""
    format: str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    force_generic_extractor: bool = False
    fragment_retries: int = 10
    ignore_errors: bool = False

@dataclass
class ExtractorConfig:
    """YouTube extractor settings."""
    youtube_skip: List[str] = None

    def __post_init__(self):
        if self.youtube_skip is None:
            self.youtube_skip = ['dash', 'hls']

    def get_args(self) -> Dict[str, Any]:
        return {'youtube': {'skip': self.youtube_skip}}

@dataclass
class PostProcessorConfig:
    """Post-processing settings."""
    args: List[str] = None

    def __post_init__(self):
        if self.args is None:
            self.args = ['-avoid_negative_ts', 'make_zero']

def get_download_options(
    output_path: str,
    progress_hook: Callable[[Dict[str, Any]], None],
    start_seconds: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    video_format: Optional[VideoFormat] = None,
    extractor_config: Optional[ExtractorConfig] = None,
    post_processor_config: Optional[PostProcessorConfig] = None
) -> Dict[str, Any]:
    """Configure YT-DLP options for video download."""
    if video_format is None:
        video_format = VideoFormat()
    if extractor_config is None:
        extractor_config = ExtractorConfig()
    if post_processor_config is None:
        post_processor_config = PostProcessorConfig()

    opts = {
        'format': video_format.format,
        'outtmpl': output_path,
        'force_keyframes_at_cuts': True,
        'progress_hooks': [progress_hook],
        'force_generic_extractor': video_format.force_generic_extractor,
        'fragment_retries': video_format.fragment_retries,
        'ignoreerrors': video_format.ignore_errors,
        'extractor_args': extractor_config.get_args(),
        'postprocessor_args': post_processor_config.args,
        # Подавление лишних логов
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': None,  # Использовать системный ffmpeg
        'ffmpeg': {
            'loglevel': 'error',  # Только ошибки от ffmpeg
            'hide_banner': True,   # Скрыть баннер ffmpeg
        }
    }

    if start_seconds is not None and duration_seconds is not None:
        opts['download_ranges'] = download_range_func(
            [], [[start_seconds, start_seconds + duration_seconds]]
        )

    return opts
