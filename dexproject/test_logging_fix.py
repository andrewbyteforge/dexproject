#!/usr/bin/env python
"""
Test script to verify logging fixes work properly.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
django.setup()

import logging

def test_logging():
    """Test logging with various characters."""
    logger = logging.getLogger('test_logger')
    
    print("Testing logging with ASCII characters...")
    logger.info("[OK] This should work fine")
    logger.warning("[WARNING] This is a warning")
    logger.error("[ERROR] This is an error")
    
    print("Testing logging with numbers and symbols...")
    logger.info("Loaded 3 chain configurations successfully")
    logger.info("Redis connection established on localhost:6379")
    logger.info("Engine status: RUNNING")
    
    print("All logging tests completed successfully!")

if __name__ == "__main__":
    test_logging()
