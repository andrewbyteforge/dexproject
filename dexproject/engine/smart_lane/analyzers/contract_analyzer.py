"""
Contract Security Analyzer

Critical-priority analyzer that performs comprehensive smart contract security
analysis, vulnerability detection, and code quality assessment. Essential for
identifying malicious contracts and security risks.

Path: engine/smart_lane/analyzers/contract_analyzer.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
import hashlib

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory

logger = logging.getLogger(__name__)


@dataclass
class SecurityVulnerability:
    """Individual security vulnerability found in contract."""
    vulnerability_type: str  # REENTRANCY, OVERFLOW, BACKDOOR, etc.
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    location: Optional[str]  # Function or line where found
    impact: str  # Description of potential impact
    confidence: float  # 0-1 scale
    remediation: str  # Suggested fix


@dataclass
class ContractFunction:
    """Analysis of individual contract function."""
    name: str
    visibility: str  # PUBLIC, PRIVATE, INTERNAL, EXTERNAL
    is_payable: bool
    is_view: bool
    is_pure: bool
    has_modifiers: bool
    complexity_score: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL


@dataclass
class OwnershipAnalysis:
    """Contract ownership and admin function analysis."""
    has_owner: bool
    owner_address: Optional[str]
    is_renounced: bool
    admin_functions: List[str]
    emergency_functions: List[str]
    upgrade_mechanism: Optional[str]
    centralization_risk: str  # LOW, MEDIUM, HIGH, CRITICAL


@dataclass
class ContractMetrics:
    """Overall contract quality and security metrics."""
    total_functions: int
    public_functions: int
    external_functions: int
    payable_functions: int
    complexity_score: float
    code_quality_score: float
    security_score: float
    audit_status: str  # UNAUDITED, SELF_AUDITED, PROFESSIONALLY_AUDITED
    verification_status: str  # VERIFIED, UNVERIFIED, PROXY


class ContractAnalyzer(BaseAnalyzer):
    """
    Advanced smart contract security and quality analyzer.
    
    Analyzes:
    - Smart contract bytecode and source code (if available)
    - Common vulnerability patterns (reentrancy, overflow, etc.)
    - Ownership and admin function analysis
    - Upgrade mechanisms and proxy patterns
    - Code quality and complexity metrics
    - Audit status and verification
    - Backdoor and malicious pattern detection
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize contract security analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration including security thresholds
        """
        super().__init__(chain_id, config)
        
        # Security thresholds
        self.thresholds = {
            'critical_vulnerability_limit': 0,  # No critical vulnerabilities allowed
            'high_vulnerability_limit': 2,
            'max_admin_functions': 5,
            'max_complexity_score': 0.8,
            'min_security_score': 0.6,
            'centralization_risk_threshold': 'MEDIUM'
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Vulnerability patterns to detect
        self.vulnerability_patterns = self._load_vulnerability_patterns()
        
        # Known malicious patterns
        self.malicious_patterns = self._load_malicious_patterns()
        
        # Analysis cache
        self.contract_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self.cache_ttl_hours = 24  # Contract code doesn't change often
        
        logger.info(f"Contract analyzer initialized for chain {chain_id}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.CONTRACT_SECURITY
    
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive contract security analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context including bytecode, source code
            
        Returns:
            RiskScore with contract security assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting contract analysis for {token_address[:10]}...")
            
            # Update performance stats
            self.performance_stats['total_analyses'] += 1
            
            # Input validation
            if not self._validate_inputs(token_address, context):
                return self._create_error_risk_score("Invalid inputs for contract analysis")
            
            # Check cache first
            cached_result = self._get_cached_analysis(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Get contract data
            contract_data = await self._fetch_contract_data(token_address, context)
            if not contract_data:
                return self._create_error_risk_score("Unable to fetch contract data")
            
            # Perform security analysis tasks
            analysis_tasks = [
                self._analyze_bytecode_vulnerabilities(contract_data),
                self._analyze_source_code_vulnerabilities(contract_data),
                self._analyze_ownership_structure(contract_data),
                self._analyze_function_security(contract_data),
                self._check_known_malicious_patterns(contract_data),
                self._assess_upgrade_mechanisms(contract_data),
                self._calculate_contract_metrics(contract_data)
            ]
            
            # Execute all tasks with timeout protection
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*analysis_tasks, return_exceptions=True),
                    timeout=20.0  # 20 second timeout for contract analysis
                )
            except asyncio.TimeoutError:
                logger.warning(f"Contract analysis timeout for {token_address[:10]}")
                return self._create_timeout_risk_score()
            
            # Process results
            vulnerabilities = []
            ownership_analysis = None
            contract_functions = []
            malicious_patterns = []
            upgrade_analysis = {}
            contract_metrics = None
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"Contract analysis task {i} failed: {result}")
                    continue
                
                if i <= 1 and isinstance(result, list):  # Vulnerabilities
                    vulnerabilities.extend(result)
                elif i == 2:  # Ownership analysis
                    ownership_analysis = result
                elif i == 3 and isinstance(result, list):  # Function analysis
                    contract_functions = result
                elif i == 4 and isinstance(result, list):  # Malicious patterns
                    malicious_patterns = result
                elif i == 5:  # Upgrade mechanisms
                    upgrade_analysis = result
                elif i == 6:  # Contract metrics
                    contract_metrics = result
            
            # Calculate overall security risk score
            risk_score = self._calculate_security_risk_score(
                vulnerabilities, ownership_analysis, malicious_patterns, contract_metrics
            )
            
            # Cache the result
            analysis_result = {
                'vulnerabilities': vulnerabilities,
                'ownership_analysis': ownership_analysis,
                'contract_functions': contract_functions,
                'malicious_patterns': malicious_patterns,
                'upgrade_analysis': upgrade_analysis,
                'contract_metrics': contract_metrics
            }
            self._cache_analysis_result(token_address, analysis_result)
            
            # Create detailed analysis data
            analysis_details = {
                'vulnerabilities': [v.__dict__ for v in vulnerabilities],
                'ownership_analysis': ownership_analysis.__dict__ if ownership_analysis else None,
                'contract_functions': [f.__dict__ for f in contract_functions],
                'malicious_patterns': malicious_patterns,
                'upgrade_analysis': upgrade_analysis,
                'contract_metrics': contract_metrics.__dict__ if contract_metrics else None,
                'verification_status': contract_data.get('verification_status', 'UNKNOWN'),
                'compiler_version': contract_data.get('compiler_version'),
                'audit_reports': contract_data.get('audit_reports', [])
            }
            
            # Generate warnings
            warnings = self._generate_security_warnings(vulnerabilities, ownership_analysis, malicious_patterns)
            
            # Calculate analysis time
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Update performance stats
            self.performance_stats['successful_analyses'] += 1
            
            # Determine confidence based on data availability
            confidence = self._calculate_analysis_confidence(contract_data, vulnerabilities)
            
            # Create and return risk score
            return RiskScore(
                category=self.get_category(),
                score=risk_score,
                confidence=confidence,
                details=analysis_details,
                analysis_time_ms=analysis_time_ms,
                warnings=warnings,
                data_quality=self._assess_contract_data_quality(contract_data),
                last_updated=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error in contract security analysis: {e}", exc_info=True)
            self.performance_stats['failed_analyses'] += 1
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            return RiskScore(
                category=self.get_category(),
                score=0.8,  # High risk due to analysis failure
                confidence=0.2,
                details={'error': str(e), 'analysis_failed': True},
                analysis_time_ms=analysis_time_ms,
                warnings=[f"Contract analysis failed: {str(e)}"],
                data_quality="POOR"
            )
    
    async def _fetch_contract_data(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetch contract bytecode, source code, and metadata.
        
        In production, this would use blockchain APIs like Etherscan,
        Web3 providers, and verification services.
        """
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Mock contract data - in production would fetch real data
        contract_data = {
            'address': token_address,
            'bytecode': context.get('bytecode', '0x608060405234801561001057600080fd5b50...'),  # Mock bytecode
            'source_code': context.get('source_code'),  # May be None if not verified
            'verification_status': 'VERIFIED' if context.get('source_code') else 'UNVERIFIED',
            'compiler_version': '0.8.19+commit.7dd6d404',
            'optimization_enabled': True,
            'creation_block': 18567890,
            'creator_address': '0x742d35Cc6481C4c29f4F1f8CA0dAa5c2E8a2C0A5',
            'transaction_count': 15234,
            'contract_size_bytes': 12458,
            'audit_reports': [],  # Would contain audit information if available
            'proxy_type': None,  # 'TRANSPARENT', 'UUPS', 'BEACON', or None
            'implementation_address': None
        }
        
        # Add mock source code if available
        if not contract_data['source_code'] and context.get('include_mock_source'):
            contract_data['source_code'] = self._generate_mock_source_code()
            contract_data['verification_status'] = 'VERIFIED'
        
        return contract_data
    
    async def _analyze_bytecode_vulnerabilities(self, contract_data: Dict[str, Any]) -> List[SecurityVulnerability]:
        """
        Analyze bytecode for known vulnerability patterns.
        
        In production, this would use sophisticated bytecode analysis tools
        and pattern matching against known vulnerability signatures.
        """
        vulnerabilities = []
        bytecode = contract_data.get('bytecode', '')
        
        if not bytecode or len(bytecode) < 10:
            return vulnerabilities
        
        try:
            # Mock bytecode analysis - in production would use real analysis
            await asyncio.sleep(0.2)  # Simulate analysis time
            
            # Check for suspicious patterns in bytecode
            patterns_to_check = [
                {
                    'pattern': 'selfdestruct',
                    'opcode': '0xff',
                    'vulnerability': 'SELFDESTRUCT_VULNERABILITY',
                    'severity': 'HIGH',
                    'description': 'Contract contains selfdestruct function'
                },
                {
                    'pattern': 'delegatecall',
                    'opcode': '0xf4',
                    'vulnerability': 'DELEGATECALL_VULNERABILITY',
                    'severity': 'MEDIUM',
                    'description': 'Contract uses delegatecall - potential for logic bugs'
                }
            ]
            
            for pattern in patterns_to_check:
                if pattern['opcode'] in bytecode.lower():
                    vulnerabilities.append(SecurityVulnerability(
                        vulnerability_type=pattern['vulnerability'],
                        severity=pattern['severity'],
                        description=pattern['description'],
                        location='Bytecode analysis',
                        impact=f"Potential {pattern['vulnerability'].lower()} risk",
                        confidence=0.6,
                        remediation=f"Review {pattern['pattern']} usage carefully"
                    ))
            
            # Check for common vulnerability signatures
            if len(bytecode) > 20000:  # Very large contract
                vulnerabilities.append(SecurityVulnerability(
                    vulnerability_type='LARGE_CONTRACT',
                    severity='MEDIUM',
                    description='Contract bytecode is unusually large',
                    location='Contract size',
                    impact='Increased complexity may hide vulnerabilities',
                    confidence=0.8,
                    remediation='Review contract complexity and consider refactoring'
                ))
            
        except Exception as e:
            logger.warning(f"Error in bytecode analysis: {e}")
        
        return vulnerabilities
    
    async def _analyze_source_code_vulnerabilities(self, contract_data: Dict[str, Any]) -> List[SecurityVulnerability]:
        """
        Analyze source code for vulnerability patterns.
        
        This performs static analysis on Solidity source code to identify
        common security issues and anti-patterns.
        """
        vulnerabilities = []
        source_code = contract_data.get('source_code')
        
        if not source_code:
            # Can't analyze without source code
            vulnerabilities.append(SecurityVulnerability(
                vulnerability_type='UNVERIFIED_CONTRACT',
                severity='HIGH',
                description='Contract source code is not verified',
                location='Verification status',
                impact='Cannot perform comprehensive security analysis',
                confidence=1.0,
                remediation='Verify contract source code on block explorer'
            ))
            return vulnerabilities
        
        try:
            await asyncio.sleep(0.1)  # Simulate analysis time
            
            # Check for common vulnerability patterns
            vulnerability_checks = [
                {
                    'pattern': r'\.call\s*\(',
                    'type': 'LOW_LEVEL_CALL',
                    'severity': 'MEDIUM',
                    'description': 'Contract uses low-level calls'
                },
                {
                    'pattern': r'tx\.origin',
                    'type': 'TX_ORIGIN_USAGE',
                    'severity': 'HIGH',
                    'description': 'Dangerous use of tx.origin for authorization'
                },
                {
                    'pattern': r'block\.timestamp',
                    'type': 'TIMESTAMP_DEPENDENCE',
                    'severity': 'LOW',
                    'description': 'Contract depends on block timestamp'
                },
                {
                    'pattern': r'suicide\s*\(',
                    'type': 'DEPRECATED_SUICIDE',
                    'severity': 'MEDIUM',
                    'description': 'Use of deprecated suicide function'
                },
                {
                    'pattern': r'throw\s*;',
                    'type': 'DEPRECATED_THROW',
                    'severity': 'LOW',
                    'description': 'Use of deprecated throw statement'
                }
            ]
            
            for check in vulnerability_checks:
                matches = re.findall(check['pattern'], source_code, re.IGNORECASE)
                if matches:
                    vulnerabilities.append(SecurityVulnerability(
                        vulnerability_type=check['type'],
                        severity=check['severity'],
                        description=check['description'],
                        location=f"Found {len(matches)} occurrence(s)",
                        impact=f"Potential security risk from {check['type'].lower()}",
                        confidence=0.8,
                        remediation=f"Review and replace {check['type'].lower()} usage"
                    ))
            
            # Check for reentrancy patterns
            if re.search(r'\.call\.value\s*\(', source_code, re.IGNORECASE):
                vulnerabilities.append(SecurityVulnerability(
                    vulnerability_type='REENTRANCY_RISK',
                    severity='CRITICAL',
                    description='Potential reentrancy vulnerability detected',
                    location='call.value usage',
                    impact='Funds could be drained through reentrancy attack',
                    confidence=0.7,
                    remediation='Implement checks-effects-interactions pattern'
                ))
            
            # Check for unchecked external calls
            external_calls = re.findall(r'(\w+)\.call\(', source_code)
            if external_calls:
                vulnerabilities.append(SecurityVulnerability(
                    vulnerability_type='UNCHECKED_EXTERNAL_CALL',
                    severity='MEDIUM',
                    description='External calls may not be properly checked',
                    location='External call sites',
                    impact='Failed calls might not be handled properly',
                    confidence=0.6,
                    remediation='Always check return values of external calls'
                ))
            
        except Exception as e:
            logger.warning(f"Error in source code analysis: {e}")
        
        return vulnerabilities
    
    async def _analyze_ownership_structure(self, contract_data: Dict[str, Any]) -> OwnershipAnalysis:
        """Analyze contract ownership and admin functions."""
        source_code = contract_data.get('source_code', '')
        
        try:
            await asyncio.sleep(0.05)
            
            # Check for ownership patterns
            has_owner = bool(re.search(r'owner\s*=|onlyOwner|Ownable', source_code, re.IGNORECASE))
            is_renounced = bool(re.search(r'renounceOwnership|owner.*=.*address\(0\)', source_code, re.IGNORECASE))
            
            # Find admin functions
            admin_functions = []
            admin_patterns = [
                r'function\s+(\w*(?:admin|owner|mint|burn|pause|emergency)\w*)',
                r'function\s+(\w+).*onlyOwner',
                r'function\s+(set\w+)',
                r'function\s+(withdraw\w*)'
            ]
            
            for pattern in admin_patterns:
                matches = re.findall(pattern, source_code, re.IGNORECASE)
                admin_functions.extend(matches)
            
            # Remove duplicates
            admin_functions = list(set(admin_functions))
            
            # Find emergency functions
            emergency_functions = []
            emergency_patterns = [
                r'function\s+(\w*emergency\w*)',
                r'function\s+(\w*pause\w*)',
                r'function\s+(\w*stop\w*)'
            ]
            
            for pattern in emergency_patterns:
                matches = re.findall(pattern, source_code, re.IGNORECASE)
                emergency_functions.extend(matches)
            
            emergency_functions = list(set(emergency_functions))
            
            # Check for upgrade mechanisms
            upgrade_mechanism = None
            if re.search(r'upgradeTo|proxy|implementation', source_code, re.IGNORECASE):
                upgrade_mechanism = 'PROXY_UPGRADEABLE'
            elif re.search(r'migrate|upgrade', source_code, re.IGNORECASE):
                upgrade_mechanism = 'MIGRATION_BASED'
            
            # Determine centralization risk
            admin_count = len(admin_functions)
            if not has_owner and admin_count == 0:
                centralization_risk = 'LOW'
            elif is_renounced and admin_count <= 2:
                centralization_risk = 'LOW'
            elif admin_count <= 3:
                centralization_risk = 'MEDIUM'
            elif admin_count <= 8:
                centralization_risk = 'HIGH'
            else:
                centralization_risk = 'CRITICAL'
            
            return OwnershipAnalysis(
                has_owner=has_owner,
                owner_address=contract_data.get('creator_address'),
                is_renounced=is_renounced,
                admin_functions=admin_functions,
                emergency_functions=emergency_functions,
                upgrade_mechanism=upgrade_mechanism,
                centralization_risk=centralization_risk
            )
            
        except Exception as e:
            logger.warning(f"Error in ownership analysis: {e}")
            return OwnershipAnalysis(
                has_owner=False,
                owner_address=None,
                is_renounced=False,
                admin_functions=[],
                emergency_functions=[],
                upgrade_mechanism=None,
                centralization_risk='UNKNOWN'
            )
    
    async def _analyze_function_security(self, contract_data: Dict[str, Any]) -> List[ContractFunction]:
        """Analyze individual functions for security issues."""
        functions = []
        source_code = contract_data.get('source_code', '')
        
        if not source_code:
            return functions
        
        try:
            await asyncio.sleep(0.1)
            
            # Find all function definitions
            function_pattern = r'function\s+(\w+)\s*\([^)]*\)\s*((?:public|private|internal|external|payable|view|pure|override|virtual|onlyOwner|\s)*)\s*(?:returns\s*\([^)]*\))?\s*\{'
            
            matches = re.finditer(function_pattern, source_code, re.IGNORECASE | re.MULTILINE)
            
            for match in matches:
                func_name = match.group(1)
                modifiers = match.group(2).lower() if match.group(2) else ''
                
                # Analyze function properties
                visibility = 'public'  # default
                if 'private' in modifiers:
                    visibility = 'private'
                elif 'internal' in modifiers:
                    visibility = 'internal'
                elif 'external' in modifiers:
                    visibility = 'external'
                
                is_payable = 'payable' in modifiers
                is_view = 'view' in modifiers
                is_pure = 'pure' in modifiers
                has_modifiers = 'onlyowner' in modifiers or 'modifier' in modifiers
                
                # Calculate complexity score (simplified)
                func_body_start = match.end()
                func_body_end = self._find_function_end(source_code, func_body_start)
                func_body = source_code[func_body_start:func_body_end]
                
                complexity_score = self._calculate_function_complexity(func_body)
                
                # Determine risk level
                risk_level = 'LOW'
                if is_payable and visibility in ['public', 'external'] and not has_modifiers:
                    risk_level = 'HIGH'
                elif is_payable or (visibility in ['public', 'external'] and not is_view and not is_pure):
                    risk_level = 'MEDIUM'
                elif complexity_score > 0.8:
                    risk_level = 'MEDIUM'
                
                functions.append(ContractFunction(
                    name=func_name,
                    visibility=visibility,
                    is_payable=is_payable,
                    is_view=is_view,
                    is_pure=is_pure,
                    has_modifiers=has_modifiers,
                    complexity_score=complexity_score,
                    risk_level=risk_level
                ))
            
        except Exception as e:
            logger.warning(f"Error in function analysis: {e}")
        
        return functions
    
    async def _check_known_malicious_patterns(self, contract_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for known malicious patterns."""
        patterns = []
        source_code = contract_data.get('source_code', '')
        bytecode = contract_data.get('bytecode', '')
        
        try:
            await asyncio.sleep(0.05)
            
            # Check for honeypot patterns
            for pattern in self.malicious_patterns:
                if pattern['type'] == 'SOURCE_PATTERN' and source_code:
                    if re.search(pattern['pattern'], source_code, re.IGNORECASE):
                        patterns.append({
                            'pattern_name': pattern['name'],
                            'severity': pattern['severity'],
                            'description': pattern['description'],
                            'confidence': pattern['confidence']
                        })
                elif pattern['type'] == 'BYTECODE_PATTERN' and bytecode:
                    if pattern['pattern'] in bytecode.lower():
                        patterns.append({
                            'pattern_name': pattern['name'],
                            'severity': pattern['severity'],
                            'description': pattern['description'],
                            'confidence': pattern['confidence']
                        })
            
        except Exception as e:
            logger.warning(f"Error checking malicious patterns: {e}")
        
        return patterns
    
    async def _assess_upgrade_mechanisms(self, contract_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess contract upgrade mechanisms and associated risks."""
        source_code = contract_data.get('source_code', '')
        proxy_type = contract_data.get('proxy_type')
        
        analysis = {
            'is_upgradeable': False,
            'upgrade_type': None,
            'upgrade_controls': [],
            'immutability_score': 1.0,
            'upgrade_risk': 'LOW'
        }
        
        try:
            await asyncio.sleep(0.05)
            
            if proxy_type:
                analysis['is_upgradeable'] = True
                analysis['upgrade_type'] = proxy_type
                analysis['immutability_score'] = 0.3
                analysis['upgrade_risk'] = 'HIGH'
            
            if source_code:
                # Check for upgrade patterns
                upgrade_patterns = [
                    'upgradeTo',
                    'implementation',
                    'proxy',
                    'delegate',
                    'migrate'
                ]
                
                found_patterns = []
                for pattern in upgrade_patterns:
                    if re.search(pattern, source_code, re.IGNORECASE):
                        found_patterns.append(pattern)
                
                if found_patterns:
                    analysis['is_upgradeable'] = True
                    analysis['upgrade_controls'] = found_patterns
                    analysis['immutability_score'] = max(0.1, 1.0 - (len(found_patterns) * 0.2))
                    
                    if len(found_patterns) >= 3:
                        analysis['upgrade_risk'] = 'CRITICAL'
                    elif len(found_patterns) >= 2:
                        analysis['upgrade_risk'] = 'HIGH'
                    else:
                        analysis['upgrade_risk'] = 'MEDIUM'
            
        except Exception as e:
            logger.warning(f"Error assessing upgrade mechanisms: {e}")
        
        return analysis
    
    async def _calculate_contract_metrics(self, contract_data: Dict[str, Any]) -> ContractMetrics:
        """Calculate overall contract quality and security metrics."""
        source_code = contract_data.get('source_code', '')
        bytecode = contract_data.get('bytecode', '')
        
        try:
            await asyncio.sleep(0.05)
            
            # Count function types
            if source_code:
                all_functions = re.findall(r'function\s+\w+', source_code, re.IGNORECASE)
                public_functions = re.findall(r'function\s+\w+.*public', source_code, re.IGNORECASE)
                external_functions = re.findall(r'function\s+\w+.*external', source_code, re.IGNORECASE)
                payable_functions = re.findall(r'function\s+\w+.*payable', source_code, re.IGNORECASE)
                
                total_functions = len(all_functions)
                public_count = len(public_functions)
                external_count = len(external_functions)
                payable_count = len(payable_functions)
            else:
                total_functions = 0
                public_count = 0
                external_count = 0
                payable_count = 0
            
            # Calculate complexity score
            complexity_score = self._calculate_overall_complexity(source_code, bytecode)
            
            # Calculate code quality score
            code_quality_score = self._calculate_code_quality(source_code)
            
            # Calculate security score (inverse of risk)
            security_score = self._calculate_security_score(source_code, contract_data)
            
            # Determine audit status
            audit_reports = contract_data.get('audit_reports', [])
            if len(audit_reports) > 0:
                audit_status = 'PROFESSIONALLY_AUDITED'
            elif contract_data.get('verification_status') == 'VERIFIED':
                audit_status = 'SELF_AUDITED'
            else:
                audit_status = 'UNAUDITED'
            
            # Verification status
            verification_status = contract_data.get('verification_status', 'UNVERIFIED')
            if contract_data.get('proxy_type'):
                verification_status = 'PROXY'
            
            return ContractMetrics(
                total_functions=total_functions,
                public_functions=public_count,
                external_functions=external_count,
                payable_functions=payable_count,
                complexity_score=complexity_score,
                code_quality_score=code_quality_score,
                security_score=security_score,
                audit_status=audit_status,
                verification_status=verification_status
            )
            
        except Exception as e:
            logger.warning(f"Error calculating contract metrics: {e}")
            return ContractMetrics(
                total_functions=0,
                public_functions=0,
                external_functions=0,
                payable_functions=0,
                complexity_score=0.5,
                code_quality_score=0.5,
                security_score=0.5,
                audit_status='UNKNOWN',
                verification_status='UNKNOWN'
            )
    
    def _calculate_security_risk_score(
        self,
        vulnerabilities: List[SecurityVulnerability],
        ownership_analysis: Optional[OwnershipAnalysis],
        malicious_patterns: List[Dict[str, Any]],
        contract_metrics: Optional[ContractMetrics]
    ) -> float:
        """Calculate overall security risk score."""
        risk_factors = []
        
        # Vulnerability risk
        critical_vulns = [v for v in vulnerabilities if v.severity == 'CRITICAL']
        high_vulns = [v for v in vulnerabilities if v.severity == 'HIGH']
        
        if critical_vulns:
            risk_factors.append(0.9)  # Critical vulnerabilities = very high risk
        elif high_vulns:
            risk_factors.append(0.7)
        elif vulnerabilities:
            risk_factors.append(0.4)
        else:
            risk_factors.append(0.1)
        
        # Ownership risk
        if ownership_analysis:
            if ownership_analysis.centralization_risk == 'CRITICAL':
                risk_factors.append(0.8)
            elif ownership_analysis.centralization_risk == 'HIGH':
                risk_factors.append(0.6)
            elif ownership_analysis.centralization_risk == 'MEDIUM':
                risk_factors.append(0.4)
            else:
                risk_factors.append(0.2)
        
        # Malicious pattern risk
        critical_patterns = [p for p in malicious_patterns if p.get('severity') == 'CRITICAL']
        if critical_patterns:
            risk_factors.append(0.95)
        elif malicious_patterns:
            risk_factors.append(0.6)
        else:
            risk_factors.append(0.1)
        
        # Contract metrics risk
        if contract_metrics:
            if contract_metrics.verification_status == 'UNVERIFIED':
                risk_factors.append(0.6)
            elif contract_metrics.audit_status == 'UNAUDITED':
                risk_factors.append(0.4)
            else:
                risk_factors.append(0.2)
            
            if contract_metrics.security_score < 0.3:
                risk_factors.append(0.7)
            elif contract_metrics.security_score < 0.6:
                risk_factors.append(0.5)
            else:
                risk_factors.append(0.2)
        
        return sum(risk_factors) / len(risk_factors) if risk_factors else 0.5
    
    def _generate_security_warnings(
        self,
        vulnerabilities: List[SecurityVulnerability],
        ownership_analysis: Optional[OwnershipAnalysis],
        malicious_patterns: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate security warnings based on analysis."""
        warnings = []
        
        # Vulnerability warnings
        critical_vulns = [v for v in vulnerabilities if v.severity == 'CRITICAL']
        high_vulns = [v for v in vulnerabilities if v.severity == 'HIGH']
        
        if critical_vulns:
            warnings.append(f"CRITICAL: {len(critical_vulns)} critical security vulnerabilities found")
        
        if high_vulns:
            warnings.append(f"HIGH RISK: {len(high_vulns)} high-severity vulnerabilities detected")
        
        # Ownership warnings
        if ownership_analysis:
            if ownership_analysis.centralization_risk in ['CRITICAL', 'HIGH']:
                warnings.append(f"High centralization risk: {len(ownership_analysis.admin_functions)} admin functions")
            
            if not ownership_analysis.is_renounced and ownership_analysis.has_owner:
                warnings.append("Contract ownership not renounced - centralization risk")
        
        # Malicious pattern warnings
        for pattern in malicious_patterns:
            if pattern.get('severity') in ['CRITICAL', 'HIGH']:
                warnings.append(f"Suspicious pattern detected: {pattern.get('pattern_name')}")
        
        return warnings
    
    # Helper methods for contract analysis
    def _find_function_end(self, source_code: str, start_pos: int) -> int:
        """Find the end of a function body."""
        brace_count = 0
        i = start_pos
        
        while i < len(source_code):
            if source_code[i] == '{':
                brace_count += 1
            elif source_code[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return i
            i += 1
        
        return len(source_code)
    
    def _calculate_function_complexity(self, func_body: str) -> float:
        """Calculate function complexity score."""
        # Simple complexity based on control structures and calls
        complexity_indicators = [
            'if', 'else', 'for', 'while', 'require', 'assert',
            '.call', '.delegatecall', '.transfer', '.send'
        ]
        
        complexity_count = 0
        for indicator in complexity_indicators:
            complexity_count += len(re.findall(indicator, func_body, re.IGNORECASE))
        
        # Normalize to 0-1 scale
        return min(complexity_count / 10, 1.0)
    
    def _calculate_overall_complexity(self, source_code: str, bytecode: str) -> float:
        """Calculate overall contract complexity."""
        if source_code:
            lines = len(source_code.split('\n'))
            functions = len(re.findall(r'function\s+\w+', source_code, re.IGNORECASE))
            complexity = (lines / 1000) + (functions / 50)
        else:
            # Use bytecode size as proxy
            complexity = len(bytecode) / 50000 if bytecode else 0.5
        
        return min(complexity, 1.0)
    
    def _calculate_code_quality(self, source_code: str) -> float:
        """Calculate code quality score."""
        if not source_code:
            return 0.3  # Low quality if no source available
        
        quality_indicators = {
            'has_comments': bool(re.search(r'//|/\*', source_code)),
            'has_natspec': bool(re.search(r'///', source_code)),
            'uses_safemath': bool(re.search(r'SafeMath|using.*for', source_code, re.IGNORECASE)),
            'has_events': bool(re.search(r'event\s+\w+', source_code, re.IGNORECASE)),
            'proper_visibility': not bool(re.search(r'function\s+\w+\s*\([^)]*\)\s*\{', source_code)),
            'has_modifiers': bool(re.search(r'modifier\s+\w+', source_code, re.IGNORECASE))
        }
        
        score = sum(quality_indicators.values()) / len(quality_indicators)
        return score
    
    def _calculate_security_score(self, source_code: str, contract_data: Dict[str, Any]) -> float:
        """Calculate security score based on various factors."""
        score_components = []
        
        # Verification status
        if contract_data.get('verification_status') == 'VERIFIED':
            score_components.append(0.8)
        else:
            score_components.append(0.2)
        
        # Audit status
        audit_reports = contract_data.get('audit_reports', [])
        if audit_reports:
            score_components.append(0.9)
        else:
            score_components.append(0.4)
        
        # Source code security patterns
        if source_code:
            security_patterns = {
                'uses_require': bool(re.search(r'require\s*\(', source_code)),
                'checks_overflow': bool(re.search(r'SafeMath|overflow|underflow', source_code, re.IGNORECASE)),
                'reentrancy_guard': bool(re.search(r'nonReentrant|ReentrancyGuard', source_code, re.IGNORECASE)),
                'proper_access_control': bool(re.search(r'onlyOwner|modifier', source_code, re.IGNORECASE)),
                'event_logging': bool(re.search(r'emit\s+\w+', source_code, re.IGNORECASE))
            }
            
            pattern_score = sum(security_patterns.values()) / len(security_patterns)
            score_components.append(pattern_score)
        else:
            score_components.append(0.3)
        
        return sum(score_components) / len(score_components)
    
    def _generate_mock_source_code(self) -> str:
        """Generate mock source code for testing."""
        return '''
        pragma solidity ^0.8.0;
        
        contract MockERC20 {
            string public name = "Mock Token";
            string public symbol = "MOCK";
            uint8 public decimals = 18;
            uint256 public totalSupply;
            
            mapping(address => uint256) public balanceOf;
            mapping(address => mapping(address => uint256)) public allowance;
            
            address public owner;
            
            modifier onlyOwner() {
                require(msg.sender == owner, "Not owner");
                _;
            }
            
            constructor(uint256 _totalSupply) {
                totalSupply = _totalSupply;
                balanceOf[msg.sender] = _totalSupply;
                owner = msg.sender;
            }
            
            function transfer(address to, uint256 amount) public returns (bool) {
                require(balanceOf[msg.sender] >= amount, "Insufficient balance");
                balanceOf[msg.sender] -= amount;
                balanceOf[to] += amount;
                return true;
            }
            
            function mint(address to, uint256 amount) public onlyOwner {
                totalSupply += amount;
                balanceOf[to] += amount;
            }
        }
        '''
    
    def _load_vulnerability_patterns(self) -> List[Dict[str, Any]]:
        """Load known vulnerability patterns."""
        return [
            {
                'name': 'reentrancy',
                'pattern': r'\.call\.value\s*\(',
                'severity': 'CRITICAL',
                'description': 'Potential reentrancy vulnerability'
            },
            {
                'name': 'tx_origin',
                'pattern': r'tx\.origin',
                'severity': 'HIGH',
                'description': 'Dangerous use of tx.origin'
            },
            {
                'name': 'unchecked_call',
                'pattern': r'\.call\s*\([^)]*\)\s*;',
                'severity': 'MEDIUM',
                'description': 'Unchecked external call'
            }
        ]
    
    def _load_malicious_patterns(self) -> List[Dict[str, Any]]:
        """Load known malicious contract patterns."""
        return [
            {
                'name': 'hidden_mint',
                'type': 'SOURCE_PATTERN',
                'pattern': r'function\s+\w*\s*\([^)]*\)\s*[^{]*\{\s*[^}]*totalSupply\s*\+=',
                'severity': 'HIGH',
                'description': 'Hidden mint function detected',
                'confidence': 0.7
            },
            {
                'name': 'backdoor_transfer',
                'type': 'SOURCE_PATTERN',
                'pattern': r'if\s*\([^)]*==\s*0x[a-fA-F0-9]{40}[^)]*\)',
                'severity': 'MEDIUM',
                'description': 'Potential backdoor in transfer logic',
                'confidence': 0.6
            }
        ]
    
    def _validate_inputs(self, token_address: str, context: Dict[str, Any]) -> bool:
        """Validate inputs for contract analysis."""
        if not token_address or len(token_address) != 42:
            return False
        
        if not token_address.startswith('0x'):
            return False
        
        return True
    
    def _create_error_risk_score(self, error_message: str) -> RiskScore:
        """Create error risk score for failed analysis."""
        return RiskScore(
            category=self.get_category(),
            score=0.8,  # High risk when analysis fails
            confidence=0.1,
            details={'error': error_message, 'analysis_failed': True},
            analysis_time_ms=0.0,
            warnings=[error_message],
            data_quality="POOR"
        )
    
    def _create_timeout_risk_score(self) -> RiskScore:
        """Create risk score for timeout scenarios."""
        return RiskScore(
            category=self.get_category(),
            score=0.7,  # High risk on timeout due to security importance
            confidence=0.1,
            details={'timeout': True, 'analysis_incomplete': True},
            analysis_time_ms=20000.0,
            warnings=["Contract analysis timed out - security assessment incomplete"],
            data_quality="POOR"
        )
    
    def _get_cached_analysis(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get cached contract analysis if available and fresh."""
        if token_address in self.contract_cache:
            result, timestamp = self.contract_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_hours * 3600):
                return result
            else:
                del self.contract_cache[token_address]
        
        return None
    
    def _cache_analysis_result(self, token_address: str, result: Dict[str, Any]) -> None:
        """Cache contract analysis result."""
        self.contract_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries
        if len(self.contract_cache) > 100:
            sorted_entries = sorted(
                self.contract_cache.items(),
                key=lambda x: x[1][1]
            )
            for token, _ in sorted_entries[:20]:
                del self.contract_cache[token]
    
    def _create_risk_score_from_cache(self, cached_result: Dict[str, Any]) -> RiskScore:
        """Create risk score from cached analysis."""
        vulnerabilities = cached_result.get('vulnerabilities', [])
        ownership_analysis = cached_result.get('ownership_analysis')
        malicious_patterns = cached_result.get('malicious_patterns', [])
        contract_metrics = cached_result.get('contract_metrics')
        
        risk_score = self._calculate_security_risk_score(
            vulnerabilities, ownership_analysis, malicious_patterns, contract_metrics
        )
        
        return RiskScore(
            category=self.get_category(),
            score=risk_score,
            confidence=0.8,  # High confidence for cached analysis
            details={**cached_result, 'from_cache': True},
            analysis_time_ms=10.0,  # Fast cache retrieval
            warnings=self._generate_security_warnings(vulnerabilities, ownership_analysis, malicious_patterns),
            data_quality="GOOD",
            last_updated=datetime.now(timezone.utc).isoformat()
        )
    
    def _assess_contract_data_quality(self, contract_data: Dict[str, Any]) -> str:
        """Assess the quality of contract data available for analysis."""
        has_source = bool(contract_data.get('source_code'))
        has_bytecode = bool(contract_data.get('bytecode'))
        is_verified = contract_data.get('verification_status') == 'VERIFIED'
        has_audit = bool(contract_data.get('audit_reports'))
        
        if has_source and is_verified and has_audit:
            return "EXCELLENT"
        elif has_source and is_verified:
            return "GOOD"
        elif has_bytecode and (has_source or is_verified):
            return "FAIR"
        else:
            return "POOR"
    
    def _calculate_analysis_confidence(
        self,
        contract_data: Dict[str, Any],
        vulnerabilities: List[SecurityVulnerability]
    ) -> float:
        """Calculate confidence level for the analysis."""
        confidence_factors = []
        
        # Data availability factor
        if contract_data.get('source_code'):
            confidence_factors.append(0.9)
        elif contract_data.get('bytecode'):
            confidence_factors.append(0.6)
        else:
            confidence_factors.append(0.2)
        
        # Verification factor
        if contract_data.get('verification_status') == 'VERIFIED':
            confidence_factors.append(0.8)
        else:
            confidence_factors.append(0.4)
        
        # Analysis completeness factor
        if vulnerabilities:
            avg_vuln_confidence = sum(v.confidence for v in vulnerabilities) / len(vulnerabilities)
            confidence_factors.append(avg_vuln_confidence)
        else:
            confidence_factors.append(0.7)  # No vulnerabilities found is also valuable
        
        return sum(confidence_factors) / len(confidence_factors)


# Export the analyzer class
__all__ = [
    'ContractAnalyzer',
    'SecurityVulnerability', 
    'ContractFunction',
    'OwnershipAnalysis',
    'ContractMetrics'
]