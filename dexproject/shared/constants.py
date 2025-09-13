"""
Shared constants for the DEX project.
ECHO is off.
This module contains common constants used across multiple Django apps
to reduce duplication and ensure consistency.
"""

# Common choices for models
RISK_LEVELS = [
    ('LOW', 'Low'),
    ('MEDIUM', 'Medium'),
    ('HIGH', 'High'),
    ('CRITICAL', 'Critical'),
]

STATUS_CHOICES = [
    ('ACTIVE', 'Active'),
    ('INACTIVE', 'Inactive'),
    ('PENDING', 'Pending'),
    ('COMPLETED', 'Completed'),
    ('FAILED', 'Failed'),
    ('ERROR', 'Error'),
]

# Common field lengths
SHORT_TEXT_LENGTH = 100
MEDIUM_TEXT_LENGTH = 255
ADDRESS_LENGTH = 42  # Ethereum address length
HASH_LENGTH = 66     # Ethereum transaction hash length

# Decimal precision settings
DECIMAL_PLACES = 18
MAX_DIGITS = 32

# Common regex patterns
ETHEREUM_ADDRESS_PATTERN = r'0x[a-fA-F0-9]{40}$'
TRANSACTION_HASH_PATTERN = r'0x[a-fA-F0-9]{64}$'

# Default timeouts
DEFAULT_TIMEOUT_SECONDS = 30
LONG_TIMEOUT_SECONDS = 60
SHORT_TIMEOUT_SECONDS = 10
