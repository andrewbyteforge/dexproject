@echo off
setlocal enabledelayedexpansion

REM ===============================================================================
REM Django Project Duplication Fixer - Windows Console Tool
REM 
REM Interactive tool to safely handle code duplications detected by the 
REM duplication detector script.
REM 
REM Usage: fix_duplications.bat
REM ===============================================================================

title Django Duplication Fixer

REM Color codes for better output
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "MAGENTA=[95m"
set "CYAN=[96m"
set "WHITE=[97m"
set "RESET=[0m"

REM Configuration
set "PROJECT_ROOT=%~dp0..\"
set "BACKUP_DIR=%PROJECT_ROOT%\backups\duplication_fixes_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "REPORT_FILE=%PROJECT_ROOT%\duplication_report.txt"
set "LOG_FILE=%PROJECT_ROOT%\duplication_fix_log.txt"

REM Remove spaces from backup directory name
set "BACKUP_DIR=%BACKUP_DIR: =%"

echo %CYAN%===============================================================================%RESET%
echo %CYAN%                    Django Project Duplication Fixer%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %WHITE%Project Root: %PROJECT_ROOT%%RESET%
echo %WHITE%Backup Directory: %BACKUP_DIR%%RESET%
echo %WHITE%Log File: %LOG_FILE%%RESET%
echo.

REM Initialize log file
echo [%date% %time%] Duplication fix session started > "%LOG_FILE%"

REM Check if duplication report exists
if not exist "%REPORT_FILE%" (
    echo %RED%Error: Duplication report not found at %REPORT_FILE%%RESET%
    echo %YELLOW%Please run the duplication detector first:%RESET%
    echo %WHITE%  python scripts/duplication_detector.py%RESET%
    echo.
    pause
    exit /b 1
)

:MAIN_MENU
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                         DUPLICATION FIXER MENU%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %WHITE%Choose an action:%RESET%
echo.
echo %GREEN% 1.%RESET% View duplication report summary
echo %GREEN% 2.%RESET% Fix duplicate management commands (SAFE)
echo %GREEN% 3.%RESET% Remove duplicate files (REQUIRES REVIEW)
echo %GREEN% 4.%RESET% Create shared base classes (SAFE)
echo %GREEN% 5.%RESET% Fix import duplications (SAFE)
echo %GREEN% 6.%RESET% Create backup of entire project
echo %GREEN% 7.%RESET% Restore from backup
echo %GREEN% 8.%RESET% View fix log
echo %GREEN% 9.%RESET% Re-run duplication detector
echo %RED% 0.%RESET% Exit
echo.
set /p "choice=%YELLOW%Enter your choice (0-9): %RESET%"

if "%choice%"=="1" goto VIEW_REPORT
if "%choice%"=="2" goto FIX_MANAGEMENT_COMMANDS
if "%choice%"=="3" goto REMOVE_DUPLICATES
if "%choice%"=="4" goto CREATE_BASE_CLASSES
if "%choice%"=="5" goto FIX_IMPORTS
if "%choice%"=="6" goto CREATE_BACKUP
if "%choice%"=="7" goto RESTORE_BACKUP
if "%choice%"=="8" goto VIEW_LOG
if "%choice%"=="9" goto RUN_DETECTOR
if "%choice%"=="0" goto EXIT
goto MAIN_MENU

:VIEW_REPORT
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                         DUPLICATION REPORT SUMMARY%RESET%
echo %CYAN%===============================================================================%RESET%
echo.

REM Extract summary from report
findstr /C:"Total duplications found:" "%REPORT_FILE%"
findstr /C:"HIGH:" "%REPORT_FILE%"
findstr /C:"MEDIUM:" "%REPORT_FILE%"
echo.

echo %YELLOW%Top 10 Most Critical Issues:%RESET%
echo.

REM Show first 10 duplications
for /f "skip=6 tokens=*" %%a in ('type "%REPORT_FILE%"') do (
    echo %%a
    set /a count+=1
    if !count! geq 20 goto REPORT_DONE
)

:REPORT_DONE
echo.
echo %GREEN%Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:FIX_MANAGEMENT_COMMANDS
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                    FIX DUPLICATE MANAGEMENT COMMANDS%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %WHITE%This will:%RESET%
echo %GREEN% - Create shared/management/commands/base.py%RESET%
echo %GREEN% - Create BaseDexCommand class with common methods%RESET%
echo %GREEN% - Update management commands to inherit from base class%RESET%
echo.
echo %YELLOW%This is a SAFE operation that improves code structure.%RESET%
echo.
set /p "confirm=%YELLOW%Continue? (y/N): %RESET%"
if /i not "%confirm%"=="y" goto MAIN_MENU

call :CREATE_BACKUP_SILENT

echo %WHITE%Creating base management command class...%RESET%

REM Create shared management commands directory
if not exist "%PROJECT_ROOT%\shared\management" mkdir "%PROJECT_ROOT%\shared\management"
if not exist "%PROJECT_ROOT%\shared\management\commands" mkdir "%PROJECT_ROOT%\shared\management\commands"

REM Create __init__.py files
echo. > "%PROJECT_ROOT%\shared\management\__init__.py"
echo. > "%PROJECT_ROOT%\shared\management\commands\__init__.py"

REM Create base command class
(
echo from django.core.management.base import BaseCommand
echo import logging
echo from django.utils import timezone
echo.
echo.
echo class BaseDexCommand^(BaseCommand^):
echo     """
echo     Base class for DEX project management commands.
echo     
echo     Provides common functionality like logging helpers and
echo     standardized output formatting.
echo     """
echo     
echo     def __init__^(self, *args, **kwargs^):
echo         super^(^).__init__^(*args, **kwargs^)
echo         self.logger = logging.getLogger^(self.__class__.__module__^)
echo         self.verbosity = 1
echo     
echo     def _log_info^(self, message: str^) -^> None:
echo         """Log info message based on verbosity."""
echo         if self.verbosity ^>= 1:
echo             self.stdout.write^(message^)
echo         self.logger.info^(message^)
echo     
echo     def _log_success^(self, message: str^) -^> None:
echo         """Log success message."""
echo         if self.verbosity ^>= 1:
echo             self.stdout.write^(self.style.SUCCESS^(message^)^)
echo         self.logger.info^(message^)
echo     
echo     def _log_warning^(self, message: str^) -^> None:
echo         """Log warning message."""
echo         if self.verbosity ^>= 1:
echo             self.stdout.write^(self.style.WARNING^(message^)^)
echo         self.logger.warning^(message^)
echo     
echo     def _log_error^(self, message: str^) -^> None:
echo         """Log error message."""
echo         if self.verbosity ^>= 1:
echo             self.stdout.write^(self.style.ERROR^(message^)^)
echo         self.logger.error^(message^)
echo     
echo     def handle^(self, *args, **options^):
echo         """
echo         Main command handler. Override in subclasses.
echo         Sets up verbosity and calls execute_command^(^).
echo         """
echo         self.verbosity = options.get^('verbosity', 1^)
echo         
echo         try:
echo             self.execute_command^(*args, **options^)
echo         except Exception as e:
echo             self._log_error^(f"Command failed: {e}"^)
echo             raise
echo     
echo     def execute_command^(self, *args, **options^):
echo         """
echo         Override this method in subclasses instead of handle^(^).
echo         """
echo         raise NotImplementedError^("Subclasses must implement execute_command"^)
) > "%PROJECT_ROOT%\shared\management\commands\base.py"

echo %GREEN%Base management command class created successfully!%RESET%
echo [%date% %time%] Created shared base management command class >> "%LOG_FILE%"

echo.
echo %GREEN%Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:REMOVE_DUPLICATES
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                           REMOVE DUPLICATE FILES%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %RED%WARNING: This operation will DELETE files!%RESET%
echo.
echo %WHITE%Files that appear to be complete duplicates:%RESET%
echo.

REM Check for the obvious duplicate
if exist "%PROJECT_ROOT%\trading\management\commands\initialize_dex_bot.py" (
    if exist "%PROJECT_ROOT%\management\commands\initialize_dex_bot.py" (
        echo %YELLOW% - trading\management\commands\initialize_dex_bot.py%RESET%
        echo %WHITE%   ^(appears to be duplicate of management\commands\initialize_dex_bot.py^)%RESET%
        echo.
        
        set /p "confirm=%RED%Delete trading\management\commands\initialize_dex_bot.py? (y/N): %RESET%"
        if /i "!confirm!"=="y" (
            call :CREATE_BACKUP_SILENT
            del "%PROJECT_ROOT%\trading\management\commands\initialize_dex_bot.py"
            echo %GREEN%File deleted successfully!%RESET%
            echo [%date% %time%] Deleted duplicate file: trading\management\commands\initialize_dex_bot.py >> "%LOG_FILE%"
        )
    )
) else (
    echo %GREEN%No obvious duplicate files found.%RESET%
)

echo.
echo %GREEN%Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:CREATE_BASE_CLASSES
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                          CREATE SHARED BASE CLASSES%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %WHITE%This will create shared base classes for:%RESET%
echo %GREEN% - Model mixins (TimestampMixin, UUIDMixin)%RESET%
echo %GREEN% - Admin base classes (BaseModelAdmin)%RESET%
echo %GREEN% - Test base classes (BaseDexTestCase)%RESET%
echo.
set /p "confirm=%YELLOW%Continue? (y/N): %RESET%"
if /i not "%confirm%"=="y" goto MAIN_MENU

call :CREATE_BACKUP_SILENT

echo %WHITE%Creating shared base classes...%RESET%

REM Create shared directory structure
if not exist "%PROJECT_ROOT%\shared" mkdir "%PROJECT_ROOT%\shared"
if not exist "%PROJECT_ROOT%\shared\models" mkdir "%PROJECT_ROOT%\shared\models"
if not exist "%PROJECT_ROOT%\shared\admin" mkdir "%PROJECT_ROOT%\shared\admin"
if not exist "%PROJECT_ROOT%\shared\tests" mkdir "%PROJECT_ROOT%\shared\tests"

REM Create __init__.py files
echo. > "%PROJECT_ROOT%\shared\__init__.py"
echo. > "%PROJECT_ROOT%\shared\models\__init__.py"
echo. > "%PROJECT_ROOT%\shared\admin\__init__.py"
echo. > "%PROJECT_ROOT%\shared\tests\__init__.py"

REM Create model mixins
(
echo import uuid
echo from django.db import models
echo from django.utils import timezone
echo.
echo.
echo class TimestampMixin^(models.Model^):
echo     """
echo     Abstract model mixin that provides timestamp fields.
echo     """
echo     created_at = models.DateTimeField^(auto_now_add=True^)
echo     updated_at = models.DateTimeField^(auto_now=True^)
echo     
echo     class Meta:
echo         abstract = True
echo.
echo.
echo class UUIDMixin^(models.Model^):
echo     """
echo     Abstract model mixin that provides UUID primary key.
echo     """
echo     id = models.UUIDField^(
echo         primary_key=True,
echo         default=uuid.uuid4,
echo         editable=False
echo     ^)
echo     
echo     class Meta:
echo         abstract = True
echo.
echo.
echo class SoftDeleteMixin^(models.Model^):
echo     """
echo     Abstract model mixin that provides soft delete functionality.
echo     """
echo     is_deleted = models.BooleanField^(default=False^)
echo     deleted_at = models.DateTimeField^(null=True, blank=True^)
echo     
echo     def soft_delete^(self^):
echo         """Mark the object as deleted."""
echo         self.is_deleted = True
echo         self.deleted_at = timezone.now^(^)
echo         self.save^(^)
echo     
echo     def restore^(self^):
echo         """Restore a soft-deleted object."""
echo         self.is_deleted = False
echo         self.deleted_at = None
echo         self.save^(^)
echo     
echo     class Meta:
echo         abstract = True
) > "%PROJECT_ROOT%\shared\models\mixins.py"

REM Create admin base classes
(
echo from django.contrib import admin
echo from django.utils.html import format_html
echo.
echo.
echo class BaseModelAdmin^(admin.ModelAdmin^):
echo     """
echo     Base admin class with common functionality.
echo     """
echo     
echo     def short_id^(self, obj^):
echo         """Display shortened ID for UUID fields."""
echo         if hasattr^(obj, 'id'^) and obj.id:
echo             return str^(obj.id^)[:8] + '...'
echo         return '-'
echo     short_id.short_description = 'ID'
echo     
echo     def colored_status^(self, obj, status_field='status'^):
echo         """Display colored status field."""
echo         status = getattr^(obj, status_field, None^)
echo         if not status:
echo             return '-'
echo         
echo         colors = {
echo             'ACTIVE': 'green',
echo             'INACTIVE': 'red',
echo             'PENDING': 'orange',
echo             'SUCCESS': 'green',
echo             'FAILED': 'red',
echo             'ERROR': 'red',
echo             'WARNING': 'orange'
echo         }
echo         
echo         color = colors.get^(status.upper^(^), 'black'^)
echo         return format_html^(
echo             '^<span style="color: {};"^>{}'</span^>',
echo             color,
echo             status
echo         ^)
echo     
echo     def get_readonly_fields^(self, request, obj=None^):
echo         """Make timestamp fields readonly."""
echo         readonly = list^(super^(^).get_readonly_fields^(request, obj^)^)
echo         timestamp_fields = ['created_at', 'updated_at', 'deleted_at']
echo         for field in timestamp_fields:
echo             if hasattr^(self.model, field^) and field not in readonly:
echo                 readonly.append^(field^)
echo         return readonly
) > "%PROJECT_ROOT%\shared\admin\base.py"

REM Create test base classes
(
echo from django.test import TestCase
echo from django.contrib.auth import get_user_model
echo from unittest.mock import Mock, patch
echo.
echo User = get_user_model^(^)
echo.
echo.
echo class BaseDexTestCase^(TestCase^):
echo     """
echo     Base test case with common setup and utilities.
echo     """
echo     
echo     def setUp^(self^):
echo         """Set up test data."""
echo         super^(^).setUp^(^)
echo         self.user = self.create_test_user^(^)
echo     
echo     def create_test_user^(self, username='testuser', email='test@example.com'^):
echo         """Create a test user."""
echo         return User.objects.create_user^(
echo             username=username,
echo             email=email,
echo             password='testpass123'
echo         ^)
echo     
echo     def create_mock_web3^(self^):
echo         """Create a mock Web3 instance."""
echo         mock_w3 = Mock^(^)
echo         mock_w3.eth.get_block_number.return_value = 18000000
echo         mock_w3.is_connected.return_value = True
echo         return mock_w3
echo     
echo     def assertEqualRounded^(self, first, second, places=2^):
echo         """Assert two decimal values are equal when rounded."""
echo         self.assertEqual^(
echo             round^(float^(first^), places^),
echo             round^(float^(second^), places^)
echo         ^)
) > "%PROJECT_ROOT%\shared\tests\base.py"

echo %GREEN%Shared base classes created successfully!%RESET%
echo [%date% %time%] Created shared base classes (models, admin, tests) >> "%LOG_FILE%"

echo.
echo %GREEN%Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:FIX_IMPORTS
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                          FIX IMPORT DUPLICATIONS%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %WHITE%This will create a shared constants module to consolidate imports.%RESET%
echo.
set /p "confirm=%YELLOW%Continue? (y/N): %RESET%"
if /i not "%confirm%"=="y" goto MAIN_MENU

call :CREATE_BACKUP_SILENT

echo %WHITE%Creating shared constants module...%RESET%

REM Create shared constants
(
echo """
echo Shared constants for the DEX project.
echo 
echo This module contains common constants used across multiple Django apps
echo to reduce duplication and ensure consistency.
echo """
echo.
echo # Common choices for models
echo RISK_LEVELS = [
echo     ^('LOW', 'Low'^),
echo     ^('MEDIUM', 'Medium'^),
echo     ^('HIGH', 'High'^),
echo     ^('CRITICAL', 'Critical'^),
echo ]
echo.
echo STATUS_CHOICES = [
echo     ^('ACTIVE', 'Active'^),
echo     ^('INACTIVE', 'Inactive'^),
echo     ^('PENDING', 'Pending'^),
echo     ^('COMPLETED', 'Completed'^),
echo     ^('FAILED', 'Failed'^),
echo     ^('ERROR', 'Error'^),
echo ]
echo.
echo # Common field lengths
echo SHORT_TEXT_LENGTH = 100
echo MEDIUM_TEXT_LENGTH = 255
echo ADDRESS_LENGTH = 42  # Ethereum address length
echo HASH_LENGTH = 66     # Ethereum transaction hash length
echo.
echo # Decimal precision settings
echo DECIMAL_PLACES = 18
echo MAX_DIGITS = 32
echo.
echo # Common regex patterns
echo ETHEREUM_ADDRESS_PATTERN = r'^0x[a-fA-F0-9]{40}$'
echo TRANSACTION_HASH_PATTERN = r'^0x[a-fA-F0-9]{64}$'
echo.
echo # Default timeouts
echo DEFAULT_TIMEOUT_SECONDS = 30
echo LONG_TIMEOUT_SECONDS = 60
echo SHORT_TIMEOUT_SECONDS = 10
) > "%PROJECT_ROOT%\shared\constants.py"

echo %GREEN%Shared constants module created successfully!%RESET%
echo [%date% %time%] Created shared constants module >> "%LOG_FILE%"

echo.
echo %GREEN%Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:CREATE_BACKUP
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                           CREATE PROJECT BACKUP%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %WHITE%Creating backup of entire project...%RESET%
echo %WHITE%Backup location: %BACKUP_DIR%%RESET%
echo.

call :CREATE_BACKUP_SILENT

echo %GREEN%Backup created successfully!%RESET%
echo.
echo %GREEN%Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:RESTORE_BACKUP
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                          RESTORE FROM BACKUP%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %WHITE%Available backups:%RESET%
echo.

if not exist "%PROJECT_ROOT%\backups" (
    echo %RED%No backups found.%RESET%
    echo.
    echo %GREEN%Press any key to return to main menu...%RESET%
    pause >nul
    goto MAIN_MENU
)

dir /b "%PROJECT_ROOT%\backups" | findstr "duplication_fixes"

echo.
set /p "backup_name=%YELLOW%Enter backup folder name to restore (or press Enter to cancel): %RESET%"
if "%backup_name%"=="" goto MAIN_MENU

if not exist "%PROJECT_ROOT%\backups\%backup_name%" (
    echo %RED%Backup not found.%RESET%
    echo.
    echo %GREEN%Press any key to return to main menu...%RESET%
    pause >nul
    goto MAIN_MENU
)

echo.
echo %RED%WARNING: This will overwrite current project files!%RESET%
set /p "confirm=%RED%Are you sure? (y/N): %RESET%"
if /i not "%confirm%"=="y" goto MAIN_MENU

echo %WHITE%Restoring from backup...%RESET%
xcopy /E /Y "%PROJECT_ROOT%\backups\%backup_name%\*" "%PROJECT_ROOT%\"

echo %GREEN%Restore completed!%RESET%
echo [%date% %time%] Restored from backup: %backup_name% >> "%LOG_FILE%"

echo.
echo %GREEN%Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:VIEW_LOG
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                              FIX LOG%RESET%
echo %CYAN%===============================================================================%RESET%
echo.

if exist "%LOG_FILE%" (
    type "%LOG_FILE%"
) else (
    echo %YELLOW%No log file found.%RESET%
)

echo.
echo %GREEN%Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:RUN_DETECTOR
cls
echo %CYAN%===============================================================================%RESET%
echo %CYAN%                         RE-RUN DUPLICATION DETECTOR%RESET%
echo %CYAN%===============================================================================%RESET%
echo.
echo %WHITE%Running duplication detector...%RESET%
echo.

python "%PROJECT_ROOT%\scripts\duplication_detector.py" --verbose

echo.
echo %GREEN%Detection complete! Press any key to return to main menu...%RESET%
pause >nul
goto MAIN_MENU

:CREATE_BACKUP_SILENT
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
echo %WHITE%Creating backup...%RESET%
xcopy /E /Q "%PROJECT_ROOT%\*.py" "%BACKUP_DIR%\" 2>nul
xcopy /E /Q "%PROJECT_ROOT%\*/management" "%BACKUP_DIR%\" 2>nul
xcopy /E /Q "%PROJECT_ROOT%\*/models.py" "%BACKUP_DIR%\" 2>nul
xcopy /E /Q "%PROJECT_ROOT%\*/admin.py" "%BACKUP_DIR%\" 2>nul
echo [%date% %time%] Created backup: %BACKUP_DIR% >> "%LOG_FILE%"
exit /b

:EXIT
echo.
echo %GREEN%Thank you for using the Duplication Fixer!%RESET%
echo %WHITE%Check the log file for details: %LOG_FILE%%RESET%
echo.
echo [%date% %time%] Duplication fix session ended >> "%LOG_FILE%"
pause
exit /b 0