"""
Logging setup and filters.

This module provides utilities for configuring logging with appropriate
filters to reduce noise from external libraries and technical messages.
"""
import logging
from typing import Optional, List, Set
from dataclasses import dataclass, field
from logging import Logger, Filter

@dataclass
class LoggerConfig:
    """
    Logger configuration settings.
    
    Defines format, level, and modules to suppress for application logging.
    """
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    level: int = logging.INFO
    suppress_modules: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        Initialize default values if not provided.
        
        Sets default list of modules to suppress if none provided.
        """
        if not self.suppress_modules:
            self.suppress_modules = [
                "httpx",
                "apscheduler.scheduler",
                "apscheduler.executors.default",
                "yt_dlp",
                "ffmpeg"
            ]

class LogFilter(Filter):
    """
    Filter for technical and debug messages.
    
    Filters out noisy messages from external libraries like ffmpeg and yt-dlp
    that would otherwise clutter the logs.
    """
    # Patterns to filter out
    _noise_patterns: Set[str] = {
        "maximum number of running instances reached",
        "[ffmpeg]",
        "kb/s:",
        "using cpu capabilities:",
        "compatible_brands:",
        "Stream #"
    }
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records based on content.
        
        Args:
            record: Log record to filter
            
        Returns:
            False if the message should be filtered out, True otherwise
        """
        msg = record.getMessage()
        
        # Check for exact matches in noise patterns
        for pattern in self._noise_patterns:
            if pattern in msg:
                return False
                
        # Check for more complex patterns
        if "video:" in msg and "audio:" in msg and "subtitle:" in msg:
            return False
            
        if "frame I:" in msg or "frame P:" in msg or "frame B:" in msg:
            return False
            
        return True

def configure_logger(name: Optional[str] = None, config: Optional[LoggerConfig] = None) -> Logger:
    """
    Configure and return a logger instance with specified settings.
    
    This function sets up a logger with appropriate formatting, level, and filters
    to ensure clean and relevant logging output.
    
    Args:
        name: Logger name. If None, returns root logger
        config: Logger configuration settings. If None, uses default settings
        
    Returns:
        Configured logger instance
    """
    if config is None:
        config = LoggerConfig()
        
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        # Configure basic logging
        logging.basicConfig(
            format=config.format,
            level=config.level
        )
        
        # Create and apply filter for noisy messages
        log_filter = LogFilter()
        
        # Suppress logs from specified modules
        for module in config.suppress_modules:
            mod_logger = logging.getLogger(module)
            # Set to ERROR level to reduce noise
            mod_logger.setLevel(logging.ERROR)
            # Add filter to remove noisy messages
            mod_logger.addFilter(log_filter)
    
    return logger
