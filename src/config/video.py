"""
YT-DLP configuration module.

This module provides configuration settings for the yt-dlp library,
which is used for downloading and processing YouTube videos.
"""
from typing import Any, Callable, Dict, Optional, List, Union
from dataclasses import dataclass, field
from yt_dlp.utils import download_range_func

# Type alias for progress hook function
ProgressHook = Callable[[Dict[str, Any]], None]

@dataclass 
class VideoFormat:
    """
    Video format settings.
    
    Configures the preferred video formats and download behavior.
    """
    # Using legacy formats that work better with partial downloads
    format: str = '22/18'  # 720p/360p MP4 with embedded audio
    force_generic_extractor: bool = False
    fragment_retries: int = 10
    ignore_errors: bool = False

@dataclass
class ExtractorConfig:
    """
    YouTube extractor settings.
    
    Configures how yt-dlp extracts video information and streams.
    """
    youtube_skip: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize default values if not provided."""
        if not self.youtube_skip:
            # Skip problematic formats that can cause issues with partial downloads
            self.youtube_skip = ['dash', 'hls']

    def get_args(self) -> Dict[str, Any]:
        """
        Get extractor arguments in the format expected by yt-dlp.
        
        Returns:
            Dictionary of extractor arguments
        """
        return {'youtube': {'skip': self.youtube_skip}}

@dataclass
class PostProcessorConfig:
    """
    Post-processing settings.
    
    Configures how videos are processed after download.
    """
    args: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize default values if not provided."""
        if not self.args:
            # Handle negative timestamps in a way that works better for cutting
            self.args = ['-avoid_negative_ts', 'make_zero']

def get_download_options(
    output_path: str,
    progress_hook: ProgressHook,
    start_seconds: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    video_format: Optional[VideoFormat] = None,
    extractor_config: Optional[ExtractorConfig] = None,
    post_processor_config: Optional[PostProcessorConfig] = None
) -> Dict[str, Any]:
    """
    Configure YT-DLP options for video download.
    
    This function creates a configuration dictionary for yt-dlp with
    appropriate settings for downloading and processing videos.
    
    Args:
        output_path: Path where the downloaded video will be saved
        progress_hook: Callback function for tracking download progress
        start_seconds: Start time for video cutting in seconds
        duration_seconds: Duration for video cutting in seconds
        video_format: Video format configuration
        extractor_config: YouTube extractor configuration
        post_processor_config: Post-processing configuration
        
    Returns:
        Dictionary of yt-dlp options
    """
    # Use default configurations if not provided
    if video_format is None:
        video_format = VideoFormat()
    if extractor_config is None:
        extractor_config = ExtractorConfig()
    if post_processor_config is None:
        post_processor_config = PostProcessorConfig()

    # Base options that work well for most downloads
    opts = {
        'format': video_format.format,
        'outtmpl': output_path,
        'progress_hooks': [progress_hook],
        
        # Reliability options
        'retries': 10,                # Number of retries for the whole file
        'fragment_retries': 10,       # Number of retries for fragments
        
        # Performance options
        'prefer_ffmpeg': False,       # Avoid using ffmpeg when possible
        'youtube_include_dash_manifest': False,  # Skip DASH manifests
        
        # Partial download settings
        'http_chunk_size': 10485760,  # 10MB chunks for better progress reporting
        
        # Logging options
        'quiet': True,                # Suppress standard output
        'no_warnings': True           # Suppress warnings
    }

    # Add video cutting options if start and duration are provided
    if start_seconds is not None and duration_seconds is not None:
        opts.update({
            # Define the time range to download
            'download_ranges': download_range_func(
                [], [[start_seconds, start_seconds + duration_seconds]]
            ),
            'force_keyframes_at_cuts': False,  # More reliable cutting
            'external_downloader': 'native'    # Use native downloader for better range support
        })

    return opts
