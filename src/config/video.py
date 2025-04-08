"""YT-DLP configuration."""
from typing import Any, Callable, Dict, Optional, List
from dataclasses import dataclass
from yt_dlp.utils import download_range_func

@dataclass 
class VideoFormat:
    """Video format settings."""
    # Используем legacy форматы, которые лучше работают с частичной загрузкой
    format: str = '22/18'  # 720p/360p MP4 с встроенным аудио
    force_generic_extractor: bool = False
    fragment_retries: int = 10
    ignore_errors: bool = False

@dataclass
class ExtractorConfig:
    """YouTube extractor settings."""
    youtube_skip: List[str] = None

    def __post_init__(self):
        if self.youtube_skip is None:
            self.youtube_skip = ['dash', 'hls']  # Пропускаем проблемные форматы

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
        'progress_hooks': [progress_hook],
        
        # Базовые опции
        'retries': 10,
        'fragment_retries': 10,
        
        # Отключаем сложную обработку видео
        'prefer_ffmpeg': False,
        'youtube_include_dash_manifest': False,
        
        # Настройки для частичной загрузки
        'http_chunk_size': 10485760,  # 10MB
        
        # Подавление логов
        'quiet': True,
        'no_warnings': True
    }

    if start_seconds is not None and duration_seconds is not None:
        opts.update({
            'download_ranges': download_range_func(
                [], [[start_seconds, start_seconds + duration_seconds]]
            ),
            'force_keyframes_at_cuts': False,
            'external_downloader': 'native'
        })

    return opts