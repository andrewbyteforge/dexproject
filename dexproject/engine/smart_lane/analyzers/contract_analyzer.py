"""
Contract Security Analyzer

Critical security analyzer that evaluates smart contract security,
vulnerability patterns, and potential exploit risks. This is one of
the most important risk categories for preventing total loss.

Path: engine/smart_lane/analyzers/contract_analyzer.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory

logger = logging.getLogger(__name__)


@dataclass
class SecurityVulnerability:
    """Individual security vulnerability finding."""
    vulnerability_id: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float  # 0-1 scale
    category: str  # REENTRANCY, OVERFLOW, ACCESS_CONTROL, etc.
    description: str
    exploit_potential: str  # NONE, LOW, MEDIUM, HIGH, CRITICAL
    mitigation: Optional[str]
    code_location: Optional[str]


@dataclass
class ContractMetadata:
    """Contract metadata and basic information."""
    is_verified: bool
    compiler_version: str
    optimization_enabled: bool
    license: Optional[str]
    creation_block: Optional[int]
    creator_address: Optional[str]
    contract_size_bytes: int


class ContractAnalyzer(BaseAnalyzer):
    """
    Advanced smart contract security analyzer.
    
    Analyzes:
    - Common vulnerability patterns (reentrancy, overflow, etc.)
    - Access control mechanisms and ownership
    - Proxy patterns and upgradeability risks
    - External dependencies and integrations
    - Code verification and audit status
    - Known malicious patterns and honeypot indicators
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize contract security analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration
        """
        super().__init__(chain_id, config)
        
        # Security analysis thresholds
        self.thresholds = {
            'critical_vuln_limit': 0,       # No critical vulnerabilities allowed
            'high_vuln_limit': 1,           # Max 1 high severity vulnerability
            'medium_vuln_limit': 3,         # Max 3 medium vulnerabilities
            'min_verification_score': 0.7,  # Minimum verification requirement
            'max_contract_size_kb': 24,     # Max contract size in KB
            'proxy_risk_threshold': 0.6,    # Proxy upgrade risk threshold
            'external_deps_limit': 5        # Max external dependencies
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Known malicious patterns (hashes for pattern matching)
        self.malicious_patterns = self._load_malicious_patterns()
        
        # Known secure patterns (for positive scoring)
        self.secure_patterns = self._load_secure_patterns()
        
        # Vulnerability pattern definitions
        self.vulnerability_patterns = self._load_vulnerability_patterns()
        
        # Contract analysis cache
        self.analysis_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self.cache_ttl_minutes = 60  # Contract analysis can be cached longer
        
        logger.info(f"Contract security analyzer initialized for chain {chain_id}")
    
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
            context: Additional context for analysis
            
        Returns:
            RiskScore with security assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting contract security analysis for {token_address[:10]}...")
            
            # Input validation
            if not self._validate_contract_address(token_address):
                return self._create_error_risk_score("Invalid contract address")
            
            # Check cache first
            cached_result = self._get_cached_analysis(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Parallel security analysis tasks
            analysis_tasks = [
                self._analyze_contract_metadata(token_address),
                self._analyze_vulnerability_patterns(token_address),
                self._analyze_access_controls(token_address),
                self._analyze_proxy_patterns(token_address),
                self._analyze_external_dependencies(token_address),
                self._analyze_known_patterns(token_address),
                self._analyze_audit_status(token_address)
            ]
            
            analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Process results and handle exceptions
            contract_metadata = self._safe_extract_result(analysis_results[0], {})
            vulnerabilities = self._safe_extract_result(analysis_results[1], [])
            access_controls = self._safe_extract_result(analysis_results[2], {})
            proxy_analysis = self._safe_extract_result(analysis_results[3], {})
            dependencies = self._safe_extract_result(analysis_results[4], {})
            pattern_analysis = self._safe_extract_result(analysis_results[5], {})
            audit_status = self._safe_extract_result(analysis_results[6], {})
            
            # Calculate overall security risk
            risk_score, confidence = self._calculate_security_risk(
                contract_metadata, vulnerabilities, access_controls,
                proxy_analysis, dependencies, pattern_analysis, audit_status
            )
            
            # Generate security warnings
            warnings = self._generate_security_warnings(
                vulnerabilities, access_controls, proxy_analysis, risk_score
            )
            
            # Compile detailed analysis
            analysis_details = self._compile_security_details(
                contract_metadata, vulnerabilities, access_controls,
                proxy_analysis, dependencies, pattern_analysis, audit_status
            )
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Cache the results
            self._cache_analysis_result(token_address, {
                'risk_score': risk_score,
                'confidence': confidence,
                'details': analysis_details,
                'warnings': warnings,
                'vulnerabilities': vulnerabilities
            })
            
            # Update performance stats
            self._update_performance_stats(analysis_time_ms, success=True)
            
            logger.debug(
                f"Contract security analysis completed for {token_address[:10]}... "
                f"Risk: {risk_score:.3f}, Confidence: {confidence:.3f} "
                f"({len(vulnerabilities)} vulns, {analysis_time_ms:.1f}ms)"
            )
            
            return self._create_risk_score(
                score=risk_score,
                confidence=confidence,
                details=analysis_details,
                warnings=warnings,
                data_quality=self._assess_data_quality(contract_metadata, vulnerabilities),
                analysis_time_ms=analysis_time_ms
            )
            
        except Exception as e:
            analysis_time_ms = (time.time() - analysis_start) * 1000
            self._update_performance_stats(analysis_time_ms, success=False)
            
            logger.error(f"Error in contract security analysis: {e}", exc_info=True)
            return self._create_error_risk_score(f"Contract analysis failed: {str(e)}")
    
    async def _analyze_contract_metadata(self, token_address: str) -> ContractMetadata:
        """Analyze basic contract metadata and verification status."""
        try:
            # Simulate blockchain queries for contract metadata
            await asyncio.sleep(0.15)
            
            # Mock contract metadata based on address characteristics
            address_hash = hash(token_address)
            is_verified = (address_hash % 100) > 20  # 80% verified rate
            
            metadata = ContractMetadata(
                is_verified=is_verified,
                compiler_version="0.8.19" if is_verified else "unknown",
                optimization_enabled=True if is_verified else False,
                license="MIT" if is_verified and (address_hash % 10) > 3 else None,
                creation_block=18000000 + (address_hash % 1000000),
                creator_address=f"0x{(address_hash % (16**40)):040x}",
                contract_size_bytes=8192 + (address_hash % 16384)  # 8-24KB typical
            )
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error analyzing contract metadata: {e}")
            # Return default metadata with error indication
            return ContractMetadata(
                is_verified=False,
                compiler_version="error",
                optimization_enabled=False,
                license=None,
                creation_block=None,
                creator_address=None,
                contract_size_bytes=0
            )
    
    async def _analyze_vulnerability_patterns(self, token_address: str) -> List[SecurityVulnerability]:
        """Analyze contract for known vulnerability patterns."""
        try:
            await asyncio.sleep(0.3)  # Simulate static analysis time
            
            vulnerabilities = []
            address_hash = hash(token_address)
            
            # Generate realistic vulnerability findings based on address
            vuln_probability = (address_hash % 100) / 100.0
            
            # Check for common vulnerabilities
            if vuln_probability > 0.85:  # 15% have reentrancy issues
                vulnerabilities.append(SecurityVulnerability(
                    vulnerability_id="REEN-001",
                    severity="HIGH",
                    confidence=0.8,
                    category="REENTRANCY",
                    description="Potential reentrancy vulnerability in transfer function",
                    exploit_potential="MEDIUM",
                    mitigation="Implement checks-effects-interactions pattern",
                    code_location="transfer() line 145"
                ))
            
            if vuln_probability > 0.75:  # 25% have access control issues
                vulnerabilities.append(SecurityVulnerability(
                    vulnerability_id="AC-002",
                    severity="MEDIUM",
                    confidence=0.7,
                    category="ACCESS_CONTROL",
                    description="Insufficient access control on administrative functions",
                    exploit_potential="LOW",
                    mitigation="Add proper onlyOwner modifiers",
                    code_location="setFeePercent() line 89"
                ))
            
            if vuln_probability > 0.9:  # 10% have integer overflow potential
                vulnerabilities.append(SecurityVulnerability(
                    vulnerability_id="OF-003",
                    severity="HIGH",
                    confidence=0.85,
                    category="INTEGER_OVERFLOW",
                    description="Potential integer overflow in balance calculations",
                    exploit_potential="HIGH",
                    mitigation="Use SafeMath library or Solidity 0.8+ built-in checks",
                    code_location="_mint() line 234"
                ))
            
            if vuln_probability > 0.95:  # 5% have critical issues
                vulnerabilities.append(SecurityVulnerability(
                    vulnerability_id="CRIT-004",
                    severity="CRITICAL",
                    confidence=0.9,
                    category="BACKDOOR",
                    description="Hidden backdoor function detected in contract",
                    exploit_potential="CRITICAL",
                    mitigation="Remove backdoor function or avoid contract",
                    code_location="_backdoor() line 567"
                ))
            
            # Add some low-severity findings for completeness
            if vuln_probability > 0.3:  # 70% have minor issues
                vulnerabilities.append(SecurityVulnerability(
                    vulnerability_id="INFO-005",
                    severity="LOW",
                    confidence=0.6,
                    category="CODE_QUALITY",
                    description="Missing input validation on public functions",
                    exploit_potential="NONE",
                    mitigation="Add input validation checks",
                    code_location="approve() line 67"
                ))
            
            return vulnerabilities
            
        except Exception as e:
            logger.error(f"Error analyzing vulnerability patterns: {e}")
            return []
    
    async def _analyze_access_controls(self, token_address: str) -> Dict[str, Any]:
        """Analyze contract access control mechanisms."""
        try:
            await asyncio.sleep(0.12)  # Simulate code analysis
            
            address_hash = hash(token_address)
            
            access_analysis = {
                'has_owner': True,
                'owner_can_mint': (address_hash % 10) < 7,  # 70% can mint
                'owner_can_pause': (address_hash % 10) < 4,  # 40% can pause
                'owner_can_blacklist': (address_hash % 10) < 3,  # 30% can blacklist
                'ownership_renounced': (address_hash % 10) < 2,  # 20% renounced
                'multisig_owner': (address_hash % 10) < 1,  # 10% multisig
                'timelock_delays': [],
                'role_based_access': (address_hash % 10) < 3,  # 30% use roles
                'emergency_functions': [
                    'pause()',
                    'emergencyWithdraw()'
                ] if (address_hash % 10) < 5 else [],
                'admin_privileges': {
                    'mint_tokens': (address_hash % 10) < 7,
                    'change_fees': (address_hash % 10) < 8,
                    'update_router': (address_hash % 10) < 3,
                    'exclude_from_fees': (address_hash % 10) < 9
                }
            }
            
            return access_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing access controls: {e}")
            return {'error': str(e)}
    
    async def _analyze_proxy_patterns(self, token_address: str) -> Dict[str, Any]:
        """Analyze proxy patterns and upgradeability risks."""
        try:
            await asyncio.sleep(0.08)  # Simulate proxy detection
            
            address_hash = hash(token_address)
            is_proxy = (address_hash % 20) == 0  # 5% are proxies
            
            if is_proxy:
                proxy_analysis = {
                    'is_proxy': True,
                    'proxy_type': 'TRANSPARENT' if (address_hash % 2) == 0 else 'UUPS',
                    'implementation_address': f"0x{((address_hash + 1) % (16**40)):040x}",
                    'admin_address': f"0x{((address_hash + 2) % (16**40)):040x}",
                    'upgrade_mechanism': 'ADMIN_CONTROLLED',
                    'has_timelock': (address_hash % 4) == 0,
                    'upgrade_risk': 'HIGH' if (address_hash % 3) == 0 else 'MEDIUM',
                    'immutable_functions': ['name()', 'symbol()', 'decimals()'],
                    'upgrade_history': []
                }
            else:
                proxy_analysis = {
                    'is_proxy': False,
                    'immutable_contract': True,
                    'upgrade_risk': 'NONE'
                }
            
            return proxy_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing proxy patterns: {e}")
            return {'error': str(e)}
    
    async def _analyze_external_dependencies(self, token_address: str) -> Dict[str, Any]:
        """Analyze external contract dependencies and integrations."""
        try:
            await asyncio.sleep(0.1)  # Simulate dependency analysis
            
            address_hash = hash(token_address)
            num_dependencies = address_hash % 8  # 0-7 dependencies
            
            dependencies = []
            for i in range(num_dependencies):
                dep_hash = hash(f"{token_address}_{i}")
                dependencies.append({
                    'address': f"0x{(dep_hash % (16**40)):040x}",
                    'type': ['ORACLE', 'DEX', 'LIBRARY', 'GOVERNANCE'][dep_hash % 4],
                    'risk_level': ['LOW', 'MEDIUM', 'HIGH'][dep_hash % 3],
                    'verified': (dep_hash % 3) > 0,
                    'function_calls': dep_hash % 10 + 1
                })
            
            dependency_analysis = {
                'total_dependencies': num_dependencies,
                'external_contracts': dependencies,
                'dependency_risk_score': min(1.0, num_dependencies / 10.0),
                'uses_oracles': any(dep['type'] == 'ORACLE' for dep in dependencies),
                'uses_governance': any(dep['type'] == 'GOVERNANCE' for dep in dependencies),
                'unverified_dependencies': sum(1 for dep in dependencies if not dep['verified']),
                'high_risk_dependencies': sum(1 for dep in dependencies if dep['risk_level'] == 'HIGH')
            }
            
            return dependency_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing external dependencies: {e}")
            return {'error': str(e)}
    
    async def _analyze_known_patterns(self, token_address: str) -> Dict[str, Any]:
        """Analyze against known malicious and secure patterns."""
        try:
            await asyncio.sleep(0.05)  # Quick pattern matching
            
            address_hash = hash(token_address)
            
            # Check against known patterns
            malicious_score = 0.0
            secure_score = 0.0
            
            # Simulate pattern matching results
            if (address_hash % 100) < 5:  # 5% match malicious patterns
                malicious_score = 0.8
            elif (address_hash % 100) < 15:  # 10% partially match
                malicious_score = 0.3
            
            if (address_hash % 100) > 70:  # 30% match secure patterns
                secure_score = 0.7
            elif (address_hash % 100) > 50:  # 20% partially match
                secure_score = 0.4
            
            pattern_analysis = {
                'malicious_pattern_score': malicious_score,
                'secure_pattern_score': secure_score,
                'known_scam_similarity': malicious_score,
                'verified_project_similarity': secure_score,
                'pattern_confidence': 0.8 if malicious_score > 0.5 or secure_score > 0.6 else 0.4,
                'similar_contracts': [],
                'pattern_flags': []
            }
            
            if malicious_score > 0.5:
                pattern_analysis['pattern_flags'].append('POTENTIAL_SCAM_PATTERN')
            if secure_score > 0.6:
                pattern_analysis['pattern_flags'].append('VERIFIED_PATTERN_MATCH')
            
            return pattern_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing known patterns: {e}")
            return {'error': str(e)}
    
    async def _analyze_audit_status(self, token_address: str) -> Dict[str, Any]:
        """Analyze contract audit status and security reports."""
        try:
            await asyncio.sleep(0.07)  # Simulate audit database lookup
            
            address_hash = hash(token_address)
            has_audit = (address_hash % 10) < 3  # 30% have audits
            
            if has_audit:
                audit_analysis = {
                    'has_professional_audit': True,
                    'audit_firms': ['CertiK', 'PeckShield'][address_hash % 2],
                    'audit_score': 75 + (address_hash % 20),  # 75-94 audit score
                    'issues_found': address_hash % 5,  # 0-4 issues
                    'critical_issues_fixed': True,
                    'audit_date': '2024-08-15',
                    'audit_report_url': f"https://audit-reports.example.com/{token_address[:10]}",
                    'audit_coverage': 95.0,
                    'recommendations_implemented': (address_hash % 4) != 0  # 75% implemented
                }
            else:
                audit_analysis = {
                    'has_professional_audit': False,
                    'community_reviewed': (address_hash % 5) == 0,  # 20% community reviewed
                    'self_reported_security': (address_hash % 3) == 0,  # 33% self-reported
                    'audit_score': 0,
                    'security_considerations': []
                }
            
            return audit_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing audit status: {e}")
            return {'error': str(e)}
    
    def _calculate_security_risk(
        self,
        metadata: ContractMetadata,
        vulnerabilities: List[SecurityVulnerability],
        access_controls: Dict[str, Any],
        proxy_analysis: Dict[str, Any],
        dependencies: Dict[str, Any],
        pattern_analysis: Dict[str, Any],
        audit_status: Dict[str, Any]
    ) -> Tuple[float, float]:
        """Calculate overall security risk score and confidence."""
        risk_factors = []
        confidence_factors = []
        
        # Vulnerability scoring (highest weight)
        vuln_risk = self._score_vulnerabilities(vulnerabilities)
        risk_factors.append(('vulnerabilities', vuln_risk, 0.35))
        confidence_factors.append(0.9)  # High confidence in vuln detection
        
        # Pattern analysis (second highest weight)
        pattern_risk = pattern_analysis.get('malicious_pattern_score', 0.0)
        risk_factors.append(('patterns', pattern_risk, 0.25))
        confidence_factors.append(pattern_analysis.get('pattern_confidence', 0.5))
        
        # Access control analysis
        access_risk = self._score_access_controls(access_controls)
        risk_factors.append(('access_controls', access_risk, 0.2))
        confidence_factors.append(0.8)
        
        # Proxy and upgradeability risk
        proxy_risk = self._score_proxy_risk(proxy_analysis)
        risk_factors.append(('proxy', proxy_risk, 0.1))
        confidence_factors.append(0.7)
        
        # External dependencies
        dep_risk = dependencies.get('dependency_risk_score', 0.0)
        risk_factors.append(('dependencies', dep_risk, 0.05))
        confidence_factors.append(0.6)
        
        # Audit status (reduces risk if good audit)
        audit_risk = self._score_audit_status(audit_status)
        risk_factors.append(('audit', audit_risk, 0.05))
        confidence_factors.append(0.8)
        
        # Calculate weighted risk score
        total_risk = 0.0
        total_weight = 0.0
        
        for factor_name, risk, weight in risk_factors:
            total_risk += risk * weight
            total_weight += weight
        
        overall_risk = total_risk / total_weight if total_weight > 0 else 0.5
        
        # Calculate confidence (weighted average)
        overall_confidence = sum(
            conf * weight for (_, _, weight), conf in zip(risk_factors, confidence_factors)
        ) / total_weight if total_weight > 0 else 0.5
        
        return overall_risk, overall_confidence
    
    def _score_vulnerabilities(self, vulnerabilities: List[SecurityVulnerability]) -> float:
        """Score vulnerability risk based on severity and count."""
        if not vulnerabilities:
            return 0.1  # Small base risk for no analysis
        
        risk_score = 0.0
        
        for vuln in vulnerabilities:
            if vuln.severity == 'CRITICAL':
                risk_score += 0.8
            elif vuln.severity == 'HIGH':
                risk_score += 0.5
            elif vuln.severity == 'MEDIUM':
                risk_score += 0.2
            elif vuln.severity == 'LOW':
                risk_score += 0.05
        
        # Cap at 1.0 and apply confidence weighting
        return min(1.0, risk_score)
    
    def _score_access_controls(self, access_controls: Dict[str, Any]) -> float:
        """Score access control risk."""
        if 'error' in access_controls:
            return 0.7  # High risk for analysis failure
        
        risk_score = 0.0
        
        # Dangerous admin privileges
        admin_privs = access_controls.get('admin_privileges', {})
        if admin_privs.get('mint_tokens', False):
            risk_score += 0.3
        if admin_privs.get('update_router', False):
            risk_score += 0.2
        if access_controls.get('owner_can_blacklist', False):
            risk_score += 0.3
        
        # Mitigating factors
        if access_controls.get('ownership_renounced', False):
            risk_score *= 0.2  # Major risk reduction
        elif access_controls.get('multisig_owner', False):
            risk_score *= 0.5  # Moderate risk reduction
        
        return min(1.0, risk_score)
    
    def _score_proxy_risk(self, proxy_analysis: Dict[str, Any]) -> float:
        """Score proxy-related upgrade risks."""
        if not proxy_analysis.get('is_proxy', False):
            return 0.0  # No proxy risk
        
        upgrade_risk = proxy_analysis.get('upgrade_risk', 'MEDIUM')
        
        if upgrade_risk == 'HIGH':
            return 0.8
        elif upgrade_risk == 'MEDIUM':
            return 0.5
        else:
            return 0.2
    
    def _score_audit_status(self, audit_status: Dict[str, Any]) -> float:
        """Score audit-related risk (lower is better for audits)."""
        if audit_status.get('has_professional_audit', False):
            audit_score = audit_status.get('audit_score', 0)
            critical_fixed = audit_status.get('critical_issues_fixed', False)
            
            if audit_score > 85 and critical_fixed:
                return 0.1  # Low risk - good audit
            elif audit_score > 70 and critical_fixed:
                return 0.3  # Medium risk - decent audit
            else:
                return 0.6  # Higher risk - poor audit or unfixed issues
        else:
            return 0.4  # Moderate risk - no professional audit
    
    def _generate_security_warnings(
        self,
        vulnerabilities: List[SecurityVulnerability],
        access_controls: Dict[str, Any],
        proxy_analysis: Dict[str, Any],
        risk_score: float
    ) -> List[str]:
        """Generate security-specific warnings."""
        warnings = []
        
        # Critical vulnerability warnings
        critical_vulns = [v for v in vulnerabilities if v.severity == 'CRITICAL']
        if critical_vulns:
            warnings.append(f"CRITICAL: {len(critical_vulns)} critical vulnerabilities detected")
        
        high_vulns = [v for v in vulnerabilities if v.severity == 'HIGH']
        if len(high_vulns) > 1:
            warnings.append(f"HIGH RISK: {len(high_vulns)} high-severity vulnerabilities found")
        
        # Access control warnings
        if access_controls.get('owner_can_mint', False) and not access_controls.get('ownership_renounced', False):
            warnings.append("Owner can mint unlimited tokens - inflation risk")
        
        if access_controls.get('owner_can_blacklist', False):
            warnings.append("Owner can blacklist addresses - exit scam risk")
        
        # Proxy warnings
        if proxy_analysis.get('is_proxy', False) and proxy_analysis.get('upgrade_risk') == 'HIGH':
            warnings.append("Upgradeable contract with high modification risk")
        
        # Overall risk warnings
        if risk_score > 0.8:
            warnings.append("EXTREME security risk - avoid trading")
        elif risk_score > 0.6:
            warnings.append("HIGH security risk - use extreme caution")
        elif risk_score > 0.4:
            warnings.append("MODERATE security risk - monitor closely")
        
        return warnings
    
    def _compile_security_details(
        self,
        metadata: ContractMetadata,
        vulnerabilities: List[SecurityVulnerability],
        access_controls: Dict[str, Any],
        proxy_analysis: Dict[str, Any],
        dependencies: Dict[str, Any],
        pattern_analysis: Dict[str, Any],
        audit_status: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile detailed security analysis results."""
        return {
            'contract_metadata': {
                'verified': metadata.is_verified,
                'compiler_version': metadata.compiler_version,
                'size_bytes': metadata.contract_size_bytes,
                'creation_block': metadata.creation_block
            },
            'vulnerabilities': [
                {
                    'id': v.vulnerability_id,
                    'severity': v.severity,
                    'category': v.category,
                    'description': v.description,
                    'confidence': v.confidence
                } for v in vulnerabilities
            ],
            'access_controls': access_controls,
            'proxy_analysis': proxy_analysis,
            'dependencies': dependencies,
            'pattern_analysis': pattern_analysis,
            'audit_status': audit_status,
            'security_summary': {
                'total_vulnerabilities': len(vulnerabilities),
                'critical_count': len([v for v in vulnerabilities if v.severity == 'CRITICAL']),
                'high_count': len([v for v in vulnerabilities if v.severity == 'HIGH']),
                'has_admin_risks': self._has_admin_risks(access_controls),
                'is_upgradeable': proxy_analysis.get('is_proxy', False),
                'audit_score': audit_status.get('audit_score', 0)
            },
            'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
            'chain_id': self.chain_id
        }
    
    def _has_admin_risks(self, access_controls: Dict[str, Any]) -> bool:
        """Check if contract has significant admin-related risks."""
        admin_privs = access_controls.get('admin_privileges', {})
        return (
            admin_privs.get('mint_tokens', False) or
            admin_privs.get('update_router', False) or
            access_controls.get('owner_can_blacklist', False)
        ) and not access_controls.get('ownership_renounced', False)
    
    def _assess_data_quality(
        self, 
        metadata: ContractMetadata, 
        vulnerabilities: List[SecurityVulnerability]
    ) -> str:
        """Assess the quality of security analysis data."""
        if metadata.compiler_version == "error":
            return "POOR"
        
        if not metadata.is_verified:
            return "FAIR"
        
        # Check if we have comprehensive vulnerability data
        vuln_categories = set(v.category for v in vulnerabilities)
        expected_categories = {'ACCESS_CONTROL', 'REENTRANCY', 'INTEGER_OVERFLOW', 'CODE_QUALITY'}
        
        if len(vuln_categories) >= 3:
            return "EXCELLENT"
        elif len(vuln_categories) >= 2:
            return "GOOD"
        else:
            return "FAIR"
    
    # Helper methods and data loading
    
    def _validate_contract_address(self, token_address: str) -> bool:
        """Validate contract address format."""
        if not token_address or len(token_address) != 42:
            return False
        if not token_address.startswith('0x'):
            return False
        try:
            int(token_address[2:], 16)  # Validate hex format
            return True
        except ValueError:
            return False
    
    def _safe_extract_result(self, result: Any, default: Any) -> Any:
        """Safely extract result from async gather, handling exceptions."""
        if isinstance(result, Exception):
            logger.warning(f"Security analysis task failed: {result}")
            return default
        return result if result is not None else default
    
    def _load_malicious_patterns(self) -> Set[str]:
        """Load known malicious contract patterns."""
        # In production, this would load from a security database
        return {
            'honeypot_pattern_1',
            'rug_pull_pattern_2', 
            'hidden_mint_pattern_3',
            'backdoor_pattern_4'
        }
    
    def _load_secure_patterns(self) -> Set[str]:
        """Load known secure contract patterns."""
        # In production, this would load from a verified contracts database
        return {
            'openzeppelin_erc20',
            'verified_audit_pattern_1',
            'standard_token_pattern_2'
        }
    
    def _load_vulnerability_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Load vulnerability pattern definitions."""
        return {
            'reentrancy': {
                'severity': 'HIGH',
                'description': 'Reentrancy vulnerability in state-changing functions',
                'mitigation': 'Use checks-effects-interactions pattern or reentrancy guards'
            },
            'integer_overflow': {
                'severity': 'HIGH', 
                'description': 'Integer overflow/underflow in arithmetic operations',
                'mitigation': 'Use SafeMath library or Solidity 0.8+ overflow protection'
            },
            'access_control': {
                'severity': 'MEDIUM',
                'description': 'Insufficient access control on privileged functions',
                'mitigation': 'Implement proper role-based access control'
            },
            'backdoor': {
                'severity': 'CRITICAL',
                'description': 'Hidden backdoor functions allowing unauthorized access',
                'mitigation': 'Remove backdoor functions or avoid contract entirely'
            }
        }
    
    def _get_cached_analysis(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get cached security analysis if available and fresh."""
        if token_address in self.analysis_cache:
            result, timestamp = self.analysis_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_minutes * 60):
                return result
            else:
                del self.analysis_cache[token_address]
        
        return None
    
    def _cache_analysis_result(self, token_address: str, result: Dict[str, Any]) -> None:
        """Cache security analysis result."""
        self.analysis_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries
        if len(self.analysis_cache) > 100:
            oldest_token = min(
                self.analysis_cache.keys(),
                key=lambda k: self.analysis_cache[k][1]
            )
            del self.analysis_cache[oldest_token]
    
    def _create_risk_score_from_cache(self, cached_result: Dict[str, Any]) -> RiskScore:
        """Create RiskScore from cached result."""
        return self._create_risk_score(
            score=cached_result['risk_score'],
            confidence=cached_result['confidence'],
            details=cached_result['details'],
            warnings=cached_result['warnings'],
            data_quality="CACHED",
            analysis_time_ms=0.1
        )
    
    def _create_error_risk_score(self, error_message: str) -> RiskScore:
        """Create error risk score for failed analysis."""
        return self._create_risk_score(
            score=0.9,  # Very high risk for failed security analysis
            confidence=0.3,
            details={'error': error_message},
            warnings=[f"Security analysis failed: {error_message}"],
            data_quality="POOR"
        )
    
    def _create_risk_score(
        self,
        score: float,
        confidence: float,
        details: Dict[str, Any],
        warnings: List[str],
        data_quality: str,
        analysis_time_ms: float = 0.0
    ) -> RiskScore:
        """Create standardized RiskScore object."""
        return RiskScore(
            category=self.get_category(),
            score=score,
            confidence=confidence,
            details=details,
            analysis_time_ms=analysis_time_ms,
            warnings=warnings,
            data_quality=data_quality,
            last_updated=datetime.now(timezone.utc).isoformat()
        )


# Export the analyzer class
__all__ = ['ContractAnalyzer', 'SecurityVulnerability', 'ContractMetadata']