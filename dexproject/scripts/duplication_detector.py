#!/usr/bin/env python3
"""
Enhanced Duplication Detection Script with Unicode Support

Detects various types of code duplication across the Django project
with proper encoding handling for all Python files.

Features:
- Constant duplication detection
- Function signature duplication
- Import statement analysis
- Code block similarity detection
- Proper Unicode file handling
- Comprehensive error handling and logging

Usage:
    python scripts/duplication_detector.py [--fix] [--verbose]
"""

import os
import sys
import logging
import argparse
import ast
import difflib
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict, Counter
from dataclasses import dataclass
import hashlib
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('duplication_detection.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DuplicationResult:
    """Represents a detected duplication."""
    
    type: str
    description: str
    files: List[str]
    line_numbers: List[int]
    content: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    suggested_fix: Optional[str] = None


@dataclass
class FileProcessingStats:
    """Statistics for file processing."""
    
    total_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    encoding_errors: int = 0
    syntax_errors: int = 0
    skipped_file_list: List[str] = None
    
    def __post_init__(self):
        if self.skipped_file_list is None:
            self.skipped_file_list = []


class EnhancedDuplicationDetector:
    """
    Enhanced duplication detector with proper Unicode support.
    
    Detects various types of code duplication while handling
    encoding issues gracefully.
    """
    
    def __init__(self, project_root: str, fix_mode: bool = False, verbose: bool = False):
        """
        Initialize the duplication detector.
        
        Args:
            project_root: Root directory of the Django project
            fix_mode: Whether to attempt automatic fixes
            verbose: Enable verbose logging
        """
        self.project_root = Path(project_root)
        self.fix_mode = fix_mode
        self.verbose = verbose
        
        # Processing statistics
        self.stats = FileProcessingStats()
        
        # Detection results
        self.duplications: List[DuplicationResult] = []
        
        # Exclusion patterns
        self.exclude_patterns = [
            '__pycache__',
            '.git',
            '.venv',
            'venv',
            'node_modules',
            'migrations',
            '.pytest_cache',
            'htmlcov',
            '*.egg-info'
        ]
        
        # File encodings to try
        self.encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'ascii']
        
        if self.verbose:
            logger.setLevel(logging.DEBUG)
        
        logger.info(f"Initialized duplication detector for: {self.project_root}")
    
    def _safe_read_file(self, file_path: Path) -> Optional[str]:
        """
        Safely read file content with proper encoding handling.
        
        Args:
            file_path: Path to the file to read
            
        Returns:
            File content as string, or None if reading failed
        """
        for encoding in self.encodings:
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.debug(f"Error reading {file_path} with {encoding}: {e}")
                continue
        
        # If all encodings failed, log and skip
        logger.warning(f"Could not decode file {file_path} with any supported encoding")
        self.stats.encoding_errors += 1
        self.stats.skipped_file_list.append(str(file_path))
        return None
    
    def _get_python_files(self) -> List[Path]:
        """
        Get all Python files in the project, excluding specified patterns.
        
        Returns:
            List of Python file paths
        """
        python_files = []
        
        for py_file in self.project_root.rglob("*.py"):
            # Skip files matching exclusion patterns
            if any(pattern in str(py_file) for pattern in self.exclude_patterns):
                continue
            
            python_files.append(py_file)
        
        self.stats.total_files = len(python_files)
        logger.info(f"Found {len(python_files)} Python files")
        return python_files
    
    def _parse_ast_safely(self, content: str, file_path: Path) -> Optional[ast.AST]:
        """
        Safely parse Python file content into AST.
        
        Args:
            content: File content as string
            file_path: Path to the file (for error reporting)
            
        Returns:
            AST node or None if parsing failed
        """
        try:
            return ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            logger.debug(f"Syntax error in {file_path}: {e}")
            self.stats.syntax_errors += 1
            return None
        except Exception as e:
            logger.debug(f"Error parsing {file_path}: {e}")
            return None
    
    def detect_all_duplications(self) -> List[DuplicationResult]:
        """
        Run all duplication detection methods.
        
        Returns:
            List of detected duplications
        """
        logger.info("Starting comprehensive duplication detection...")
        
        # Get all Python files
        python_files = self._get_python_files()
        
        # Run detection methods
        self._detect_constant_duplication(python_files)
        self._detect_function_duplication(python_files)
        self._detect_import_duplication(python_files)
        self._detect_code_block_duplication(python_files)
        
        # Log statistics
        self._log_processing_stats()
        
        # Sort by severity
        self.duplications.sort(key=lambda x: {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}[x.severity], reverse=True)
        
        logger.info(f"Detection complete. Found {len(self.duplications)} duplications")
        return self.duplications
    
    def _detect_constant_duplication(self, python_files: List[Path]) -> None:
        """
        Detect duplicate constants across files.
        
        Args:
            python_files: List of Python files to analyze
        """
        logger.info("Detecting constant duplications...")
        
        constants_map = defaultdict(list)
        
        for py_file in python_files:
            try:
                # Safely read file content
                content = self._safe_read_file(py_file)
                if content is None:
                    self.stats.skipped_files += 1
                    continue
                
                # Parse AST
                tree = self._parse_ast_safely(content, py_file)
                if tree is None:
                    self.stats.skipped_files += 1
                    continue
                
                self.stats.processed_files += 1
                
                # Extract constants
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id.isupper():
                                if isinstance(node.value, (ast.Constant, ast.Str, ast.Num)):
                                    value = self._get_constant_value(node.value)
                                    if value is not None:
                                        constants_map[f"{target.id}={value}"].append({
                                            'file': str(py_file),
                                            'line': node.lineno,
                                            'name': target.id,
                                            'value': value
                                        })
                
            except Exception as e:
                logger.debug(f"Error processing {py_file} for constants: {e}")
                self.stats.skipped_files += 1
                continue
        
        # Find duplicates
        for constant_key, occurrences in constants_map.items():
            if len(occurrences) > 1:
                files = [occ['file'] for occ in occurrences]
                line_numbers = [occ['line'] for occ in occurrences]
                
                severity = self._determine_constant_severity(occurrences)
                
                duplication = DuplicationResult(
                    type="CONSTANT_DUPLICATION",
                    description=f"Constant '{constant_key}' defined in {len(occurrences)} files",
                    files=files,
                    line_numbers=line_numbers,
                    content=constant_key,
                    severity=severity,
                    suggested_fix=f"Consider moving to a shared constants.py file"
                )
                
                self.duplications.append(duplication)
        
        logger.info(f"Found {sum(1 for d in self.duplications if d.type == 'CONSTANT_DUPLICATION')} constant duplications")
    
    def _detect_function_duplication(self, python_files: List[Path]) -> None:
        """
        Detect duplicate function signatures across files.
        
        Args:
            python_files: List of Python files to analyze
        """
        logger.info("Detecting function duplications...")
        
        functions_map = defaultdict(list)
        
        for py_file in python_files:
            try:
                # Safely read file content
                content = self._safe_read_file(py_file)
                if content is None:
                    continue
                
                # Parse AST
                tree = self._parse_ast_safely(content, py_file)
                if tree is None:
                    continue
                
                # Extract function signatures
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        signature = self._get_function_signature(node)
                        functions_map[signature].append({
                            'file': str(py_file),
                            'line': node.lineno,
                            'name': node.name,
                            'signature': signature
                        })
                
            except Exception as e:
                logger.debug(f"Error processing {py_file} for functions: {e}")
                continue
        
        # Find duplicates
        for signature, occurrences in functions_map.items():
            if len(occurrences) > 1:
                files = [occ['file'] for occ in occurrences]
                line_numbers = [occ['line'] for occ in occurrences]
                
                severity = self._determine_function_severity(occurrences)
                
                duplication = DuplicationResult(
                    type="FUNCTION_DUPLICATION",
                    description=f"Function signature '{signature}' found in {len(occurrences)} files",
                    files=files,
                    line_numbers=line_numbers,
                    content=signature,
                    severity=severity,
                    suggested_fix="Consider extracting to a shared utility module"
                )
                
                self.duplications.append(duplication)
        
        logger.info(f"Found {sum(1 for d in self.duplications if d.type == 'FUNCTION_DUPLICATION')} function duplications")
    
    def _detect_import_duplication(self, python_files: List[Path]) -> None:
        """
        Detect redundant import patterns across files.
        
        Args:
            python_files: List of Python files to analyze
        """
        logger.info("Detecting import duplications...")
        
        import_patterns = defaultdict(list)
        
        for py_file in python_files:
            try:
                # Safely read file content
                content = self._safe_read_file(py_file)
                if content is None:
                    continue
                
                # Parse AST
                tree = self._parse_ast_safely(content, py_file)
                if tree is None:
                    continue
                
                # Extract imports
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(f"import {alias.name}")
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        for alias in node.names:
                            imports.append(f"from {module} import {alias.name}")
                
                # Group similar import patterns
                import_hash = hashlib.md5("\n".join(sorted(imports)).encode()).hexdigest()
                import_patterns[import_hash].append({
                    'file': str(py_file),
                    'imports': imports,
                    'import_count': len(imports)
                })
                
            except Exception as e:
                logger.debug(f"Error processing {py_file} for imports: {e}")
                continue
        
        # Find suspicious patterns
        for pattern_hash, occurrences in import_patterns.items():
            if len(occurrences) > 3:  # Many files with identical imports
                files = [occ['file'] for occ in occurrences]
                
                duplication = DuplicationResult(
                    type="IMPORT_DUPLICATION",
                    description=f"Identical import pattern found in {len(occurrences)} files",
                    files=files,
                    line_numbers=[1] * len(files),  # Imports typically at top
                    content=f"{len(occurrences[0]['imports'])} imports",
                    severity="MEDIUM",
                    suggested_fix="Consider creating a shared imports module"
                )
                
                self.duplications.append(duplication)
        
        logger.info(f"Found {sum(1 for d in self.duplications if d.type == 'IMPORT_DUPLICATION')} import duplications")
    
    def _detect_code_block_duplication(self, python_files: List[Path]) -> None:
        """
        Detect similar code blocks across files.
        
        Args:
            python_files: List of Python files to analyze
        """
        logger.info("Detecting code block duplications...")
        
        code_blocks = []
        
        for py_file in python_files:
            try:
                # Safely read file content
                content = self._safe_read_file(py_file)
                if content is None:
                    continue
                
                # Split into logical blocks
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if len(line.strip()) > 20:  # Meaningful lines only
                        # Get surrounding context
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        block = '\n'.join(lines[start:end])
                        
                        # Normalize for comparison
                        normalized = self._normalize_code_block(block)
                        if len(normalized) > 50:  # Skip very small blocks
                            code_blocks.append({
                                'file': str(py_file),
                                'line': i + 1,
                                'content': block,
                                'normalized': normalized
                            })
                
            except Exception as e:
                logger.debug(f"Error processing {py_file} for code blocks: {e}")
                continue
        
        # Find similar blocks
        similar_groups = defaultdict(list)
        
        for block in code_blocks:
            # Use normalized content as key for grouping
            key = hashlib.md5(block['normalized'].encode()).hexdigest()
            similar_groups[key].append(block)
        
        # Report significant duplications
        for group_key, blocks in similar_groups.items():
            if len(blocks) > 1:
                files = [block['file'] for block in blocks]
                line_numbers = [block['line'] for block in blocks]
                
                # Check if files are different (not just different lines in same file)
                unique_files = set(files)
                if len(unique_files) > 1:
                    duplication = DuplicationResult(
                        type="CODE_BLOCK_DUPLICATION",
                        description=f"Similar code block found in {len(unique_files)} files",
                        files=list(unique_files),
                        line_numbers=line_numbers,
                        content=blocks[0]['content'][:100] + "...",
                        severity="HIGH",
                        suggested_fix="Extract common logic to shared function"
                    )
                    
                    self.duplications.append(duplication)
        
        logger.info(f"Found {sum(1 for d in self.duplications if d.type == 'CODE_BLOCK_DUPLICATION')} code block duplications")
    
    def _get_constant_value(self, node: ast.AST) -> Optional[str]:
        """Extract constant value from AST node."""
        try:
            if isinstance(node, ast.Constant):
                return str(node.value)
            elif isinstance(node, ast.Str):  # Python < 3.8 compatibility
                return f"'{node.s}'"
            elif isinstance(node, ast.Num):  # Python < 3.8 compatibility
                return str(node.n)
            else:
                return None
        except Exception:
            return None
    
    def _get_function_signature(self, node: ast.FunctionDef) -> str:
        """Extract function signature from AST node."""
        try:
            args = []
            for arg in node.args.args:
                args.append(arg.arg)
            
            return f"{node.name}({', '.join(args)})"
        except Exception:
            return f"{node.name}(...)"
    
    def _normalize_code_block(self, code: str) -> str:
        """Normalize code block for comparison."""
        # Remove comments and excessive whitespace
        lines = []
        for line in code.split('\n'):
            line = re.sub(r'#.*$', '', line)  # Remove comments
            line = re.sub(r'\s+', ' ', line)  # Normalize whitespace
            line = line.strip()
            if line:
                lines.append(line)
        
        return '\n'.join(lines)
    
    def _determine_constant_severity(self, occurrences: List[Dict]) -> str:
        """Determine severity of constant duplication."""
        count = len(occurrences)
        if count >= 5:
            return "CRITICAL"
        elif count >= 3:
            return "HIGH"
        else:
            return "MEDIUM"
    
    def _determine_function_severity(self, occurrences: List[Dict]) -> str:
        """Determine severity of function duplication."""
        count = len(occurrences)
        if count >= 4:
            return "HIGH"
        elif count >= 2:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _log_processing_stats(self) -> None:
        """Log file processing statistics."""
        logger.info(f"Processing Statistics:")
        logger.info(f"  Total files found: {self.stats.total_files}")
        logger.info(f"  Successfully processed: {self.stats.processed_files}")
        logger.info(f"  Skipped files: {self.stats.skipped_files}")
        logger.info(f"  Encoding errors: {self.stats.encoding_errors}")
        logger.info(f"  Syntax errors: {self.stats.syntax_errors}")
        
        if self.stats.skipped_file_list and self.verbose:
            logger.info(f"Skipped files: {', '.join(self.stats.skipped_file_list[:10])}")
            if len(self.stats.skipped_file_list) > 10:
                logger.info(f"... and {len(self.stats.skipped_file_list) - 10} more")
    
    def generate_report(self) -> str:
        """
        Generate comprehensive duplication report.
        
        Returns:
            Formatted report as string
        """
        report = []
        report.append("=" * 80)
        report.append("DUPLICATION DETECTION REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Summary
        report.append(f"Total duplications found: {len(self.duplications)}")
        
        # Group by severity
        by_severity = defaultdict(list)
        for dup in self.duplications:
            by_severity[dup.severity].append(dup)
        
        for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            count = len(by_severity[severity])
            if count > 0:
                report.append(f"{severity}: {count}")
        
        report.append("")
        
        # Detailed results
        for i, dup in enumerate(self.duplications, 1):
            report.append(f"{i}. {dup.type} [{dup.severity}]")
            report.append(f"   Description: {dup.description}")
            report.append(f"   Files affected: {len(dup.files)}")
            
            for j, file in enumerate(dup.files[:3]):  # Show first 3 files
                line_info = f" (line {dup.line_numbers[j]})" if j < len(dup.line_numbers) else ""
                report.append(f"     - {file}{line_info}")
            
            if len(dup.files) > 3:
                report.append(f"     ... and {len(dup.files) - 3} more files")
            
            if dup.suggested_fix:
                report.append(f"   Suggested fix: {dup.suggested_fix}")
            
            report.append("")
        
        # Processing statistics
        report.append("PROCESSING STATISTICS")
        report.append("-" * 40)
        report.append(f"Total files: {self.stats.total_files}")
        report.append(f"Processed: {self.stats.processed_files}")
        report.append(f"Skipped: {self.stats.skipped_files}")
        report.append(f"Encoding errors: {self.stats.encoding_errors}")
        report.append(f"Syntax errors: {self.stats.syntax_errors}")
        
        return "\n".join(report)
    
    def save_report(self, filename: str = "duplication_report.txt") -> None:
        """Save report to file."""
        report = self.generate_report()
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        logger.info(f"Report saved to: {filename}")


def main():
    """Main entry point for the duplication detector."""
    parser = argparse.ArgumentParser(description="Detect code duplications in Django project")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--fix", action="store_true", help="Attempt automatic fixes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--report", default="duplication_report.txt", help="Report output file")
    
    args = parser.parse_args()
    
    # Initialize detector
    detector = EnhancedDuplicationDetector(
        project_root=args.project_root,
        fix_mode=args.fix,
        verbose=args.verbose
    )
    
    try:
        # Run detection
        duplications = detector.detect_all_duplications()
        
        # Generate and save report
        detector.save_report(args.report)
        
        # Print summary
        print(f"\nDuplication Detection Complete!")
        print(f"Found {len(duplications)} duplications")
        print(f"Report saved to: {args.report}")
        
        # Return appropriate exit code
        critical_count = sum(1 for d in duplications if d.severity == 'CRITICAL')
        if critical_count > 0:
            print(f"WARNING: {critical_count} critical duplications found!")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"Detection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()