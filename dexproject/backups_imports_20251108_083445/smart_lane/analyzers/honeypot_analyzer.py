"""
Honeypot Detection Analyzer

Critical security analyzer that detects potential honeypot scams,
exit scams, and malicious tokens that prevent selling or impose
excessive fees. This is one of the most important risk categories.

Path: engine/smart_lane/analyzers/honeypot_analyzer.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory

logger = logging.getLogger(__name__)


@dataclass
class HoneypotIndicator:
    """Individual honeypot risk indicator."""
    name: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    score: float  # 0-1 risk contribution
    description: str
    evidence: Dict[str, Any]
    confidence: float


@dataclass 
class SimulationResult:
    """Token transaction simulation result."""
    can_buy: bool
    can_sell: bool
    buy_gas_used: Optional[int]
    sell_gas_used: Optional[int]
    buy_tax_percent: Optional[float]
    sell_tax_percent: Optional[float]
    max_tx_percent: Optional[float]  # Maximum transaction size allowed
    simulation_error: Optional[str]
    execution_time_ms: float


class HoneypotAnalyzer(BaseAnalyzer):
    """
    Advanced honeypot detection analyzer.
    
    Uses multiple detection methods including:
    - Token contract analysis
    - Transaction simulation
    - Holder behavior patterns
    - Liquidity lock analysis
    - Historical scam pattern matching
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize honeypot analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration
        """
        super().__init__(chain_id, config)
        
        # Detection thresholds
        self.thresholds = {
            'critical_risk_score': 0.8,
            'high_risk_score': 0.6,
            'medium_risk_score': 0.4,
            'max_simulation_time_ms': 3000,
            'max_buy_tax_percent': 15.0,
            'max_sell_tax_percent': 15.0,
            'min_liquidity_usd': 1000,
            'max_holder_concentration': 0.5  # 50% of supply
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Known honeypot patterns
        self.known_patterns = self._load_known_patterns()
        
        # Simulation cache for performance
        self.simulation_cache: Dict[str, Tuple[SimulationResult, datetime]] = {}
        self.cache_ttl_minutes = 30
        
        logger.info(f"Honeypot analyzer initialized for chain {chain_id}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.HONEYPOT_DETECTION
    
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive honeypot detection analysis.
        
        Args:
            token_address: Token contract address
            context: Additional context for analysis
            
        Returns:
            Risk score with honeypot assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting honeypot analysis for {token_address[:10]}...")
            
            # Input validation
            if not self._validate_token_address(token_address):
                return self._create_risk_score(
                    score=1.0,
                    confidence=1.0,
                    details={'error': 'Invalid token address'},
                    warnings=['Invalid token address format'],
                    data_quality="POOR"
                )
            
            # Check if chain is supported
            if not self.is_chain_supported(self.chain_id):
                return self._create_risk_score(
                    score=0.5,
                    confidence=0.3,
                    details={'error': f'Chain {self.chain_id} not fully supported'},
                    warnings=[f'Limited analysis for chain {self.chain_id}'],
                    data_quality="FAIR"
                )
            
            # Collect all honeypot indicators in parallel
            indicators = await self._collect_honeypot_indicators(token_address, context)
            
            # Calculate overall risk score
            risk_score, confidence = self._calculate_honeypot_risk(indicators)
            
            # Generate warnings
            warnings = self._generate_warnings(indicators, risk_score)
            
            # Compile analysis details
            analysis_details = self._compile_analysis_details(indicators, context)
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Update performance stats
            self._update_performance_stats(analysis_time_ms, success=True)
            
            logger.debug(
                f"Honeypot analysis completed for {token_address[:10]}... "
                f"Risk: {risk_score:.3f}, Confidence: {confidence:.3f} ({analysis_time_ms:.1f}ms)"
            )
            
            return self._create_risk_score(
                score=risk_score,
                confidence=confidence,
                details=analysis_details,
                warnings=warnings,
                analysis_time_ms=analysis_time_ms,
                data_quality=self._assess_data_quality(indicators)
            )
            
        except Exception as e:
            analysis_time_ms = (time.time() - analysis_start) * 1000
            self._update_performance_stats(analysis_time_ms, success=False)
            
            logger.error(f"Honeypot analysis failed for {token_address}: {e}", exc_info=True)
            
            return self._create_risk_score(
                score=1.0,  # Maximum risk on analysis failure
                confidence=0.3,  # Low confidence
                details={'error': str(e), 'analysis_failed': True},
                warnings=[f'Analysis failed: {str(e)}'],
                analysis_time_ms=analysis_time_ms,
                data_quality="POOR"
            )
    
    async def _collect_honeypot_indicators(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> List[HoneypotIndicator]:
        """
        Collect all honeypot risk indicators in parallel.
        
        Args:
            token_address: Token contract address
            context: Analysis context
            
        Returns:
            List of honeypot risk indicators
        """
        indicators = []
        
        # Create analysis tasks that can run in parallel
        tasks = [
            self._analyze_contract_code(token_address),
            self._simulate_transactions(token_address, context),
            self._analyze_holder_patterns(token_address),
            self._check_liquidity_locks(token_address),
            self._analyze_trading_history(token_address),
            self._check_known_patterns(token_address),
            self._analyze_contract_ownership(token_address),
            self._check_external_databases(token_address)
        ]
        
        # Execute all tasks concurrently with timeout protection
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and collect indicators
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"Honeypot indicator collection failed (task {i}): {result}")
                    continue
                
                if isinstance(result, list):
                    indicators.extend(result)
                elif isinstance(result, HoneypotIndicator):
                    indicators.append(result)
            
        except Exception as e:
            logger.error(f"Error in parallel indicator collection: {e}")
            # Add error indicator
            indicators.append(
                HoneypotIndicator(
                    name="analysis_error",
                    severity="HIGH",
                    score=0.8,
                    description=f"Analysis error occurred: {str(e)}",
                    evidence={'error': str(e)},
                    confidence=0.7
                )
            )
        
        logger.debug(f"Collected {len(indicators)} honeypot indicators")
        return indicators
    
    async def _analyze_contract_code(self, token_address: str) -> List[HoneypotIndicator]:
        """
        Analyze token contract code for honeypot patterns.
        
        This would normally interact with blockchain APIs to analyze
        the contract bytecode and source code if available.
        """
        indicators = []
        
        # Simulated contract analysis - in production would use Web3
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Check for common honeypot patterns in contract code
        suspicious_patterns = [
            {'pattern': 'transfer_disabled', 'found': False, 'risk': 0.9},
            {'pattern': 'blacklist_function', 'found': False, 'risk': 0.8},
            {'pattern': 'variable_taxes', 'found': False, 'risk': 0.6},
            {'pattern': 'owner_only_sell', 'found': False, 'risk': 0.95},
            {'pattern': 'max_tx_limit', 'found': True, 'risk': 0.3},  # Common but not critical
            {'pattern': 'mint_function', 'found': False, 'risk': 0.4}
        ]
        
        for pattern in suspicious_patterns:
            if pattern['found']:
                severity = "CRITICAL" if pattern['risk'] > 0.8 else "HIGH" if pattern['risk'] > 0.6 else "MEDIUM"
                
                indicators.append(
                    HoneypotIndicator(
                        name=f"contract_{pattern['pattern']}",
                        severity=severity,
                        score=pattern['risk'],
                        description=f"Contract contains {pattern['pattern'].replace('_', ' ')}",
                        evidence={'pattern': pattern['pattern'], 'detected': True},
                        confidence=0.8
                    )
                )
        
        # Add general contract security indicator
        indicators.append(
            HoneypotIndicator(
                name="contract_analysis",
                severity="LOW",
                score=0.1,
                description="Contract code analysis completed with no major red flags",
                evidence={'patterns_checked': len(suspicious_patterns), 'issues_found': 1},
                confidence=0.7
            )
        )
        
        return indicators
    
    async def _simulate_transactions(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> List[HoneypotIndicator]:
        """
        Simulate buy/sell transactions to detect honeypot behavior.
        
        This is one of the most reliable honeypot detection methods.
        """
        indicators = []
        
        try:
            # Check cache first
            cached_result = self._get_cached_simulation(token_address)
            if cached_result:
                simulation = cached_result
            else:
                simulation = await self._perform_transaction_simulation(token_address, context)
                self._cache_simulation_result(token_address, simulation)
            
            # Analyze simulation results
            if simulation.simulation_error:
                indicators.append(
                    HoneypotIndicator(
                        name="simulation_error",
                        severity="MEDIUM",
                        score=0.5,
                        description=f"Transaction simulation failed: {simulation.simulation_error}",
                        evidence={'error': simulation.simulation_error},
                        confidence=0.6
                    )
                )
                return indicators
            
            # Check if selling is possible
            if simulation.can_buy and not simulation.can_sell:
                indicators.append(
                    HoneypotIndicator(
                        name="cannot_sell",
                        severity="CRITICAL",
                        score=0.95,
                        description="Token can be bought but cannot be sold - HONEYPOT DETECTED",
                        evidence={
                            'can_buy': simulation.can_buy,
                            'can_sell': simulation.can_sell,
                            'buy_gas': simulation.buy_gas_used,
                            'sell_gas': simulation.sell_gas_used
                        },
                        confidence=0.9
                    )
                )
            
            # Check for excessive taxes
            if simulation.buy_tax_percent and simulation.buy_tax_percent > self.thresholds['max_buy_tax_percent']:
                severity = "CRITICAL" if simulation.buy_tax_percent > 25 else "HIGH"
                indicators.append(
                    HoneypotIndicator(
                        name="excessive_buy_tax",
                        severity=severity,
                        score=min(0.9, simulation.buy_tax_percent / 100),
                        description=f"Excessive buy tax detected: {simulation.buy_tax_percent:.1f}%",
                        evidence={'buy_tax_percent': simulation.buy_tax_percent},
                        confidence=0.8
                    )
                )
            
            if simulation.sell_tax_percent and simulation.sell_tax_percent > self.thresholds['max_sell_tax_percent']:
                severity = "CRITICAL" if simulation.sell_tax_percent > 25 else "HIGH"
                indicators.append(
                    HoneypotIndicator(
                        name="excessive_sell_tax",
                        severity=severity,
                        score=min(0.9, simulation.sell_tax_percent / 100),
                        description=f"Excessive sell tax detected: {simulation.sell_tax_percent:.1f}%",
                        evidence={'sell_tax_percent': simulation.sell_tax_percent},
                        confidence=0.8
                    )
                )
            
            # Check for transaction size limits
            if simulation.max_tx_percent and simulation.max_tx_percent < 1.0:  # Less than 1% of supply
                indicators.append(
                    HoneypotIndicator(
                        name="restrictive_tx_limit",
                        severity="HIGH",
                        score=0.7,
                        description=f"Very restrictive transaction limit: {simulation.max_tx_percent:.2f}% of supply",
                        evidence={'max_tx_percent': simulation.max_tx_percent},
                        confidence=0.7
                    )
                )
            
            # If simulation passed all checks
            if simulation.can_buy and simulation.can_sell and len(indicators) == 0:
                indicators.append(
                    HoneypotIndicator(
                        name="simulation_passed",
                        severity="LOW",
                        score=0.05,
                        description="Transaction simulation passed - token appears tradeable",
                        evidence={
                            'can_buy': True,
                            'can_sell': True,
                            'buy_tax': simulation.buy_tax_percent,
                            'sell_tax': simulation.sell_tax_percent
                        },
                        confidence=0.8
                    )
                )
            
        except Exception as e:
            logger.error(f"Transaction simulation failed: {e}")
            indicators.append(
                HoneypotIndicator(
                    name="simulation_failed",
                    severity="MEDIUM",
                    score=0.6,
                    description=f"Could not simulate transactions: {str(e)}",
                    evidence={'error': str(e)},
                    confidence=0.5
                )
            )
        
        return indicators
    
    async def _analyze_holder_patterns(self, token_address: str) -> List[HoneypotIndicator]:
        """Analyze token holder distribution patterns for honeypot indicators."""
        indicators = []
        
        # Simulated holder analysis
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Mock holder data - in production would query blockchain
        holder_data = {
            'total_holders': 1250,
            'top_10_concentration': 0.65,  # 65% held by top 10
            'top_1_concentration': 0.45,   # 45% held by top holder
            'creator_balance_percent': 0.30,  # Creator holds 30%
            'locked_tokens_percent': 0.10,   # 10% locked
            'burned_tokens_percent': 0.05    # 5% burned
        }
        
        # High concentration risk
        if holder_data['top_1_concentration'] > 0.5:
            indicators.append(
                HoneypotIndicator(
                    name="extreme_holder_concentration",
                    severity="CRITICAL",
                    score=0.8,
                    description=f"Extreme holder concentration: {holder_data['top_1_concentration']:.1%} held by single address",
                    evidence=holder_data,
                    confidence=0.8
                )
            )
        elif holder_data['top_10_concentration'] > self.thresholds['max_holder_concentration']:
            indicators.append(
                HoneypotIndicator(
                    name="high_holder_concentration",
                    severity="HIGH",
                    score=0.6,
                    description=f"High holder concentration: {holder_data['top_10_concentration']:.1%} held by top 10",
                    evidence=holder_data,
                    confidence=0.7
                )
            )
        
        # Creator balance analysis
        if holder_data['creator_balance_percent'] > 0.2:
            severity = "HIGH" if holder_data['creator_balance_percent'] > 0.4 else "MEDIUM"
            indicators.append(
                HoneypotIndicator(
                    name="high_creator_balance",
                    severity=severity,
                    score=holder_data['creator_balance_percent'],
                    description=f"Creator holds large portion: {holder_data['creator_balance_percent']:.1%}",
                    evidence=holder_data,
                    confidence=0.7
                )
            )
        
        # Low holder count for established tokens
        if holder_data['total_holders'] < 100:
            indicators.append(
                HoneypotIndicator(
                    name="low_holder_count",
                    severity="MEDIUM",
                    score=0.4,
                    description=f"Low holder count: {holder_data['total_holders']} holders",
                    evidence=holder_data,
                    confidence=0.6
                )
            )
        
        return indicators
    
    async def _check_liquidity_locks(self, token_address: str) -> List[HoneypotIndicator]:
        """Check liquidity lock status and legitimacy."""
        indicators = []
        
        # Simulated liquidity analysis
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Mock liquidity data
        liquidity_data = {
            'total_liquidity_usd': 15000,
            'locked_liquidity_percent': 0.80,
            'lock_duration_days': 365,
            'lock_service': 'DxSale',
            'can_remove_liquidity': False,
            'liquidity_pairs': ['WETH', 'USDC'],
            'oldest_pair_age_days': 45
        }
        
        # Check minimum liquidity
        if liquidity_data['total_liquidity_usd'] < self.thresholds['min_liquidity_usd']:
            indicators.append(
                HoneypotIndicator(
                    name="low_liquidity",
                    severity="HIGH",
                    score=0.7,
                    description=f"Very low liquidity: ${liquidity_data['total_liquidity_usd']:,}",
                    evidence=liquidity_data,
                    confidence=0.8
                )
            )
        
        # Check liquidity lock status
        if liquidity_data['locked_liquidity_percent'] < 0.5:
            indicators.append(
                HoneypotIndicator(
                    name="unlocked_liquidity",
                    severity="CRITICAL",
                    score=0.9,
                    description=f"Most liquidity unlocked: {liquidity_data['locked_liquidity_percent']:.1%} locked",
                    evidence=liquidity_data,
                    confidence=0.8
                )
            )
        elif liquidity_data['locked_liquidity_percent'] > 0.8:
            indicators.append(
                HoneypotIndicator(
                    name="good_liquidity_lock",
                    severity="LOW",
                    score=0.1,
                    description=f"Good liquidity lock: {liquidity_data['locked_liquidity_percent']:.1%} locked for {liquidity_data['lock_duration_days']} days",
                    evidence=liquidity_data,
                    confidence=0.7
                )
            )
        
        # Check if owner can remove liquidity
        if liquidity_data['can_remove_liquidity']:
            indicators.append(
                HoneypotIndicator(
                    name="removable_liquidity",
                    severity="HIGH",
                    score=0.8,
                    description="Owner can remove liquidity - rug pull risk",
                    evidence=liquidity_data,
                    confidence=0.7
                )
            )
        
        return indicators
    
    async def _analyze_trading_history(self, token_address: str) -> List[HoneypotIndicator]:
        """Analyze historical trading patterns for honeypot indicators."""
        indicators = []
        
        # Simulated trading analysis
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Mock trading data
        trading_data = {
            'total_transactions': 2500,
            'buy_transactions': 2100,
            'sell_transactions': 400,  # Much fewer sells
            'failed_sells': 50,
            'avg_buy_size_usd': 150,
            'avg_sell_size_usd': 80,
            'unique_buyers': 890,
            'unique_sellers': 120,  # Much fewer unique sellers
            'largest_sell_usd': 2000,
            'sells_last_24h': 5,
            'buys_last_24h': 85
        }
        
        # Check buy/sell ratio
        if trading_data['sell_transactions'] > 0:
            buy_sell_ratio = trading_data['buy_transactions'] / trading_data['sell_transactions']
            if buy_sell_ratio > 10:  # 10x more buys than sells
                indicators.append(
                    HoneypotIndicator(
                        name="extreme_buy_sell_ratio",
                        severity="CRITICAL",
                        score=0.85,
                        description=f"Extreme buy/sell ratio: {buy_sell_ratio:.1f}:1 - possible honeypot",
                        evidence=trading_data,
                        confidence=0.8
                    )
                )
            elif buy_sell_ratio > 5:  # 5x more buys than sells
                indicators.append(
                    HoneypotIndicator(
                        name="high_buy_sell_ratio",
                        severity="HIGH",
                        score=0.6,
                        description=f"High buy/sell ratio: {buy_sell_ratio:.1f}:1",
                        evidence=trading_data,
                        confidence=0.7
                    )
                )
        
        # Check failed sell attempts
        if trading_data['failed_sells'] > 0:
            fail_rate = trading_data['failed_sells'] / (trading_data['sell_transactions'] + trading_data['failed_sells'])
            if fail_rate > 0.3:  # >30% of sell attempts fail
                indicators.append(
                    HoneypotIndicator(
                        name="high_sell_failure_rate",
                        severity="CRITICAL",
                        score=0.9,
                        description=f"High sell failure rate: {fail_rate:.1%} of sells fail",
                        evidence=trading_data,
                        confidence=0.8
                    )
                )
        
        # Check unique buyer/seller ratio
        if trading_data['unique_sellers'] > 0:
            buyer_seller_ratio = trading_data['unique_buyers'] / trading_data['unique_sellers']
            if buyer_seller_ratio > 15:  # 15x more unique buyers than sellers
                indicators.append(
                    HoneypotIndicator(
                        name="few_unique_sellers",
                        severity="HIGH",
                        score=0.7,
                        description=f"Very few unique sellers: {buyer_seller_ratio:.1f}:1 ratio",
                        evidence=trading_data,
                        confidence=0.7
                    )
                )
        
        # Check recent activity
        if trading_data['sells_last_24h'] == 0 and trading_data['buys_last_24h'] > 10:
            indicators.append(
                HoneypotIndicator(
                    name="no_recent_sells",
                    severity="HIGH",
                    score=0.8,
                    description="No successful sells in last 24h despite buying activity",
                    evidence=trading_data,
                    confidence=0.7
                )
            )
        
        return indicators
    
    async def _check_known_patterns(self, token_address: str) -> List[HoneypotIndicator]:
        """Check against known honeypot patterns and blacklists."""
        indicators = []
        
        # Simulated pattern matching
        await asyncio.sleep(0.05)  # Quick pattern check
        
        # Check against known patterns (mock data)
        pattern_matches = []
        
        # In production, this would check:
        # - Known honeypot contract signatures
        # - Blacklisted addresses
        # - Similar contract patterns
        # - Community reports
        
        # Mock some pattern checks
        for pattern in self.known_patterns:
            if pattern['risk_level'] == 'CRITICAL':
                # Mock: randomly not match critical patterns for this example
                continue
            
            # Add pattern check results
            pattern_matches.append({
                'pattern_name': pattern['name'],
                'match_confidence': pattern['confidence'],
                'risk_level': pattern['risk_level'],
                'description': pattern['description']
            })
        
        if pattern_matches:
            max_risk = max(p['match_confidence'] for p in pattern_matches)
            indicators.append(
                HoneypotIndicator(
                    name="pattern_matches",
                    severity="MEDIUM",
                    score=max_risk,
                    description=f"Matches {len(pattern_matches)} known risk patterns",
                    evidence={'matches': pattern_matches},
                    confidence=0.6
                )
            )
        else:
            indicators.append(
                HoneypotIndicator(
                    name="no_known_patterns",
                    severity="LOW",
                    score=0.05,
                    description="No matches against known honeypot patterns",
                    evidence={'patterns_checked': len(self.known_patterns)},
                    confidence=0.7
                )
            )
        
        return indicators
    
    async def _analyze_contract_ownership(self, token_address: str) -> List[HoneypotIndicator]:
        """Analyze contract ownership and admin functions."""
        indicators = []
        
        # Simulated ownership analysis
        await asyncio.sleep(0.05)
        
        # Mock ownership data
        ownership_data = {
            'has_owner': True,
            'owner_renounced': False,
            'admin_functions': ['pause', 'blacklist', 'change_tax'],
            'proxy_contract': False,
            'upgradeable': False,
            'timelock': False,
            'multisig_owner': False
        }
        
        # Check if ownership is renounced
        if ownership_data['has_owner'] and not ownership_data['owner_renounced']:
            admin_risk = 0.3 + (len(ownership_data['admin_functions']) * 0.1)
            severity = "HIGH" if admin_risk > 0.6 else "MEDIUM"
            
            indicators.append(
                HoneypotIndicator(
                    name="active_ownership",
                    severity=severity,
                    score=min(0.8, admin_risk),
                    description=f"Contract has active owner with {len(ownership_data['admin_functions'])} admin functions",
                    evidence=ownership_data,
                    confidence=0.7
                )
            )
        
        # Check for dangerous admin functions
        dangerous_functions = [func for func in ownership_data['admin_functions'] 
                             if func in ['blacklist', 'pause', 'disable_trading', 'change_max_tx']]
        
        if dangerous_functions:
            indicators.append(
                HoneypotIndicator(
                    name="dangerous_admin_functions",
                    severity="HIGH",
                    score=0.7,
                    description=f"Contract has dangerous admin functions: {', '.join(dangerous_functions)}",
                    evidence={'dangerous_functions': dangerous_functions},
                    confidence=0.8
                )
            )
        
        # Check if contract is upgradeable
        if ownership_data['upgradeable']:
            indicators.append(
                HoneypotIndicator(
                    name="upgradeable_contract",
                    severity="MEDIUM",
                    score=0.5,
                    description="Contract is upgradeable - owner can change behavior",
                    evidence=ownership_data,
                    confidence=0.7
                )
            )
        
        return indicators
    
    async def _check_external_databases(self, token_address: str) -> List[HoneypotIndicator]:
        """Check external honeypot databases and services."""
        indicators = []
        
        # Simulated external API checks
        await asyncio.sleep(0.1)
        
        # Mock external database results
        external_results = {
            'honeypot_is': {'is_honeypot': False, 'confidence': 0.8},
            'tokensniffer': {'risk_score': 0.2, 'warnings': []},
            'community_reports': {'scam_reports': 0, 'warning_reports': 1},
            'similar_contracts': {'honeypot_matches': 0, 'similarity_score': 0.1}
        }
        
        # Process external results
        for source, data in external_results.items():
            if source == 'honeypot_is' and data['is_honeypot']:
                indicators.append(
                    HoneypotIndicator(
                        name="external_honeypot_detection",
                        severity="CRITICAL",
                        score=0.9,
                        description=f"External service {source} flagged as honeypot",
                        evidence=data,
                        confidence=data.get('confidence', 0.7)
                    )
                )
            elif source == 'community_reports' and data['scam_reports'] > 0:
                indicators.append(
                    HoneypotIndicator(
                        name="community_scam_reports",
                        severity="HIGH",
                        score=0.8,
                        description=f"{data['scam_reports']} community scam reports",
                        evidence=data,
                        confidence=0.6
                    )
                )
        
        # If no external flags
        if not indicators:
            indicators.append(
                HoneypotIndicator(
                    name="external_checks_passed",
                    severity="LOW",
                    score=0.05,
                    description="Passed external honeypot database checks",
                    evidence=external_results,
                    confidence=0.6
                )
            )
        
        return indicators
    
    async def _perform_transaction_simulation(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> SimulationResult:
        """
        Perform actual transaction simulation.
        
        In production, this would use a blockchain simulation service
        or local node to simulate buy/sell transactions.
        """
        simulation_start = time.time()
        
        # Simulate API call delay
        await asyncio.sleep(0.2)
        
        # Mock simulation results - in production would use real blockchain simulation
        simulation = SimulationResult(
            can_buy=True,
            can_sell=True,  # This would be False for honeypots
            buy_gas_used=150000,
            sell_gas_used=160000,
            buy_tax_percent=5.0,   # 5% buy tax
            sell_tax_percent=8.0,  # 8% sell tax
            max_tx_percent=2.0,    # 2% of supply max
            simulation_error=None,
            execution_time_ms=(time.time() - simulation_start) * 1000
        )
        
        return simulation
    
    def _calculate_honeypot_risk(
        self,
        indicators: List[HoneypotIndicator]
    ) -> Tuple[float, float]:
        """
        Calculate overall honeypot risk score and confidence.
        
        Args:
            indicators: List of honeypot risk indicators
            
        Returns:
            Tuple of (risk_score, confidence)
        """
        if not indicators:
            return 0.5, 0.3  # Medium risk, low confidence if no data
        
        # Separate critical and non-critical indicators
        critical_indicators = [i for i in indicators if i.severity == "CRITICAL"]
        high_indicators = [i for i in indicators if i.severity == "HIGH"]
        medium_indicators = [i for i in indicators if i.severity == "MEDIUM"]
        low_indicators = [i for i in indicators if i.severity == "LOW"]
        
        # If any critical indicators, risk is very high
        if critical_indicators:
            critical_score = max(i.score for i in critical_indicators)
            critical_confidence = max(i.confidence for i in critical_indicators)
            return min(1.0, critical_score + 0.1), critical_confidence
        
        # Weight-based scoring for other indicators
        total_weighted_score = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        
        # Assign weights by severity
        severity_weights = {
            "HIGH": 0.8,
            "MEDIUM": 0.5,
            "LOW": 0.2
        }
        
        for indicator in indicators:
            weight = severity_weights.get(indicator.severity, 0.3)
            confidence_adjusted_score = indicator.score * indicator.confidence
            
            total_weighted_score += confidence_adjusted_score * weight
            total_weight += weight * indicator.confidence
            total_confidence += indicator.confidence
        
        # Calculate final scores
        if total_weight > 0:
            final_risk_score = total_weighted_score / total_weight
        else:
            final_risk_score = 0.5
        
        if len(indicators) > 0:
            final_confidence = total_confidence / len(indicators)
        else:
            final_confidence = 0.3
        
        return min(1.0, final_risk_score), min(1.0, final_confidence)
    
    def _generate_warnings(
        self,
        indicators: List[HoneypotIndicator],
        risk_score: float
    ) -> List[str]:
        """Generate user-friendly warnings based on indicators."""
        warnings = []
        
        # Critical warnings
        critical_indicators = [i for i in indicators if i.severity == "CRITICAL"]
        for indicator in critical_indicators:
            warnings.append(f"CRITICAL: {indicator.description}")
        
        # High-risk warnings
        high_indicators = [i for i in indicators if i.severity == "HIGH"]
        for indicator in high_indicators[:3]:  # Limit to top 3
            warnings.append(f"HIGH RISK: {indicator.description}")
        
        # Overall risk warning
        if risk_score > self.thresholds['critical_risk_score']:
            warnings.append("HONEYPOT SUSPECTED - DO NOT TRADE")
        elif risk_score > self.thresholds['high_risk_score']:
            warnings.append("High honeypot risk detected - proceed with extreme caution")
        elif risk_score > self.thresholds['medium_risk_score']:
            warnings.append("Moderate honeypot risk - use small test amounts first")
        
        return warnings
    
    def _compile_analysis_details(
        self,
        indicators: List[HoneypotIndicator],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile detailed analysis results."""
        return {
            'total_indicators': len(indicators),
            'indicators_by_severity': {
                'CRITICAL': len([i for i in indicators if i.severity == "CRITICAL"]),
                'HIGH': len([i for i in indicators if i.severity == "HIGH"]),
                'MEDIUM': len([i for i in indicators if i.severity == "MEDIUM"]),
                'LOW': len([i for i in indicators if i.severity == "LOW"])
            },
            'key_findings': [
                indicator.description for indicator in indicators
                if indicator.severity in ["CRITICAL", "HIGH"]
            ][:5],
            'analysis_methods': [
                'contract_code_analysis',
                'transaction_simulation',
                'holder_pattern_analysis',
                'liquidity_analysis',
                'trading_history_analysis',
                'known_pattern_matching',
                'ownership_analysis',
                'external_database_checks'
            ],
            'chain_id': self.chain_id,
            'thresholds_used': self.thresholds
        }
    
    def _assess_data_quality(self, indicators: List[HoneypotIndicator]) -> str:
        """Assess overall data quality based on indicators."""
        if not indicators:
            return "POOR"
        
        # Count successful vs failed analyses
        failed_indicators = [i for i in indicators if 'error' in i.evidence]
        error_rate = len(failed_indicators) / len(indicators)
        
        if error_rate > 0.5:
            return "POOR"
        elif error_rate > 0.2:
            return "FAIR"
        elif error_rate > 0.1:
            return "GOOD"
        else:
            return "EXCELLENT"
    
    def _get_cached_simulation(self, token_address: str) -> Optional[SimulationResult]:
        """Get cached simulation result if available and fresh."""
        if token_address in self.simulation_cache:
            result, timestamp = self.simulation_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_minutes * 60):
                self.performance_stats['cache_hits'] += 1
                return result
            else:
                # Remove expired cache entry
                del self.simulation_cache[token_address]
        
        self.performance_stats['cache_misses'] += 1
        return None
    
    def _cache_simulation_result(self, token_address: str, result: SimulationResult) -> None:
        """Cache simulation result for future use."""
        self.simulation_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries if cache gets too large
        if len(self.simulation_cache) > 100:
            # Remove oldest entries
            sorted_entries = sorted(
                self.simulation_cache.items(),
                key=lambda x: x[1][1]
            )
            for token, _ in sorted_entries[:20]:  # Remove oldest 20
                del self.simulation_cache[token]
    
    def _load_known_patterns(self) -> List[Dict[str, Any]]:
        """Load known honeypot patterns for pattern matching."""
        # In production, this would load from a database or external service
        return [
            {
                'name': 'transfer_disabled_pattern',
                'description': 'Contract disables transfers after initial period',
                'risk_level': 'CRITICAL',
                'confidence': 0.9,
                'pattern_hash': 'a1b2c3d4'
            },
            {
                'name': 'variable_tax_pattern',
                'description': 'Contract uses variable tax rates',
                'risk_level': 'HIGH',
                'confidence': 0.7,
                'pattern_hash': 'e5f6g7h8'
            },
            {
                'name': 'owner_only_sell_pattern',
                'description': 'Only contract owner can sell tokens',
                'risk_level': 'CRITICAL',
                'confidence': 0.95,
                'pattern_hash': 'i9j0k1l2'
            }
        ]


# Export the analyzer class
__all__ = ['HoneypotAnalyzer', 'HoneypotIndicator', 'SimulationResult']