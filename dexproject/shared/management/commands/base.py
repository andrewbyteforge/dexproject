from django.core.management.base import BaseCommand
import logging
from django.utils import timezone


class BaseDexCommand(BaseCommand):
    """
    Base class for DEX project management commands.
ECHO is off.
    Provides common functionality like logging helpers and
    standardized output formatting.
    """
ECHO is off.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__module__)
        self.verbosity = 1
ECHO is off.
    def _log_info(self, message: str) -> None:
        """Log info message based on verbosity."""
        if self.verbosity >= 1:
            self.stdout.write(message)
        self.logger.info(message)
ECHO is off.
    def _log_success(self, message: str) -> None:
        """Log success message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.SUCCESS(message))
        self.logger.info(message)
ECHO is off.
    def _log_warning(self, message: str) -> None:
        """Log warning message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.WARNING(message))
        self.logger.warning(message)
ECHO is off.
    def _log_error(self, message: str) -> None:
        """Log error message."""
        if self.verbosity >= 1:
            self.stdout.write(self.style.ERROR(message))
        self.logger.error(message)
ECHO is off.
    def handle(self, *args, **options):
        """
        Main command handler. Override in subclasses.
        Sets up verbosity and calls execute_command().
        """
        self.verbosity = options.get('verbosity', 1)
ECHO is off.
        try:
            self.execute_command(*args, **options)
        except Exception as e:
            self._log_error(f"Command failed: {e}")
            raise
ECHO is off.
    def execute_command(self, *args, **options):
        """
        Override this method in subclasses instead of handle().
        """
        raise NotImplementedError("Subclasses must implement execute_command")
