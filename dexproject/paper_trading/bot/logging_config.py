"""
Windows-compatible logging configuration for paper trading bot.
Add this to the top of your bot files to fix encoding issues.
"""

import logging
import sys

# Configure logging for Windows compatibility
def configure_logging():
    # Remove all handlers
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create new handler with UTF-8 encoding
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
    )
    
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    return logger
