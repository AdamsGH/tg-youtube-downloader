"""Logging setup and filters."""
import logging
from typing import Optional
from dataclasses import dataclass
from logging import Logger, Filter

@dataclass
class LoggerConfig:
    """Basic logger settings."""
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    level: int = logging.INFO
    suppress_modules: list[str] = None

    def __post_init__(self):
        if self.suppress_modules is None:
            self.suppress_modules = [
                "httpx",
                "apscheduler.scheduler",
                "apscheduler.executors.default",
                "yt_dlp",
                "ffmpeg"
            ]

class LogFilter(Filter):
    """Filter for technical and debug messages."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any([
            "maximum number of running instances reached" in msg,
            "[ffmpeg]" in msg,
            "video:" in msg and "audio:" in msg and "subtitle:" in msg,
            "frame I:" in msg or "frame P:" in msg or "frame B:" in msg,
            "kb/s:" in msg,
            "using cpu capabilities:" in msg,
            "compatible_brands:" in msg,
            "Stream #" in msg
        ])

def configure_logger(name: Optional[str] = None, config: Optional[LoggerConfig] = None) -> Logger:
    """Configure and return a logger instance with specified settings.
    
    Args:
        name: Logger name. If None, returns root logger
        config: Logger configuration settings. If None, uses default settings
        
    Returns:
        Configured logger instance
    """
    if config is None:
        config = LoggerConfig()
        
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logging.basicConfig(
            format=config.format,
            level=config.level
        )
        
        # Suppress logs from specified modules
        for module in config.suppress_modules:
            mod_logger = logging.getLogger(module)
            mod_logger.setLevel(logging.ERROR)
            
            mod_logger.addFilter(LogFilter())
    
    return logger
