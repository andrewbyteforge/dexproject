"""
Duplication Detection Tools for DEX Auto-Trading Bot

Automated tools to detect and prevent code duplication across the project.
These tools help maintain the Single Source of Truth (SSOT) principle.

File: dexproject/scripts/duplication_detector.py
"""

import ast
import os
import re
import json
import logging
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class DuplicationIssue:
    """Represents a duplication issue found in the codebase."""
    
    issue_type: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    description: str
    files: List[str]
    details: Dict
    suggestion: str


class DuplicationDetector:
    """
    Automated duplication detection for the DEX trading bot project.
    
    Detects various types of duplication including:
    - Configuration duplication
    - Business logic duplication
    - Import violations
    - SSOT violations
    """
    
    def __init__(self, project_root: str):
        """
        Initialize duplication detector.
        
        Args:
            project_root: Root directory of the project
        """
        self.project_root = Path(project_root)
        self.issues: List[DuplicationIssue] = []
        self.logger = logging.getLogger(__name__)
        
        # Configuration patterns to detect
        self.config_patterns = {
            'chain_ids': r'chain_id\s*[=:]\s*(\d+)',
            'chain_names': r'["\']name["\']\s*[=:]\s*["\']([^"\']+)["\']',
            'addresses': r'0x[a-fA-F0-9]{40}',
            'rpc_urls': r'https?://[^\s\'"]+',
        }
        
        # Import direction rules
        self.import_rules = {
            'shared': {
                'cannot_import': ['engine', 'trading', 'risk', 'wallet', 'analytics', 'dashboard'],
                'can_import': ['typing', 'datetime', 'decimal', 'enum']
            },
            'engine': {
                'cannot_import': ['trading', 'risk', 'wallet', 'analytics', 'dashboard'],
                'can_import': ['shared']
            },
            'django_apps': {
                'can_import': ['shared', 'django', 'celery', 'rest_framework']
            }
        }
    
    def detect_all_duplications(self) -> List[DuplicationIssue]:
        """
        Run all duplication detection checks.
        
        Returns:
            List of duplication issues found
        """
        self.issues = []
        
        self.logger.info("🔍 Starting comprehensive duplication detection...")
        
        # Run different types of checks
        self._detect_configuration_duplication()
        self._detect_business_logic_duplication()
        self._detect_import_violations()
        self._detect_ssot_violations()
        self._detect_constant_duplication()
        
        # Sort issues by severity
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        self.issues.sort(key=lambda x: severity_order.get(x.severity, 4))
        
        self.logger.info(f"✅ Detection complete. Found {len(self.issues)} issues.")
        return self.issues
    
    def _detect_configuration_duplication(self) -> None:
        """Detect duplicated configuration across files."""
        self.logger.info("🔍 Checking for configuration duplication...")
        
        config_occurrences = defaultdict(list)
        
        # Scan relevant files for configuration patterns
        files_to_scan = [
            'engine/config.py',
            'shared/constants.py',
            'trading/models.py',
            'trading/management/commands/populate_chains_and_dexes.py'
        ]
        
        for file_path in files_to_scan:
            full_path = self.project_root / file_path
            if full_path.exists():
                content = full_path.read_text()
                
                # Check for chain IDs
                chain_ids = re.findall(self.config_patterns['chain_ids'], content)
                for chain_id in chain_ids:
                    config_occurrences[f'chain_id_{chain_id}'].append(str(file_path))
                
                # Check for contract addresses
                addresses = re.findall(self.config_patterns['addresses'], content)
                for addr in addresses:
                    config_occurrences[f'address_{addr}'].append(str(file_path))
        
        # Report duplicated configurations
        for config_item, files in config_occurrences.items():
            if len(files) > 1:
                self.issues.append(DuplicationIssue(
                    issue_type="configuration_duplication",
                    severity="high" if "chain_id" in config_item else "medium",
                    description=f"Configuration item '{config_item}' found in multiple files",
                    files=files,
                    details={"config_item": config_item},
                    suggestion="Move to Django models as Single Source of Truth"
                ))
    
    def _detect_business_logic_duplication(self) -> None:
        """Detect duplicated business logic across modules."""
        self.logger.info("🔍 Checking for business logic duplication...")
        
        # Look for similar function names that might indicate duplication
        function_patterns = [
            'honeypot.*check',
            'liquidity.*check',
            'ownership.*check',
            'tax.*analysis',
            'execute.*trade',
        ]
        
        for pattern in function_patterns:
            occurrences = self._find_function_pattern(pattern)
            if len(occurrences) > 1:
                # Check if these are in different modules (potential duplication)
                modules = set(os.path.dirname(f) for f in occurrences)
                if len(modules) > 1:
                    self.issues.append(DuplicationIssue(
                        issue_type="business_logic_duplication",
                        severity="medium",
                        description=f"Similar function pattern '{pattern}' found in multiple modules",
                        files=list(occurrences),
                        details={"pattern": pattern, "modules": list(modules)},
                        suggestion="Extract common logic to shared/risk_utils.py or shared/trading_utils.py"
                    ))
    
    def _detect_import_violations(self) -> None:
        """Detect import direction violations."""
        self.logger.info("🔍 Checking for import violations...")
        
        # Scan Python files for imports
        for py_file in self.project_root.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
                
            rel_path = py_file.relative_to(self.project_root)
            module_type = self._get_module_type(str(rel_path))
            
            if module_type:
                violations = self._check_import_rules(py_file, module_type)
                for violation in violations:
                    self.issues.append(DuplicationIssue(
                        issue_type="import_violation",
                        severity="high",
                        description=violation['description'],
                        files=[str(rel_path)],
                        details=violation,
                        suggestion="Restructure imports to follow dependency direction rules"
                    ))
    
    def _detect_ssot_violations(self) -> None:
        """Detect Single Source of Truth violations."""
        self.logger.info("🔍 Checking for SSOT violations...")
        
        # Check for hardcoded values that should come from Django
        ssot_patterns = {
            'chain_configurations': {
                'pattern': r'ChainConfig\s*\(',
                'files': ['engine/config.py'],
                'should_be_in': 'Django Chain models'
            },
            'dex_addresses': {
                'pattern': r'uniswap.*factory.*=.*0x[a-fA-F0-9]{40}',
                'files': ['engine/config.py', 'shared/constants.py'],
                'should_be_in': 'Django DEX models'
            }
        }
        
        for violation_type, config in ssot_patterns.items():
            violations = []
            for file_pattern in config['files']:
                for file_path in self.project_root.rglob(file_pattern):
                    if file_path.exists():
                        content = file_path.read_text()
                        if re.search(config['pattern'], content, re.IGNORECASE):
                            violations.append(str(file_path.relative_to(self.project_root)))
            
            if violations:
                self.issues.append(DuplicationIssue(
                    issue_type="ssot_violation",
                    severity="critical",
                    description=f"SSOT violation: {violation_type} should only be defined in {config['should_be_in']}",
                    files=violations,
                    details={"violation_type": violation_type, "should_be_in": config['should_be_in']},
                    suggestion=f"Move configuration to {config['should_be_in']} and access via Django bridge"
                ))
    
    def _detect_constant_duplication(self) -> None:
        """Detect duplicated constants across files."""
        self.logger.info("🔍 Checking for constant duplication...")
        
        # Look for common constant patterns
        constant_patterns = [
            r'CHAIN_IDS\s*=',
            r'CHAIN_NAMES\s*=',
            r'WRAPPED_NATIVE\s*=',
            r'STABLECOINS\s*=',
        ]
        
        for pattern in constant_patterns:
            occurrences = []
            for py_file in self.project_root.rglob("*.py"):
                content = py_file.read_text()
                if re.search(pattern, content):
                    occurrences.append(str(py_file.relative_to(self.project_root)))
            
            if len(occurrences) > 1:
                constant_name = pattern.split('\\s')[0]
                self.issues.append(DuplicationIssue(
                    issue_type="constant_duplication",
                    severity="medium",
                    description=f"Constant '{constant_name}' defined in multiple files",
                    files=occurrences,
                    details={"constant_name": constant_name},
                    suggestion="Define constants in shared/constants.py only"
                ))
    
    def _find_function_pattern(self, pattern: str) -> List[str]:
        """Find files containing functions matching the pattern."""
        occurrences = []
        
        for py_file in self.project_root.rglob("*.py"):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Look for function definitions matching pattern
                if re.search(rf'def\s+[^(]*{pattern}[^(]*\(', content, re.IGNORECASE):
                    occurrences.append(str(py_file.relative_to(self.project_root)))
                    
            except Exception:
                continue
        
        return occurrences
    
    def _get_module_type(self, file_path: str) -> Optional[str]:
        """Determine the module type based on file path."""
        if file_path.startswith('shared/'):
            return 'shared'
        elif file_path.startswith('engine/'):
            return 'engine'
        elif file_path.startswith(('trading/', 'risk/', 'wallet/', 'analytics/', 'dashboard/')):
            return 'django_apps'
        return None
    
    def _check_import_rules(self, file_path: Path, module_type: str) -> List[Dict]:
        """Check import rules for a specific file."""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse imports
            tree = ast.parse(content)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        imports.append(name.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
            
            # Check against rules
            rules = self.import_rules.get(module_type, {})
            cannot_import = rules.get('cannot_import', [])
            
            for imp in imports:
                for forbidden in cannot_import:
                    if imp.startswith(forbidden):
                        violations.append({
                            'description': f"Module {module_type} cannot import from {forbidden}",
                            'import': imp,
                            'rule_violated': f"{module_type} -> {forbidden}"
                        })
        
        except Exception:
            pass
        
        return violations
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """
        Generate a human-readable duplication report.
        
        Args:
            output_file: Optional file path to save the report
            
        Returns:
            Report content as string
        """
        report_lines = [
            "🔍 DEX Auto-Trading Bot - Duplication Detection Report",
            "=" * 60,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Issues Found: {len(self.issues)}",
            ""
        ]
        
        # Group issues by severity
        by_severity = defaultdict(list)
        for issue in self.issues:
            by_severity[issue.severity].append(issue)
        
        # Report by severity
        for severity in ['critical', 'high', 'medium', 'low']:
            issues = by_severity[severity]
            if issues:
                report_lines.append(f"\n🔴 {severity.upper()} ISSUES ({len(issues)})")
                report_lines.append("-" * 40)
                
                for i, issue in enumerate(issues, 1):
                    report_lines.extend([
                        f"\n{i}. {issue.description}",
                        f"   Type: {issue.issue_type}",
                        f"   Files: {', '.join(issue.files)}",
                        f"   💡 Suggestion: {issue.suggestion}"
                    ])
        
        # Summary recommendations
        report_lines.extend([
            "\n" + "=" * 60,
            "📋 SUMMARY RECOMMENDATIONS",
            "=" * 60,
            "",
            "1. 🔧 IMMEDIATE ACTIONS (Critical/High):",
            "   - Fix SSOT violations by moving config to Django models",
            "   - Resolve import direction violations",
            "   - Eliminate configuration duplication",
            "",
            "2. 🛠️ MEDIUM PRIORITY:",
            "   - Extract shared business logic to shared/ modules",
            "   - Consolidate duplicate constants",
            "",
            "3. 🔍 PREVENTION:",
            "   - Run this tool in pre-commit hooks",
            "   - Add SSOT validation to CI/CD pipeline",
            "   - Document import direction rules"
        ])
        
        report_content = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_content)
            print(f"📄 Report saved to: {output_file}")
        
        return report_content


class PreCommitHook:
    """Pre-commit hook to prevent duplication."""
    
    @staticmethod
    def check_staged_files() -> bool:
        """
        Check staged files for duplication issues.
        
        Returns:
            True if no critical issues found, False otherwise
        """
        import subprocess
        
        # Get staged Python files
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            return True  # No git repo or no staged files
        
        staged_files = [f for f in result.stdout.split('\n') if f.endswith('.py')]
        
        if not staged_files:
            return True  # No Python files staged
        
        # Run quick duplication check on staged files
        detector = DuplicationDetector('.')
        issues = detector.detect_all_duplications()
        
        # Check if any critical/high issues involve staged files
        blocking_issues = [
            issue for issue in issues 
            if issue.severity in ['critical', 'high'] 
            and any(f in staged_files for f in issue.files)
        ]
        
        if blocking_issues:
            print("🚫 COMMIT BLOCKED: Critical duplication issues found!")
            for issue in blocking_issues:
                print(f"   ❌ {issue.description}")
                print(f"      💡 {issue.suggestion}")
            print("\nPlease fix these issues before committing.")
            return False
        
        return True


def main():
    """Main entry point for duplication detection."""
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description='Detect code duplication in DEX trading bot')
    parser.add_argument('--project-root', default='.', help='Project root directory')
    parser.add_argument('--output', help='Output file for report')
    parser.add_argument('--pre-commit', action='store_true', help='Run as pre-commit hook')
    parser.add_argument('--quick', action='store_true', help='Quick check (subset of rules)')
    
    args = parser.parse_args()
    
    if args.pre_commit:
        # Pre-commit hook mode
        if not PreCommitHook.check_staged_files():
            exit(1)
        print("✅ No critical duplication issues in staged files")
        return
    
    # Full detection mode
    detector = DuplicationDetector(args.project_root)
    
    if args.quick:
        # Quick mode - only critical checks
        detector._detect_ssot_violations()
        detector._detect_import_violations()
    else:
        # Full detection
        detector.detect_all_duplications()
    
    # Generate report
    report = detector.generate_report(args.output)
    
    if not args.output:
        print(report)
    
    # Exit with error code if critical issues found
    critical_issues = [i for i in detector.issues if i.severity == 'critical']
    if critical_issues:
        print(f"\n🚨 {len(critical_issues)} critical issues found!")
        exit(1)
    else:
        print("\n✅ No critical duplication issues found")


if __name__ == "__main__":
    main()