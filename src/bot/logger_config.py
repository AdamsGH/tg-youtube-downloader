import logging
from typing import Optional

def setup_logger(name: Optional[str] = None) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        
        # Suppress extra logs from third-party modules
        logging.getLogger("httpx").setLevel(logging.ERROR)
        
        # Suppress all apscheduler logs
        for logger_name in ["apscheduler.scheduler", "apscheduler.executors.default"]:
            aps_logger = logging.getLogger(logger_name)
            aps_logger.setLevel(logging.ERROR)
            
            class SuppressMaxInstancesFilter(logging.Filter):
                def filter(self, record):
                    return "maximum number of running instances reached" not in record.getMessage()
                    
            aps_logger.addFilter(SuppressMaxInstancesFilter())
    
    return logger
