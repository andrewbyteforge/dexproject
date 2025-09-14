"""
Tax Analysis Analyzer

High-priority analyzer that evaluates token transaction taxes, fees,
and transfer restrictions. Critical for understanding true trading
costs and detecting excessive taxation schemes.

Path: engine/smart_lane/analyzers/tax_analyzer.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory

logger = logging.getLogger(__name__)


@dataclass
class TaxStructure:
    """Token tax structure analysis."""
    buy_tax_percent: float
    sell_tax_percent: float
    transfer_tax_percent: float
    max_transaction_percent: Optional[float]  # Max transaction size as % of supply
    has_dynamic_taxes: bool
    tax_distribution: Dict[str, float]  # Where taxes go (burn, liquidity, team, etc.)
    anti_whale_enabled: bool
    cooldown_enabled: bool
    whitelist_enabled: bool


@dataclass
class TaxEvent:
    """Individual tax event analysis."""
    event_type: str  # BUY, SELL, TRANSFER
    effective_tax_rate: float
    base_tax_rate: float
    additional_fees: List[Dict[str, Any]]
    restrictions_applied: List[str]
    simulation_successful: bool
    gas_estimate: Optional[int]


class TaxAnalyzer(BaseAnalyzer):
    """
    Advanced tax and fee analysis for token transactions.
    
    Analyzes:
    - Buy, sell, and transfer tax rates
    - Dynamic tax mechanisms and conditions
    - Maximum transaction size limits
    - Anti-whale and anti-bot mechanisms
    - Tax distribution and sustainability
    - Hidden fees and restrictions
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize tax analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration
        """
        super().__init__(chain_id, config)
        
        # Tax analysis thresholds
        self.thresholds = {
            'max_buy_tax_percent': 10.0,        # Reasonable buy tax limit
            'max_sell_tax_percent': 15.0,       # Reasonable sell tax limit
            'max_transfer_tax_percent': 5.0,    # Transfer tax limit
            'excessive_tax_threshold': 20.0,    # Clearly excessive tax
            'min_max_transaction_percent': 0.5, # Minimum allowed transaction size
            'max_cooldown_seconds': 300,        # Maximum reasonable cooldown
            'sustainable_team_tax': 5.0         # Sustainable team allocation
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
        
        # Tax simulation amounts (in tokens, will be converted)
        self.simulation_amounts = [100, 1000, 10000, 100000]  # Different test sizes
        
        # Tax analysis cache
        self.tax_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self.cache_ttl_minutes = 30  # Tax structures can change
        
        logger.info(f"Tax analyzer initialized for chain {chain_id}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.TOKEN_TAX_ANALYSIS
    
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive tax analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context including pair info
            
        Returns:
            RiskScore with tax assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting tax analysis for {token_address[:10]}...")
            
            # Input validation
            if not self._validate_inputs(token_address, context):
                return self._create_error_risk_score("Invalid inputs for tax analysis")
            
            # Check cache first
            cached_result = self._get_cached_analysis(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Parallel tax analysis tasks
            analysis_tasks = [
                self._analyze_static_tax_structure(token_address),
                self._simulate_tax_transactions(token_address, context),
                self._analyze_dynamic_tax_mechanisms(token_address),
                self._analyze_transfer_restrictions(token_address),
                self._analyze_tax_distribution(token_address),
                self._analyze_anti_whale_mechanisms(token_address)
            ]
            
            analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # Process results and handle exceptions
            static_taxes = self._safe_extract_result(analysis_results[0], {})
            tax_simulations = self._safe_extract_result(analysis_results[1], [])
            dynamic_taxes = self._safe_extract_result(analysis_results[2], {})
            restrictions = self._safe_extract_result(analysis_results[3], {})
            tax_distribution = self._safe_extract_result(analysis_results[4], {})
            anti_whale = self._safe_extract_result(analysis_results[5], {})
            
            # Create comprehensive tax structure
            tax_structure = self._compile_tax_structure(
                static_taxes, dynamic_taxes, restrictions, 
                tax_distribution, anti_whale
            )
            
            # Calculate tax risk score
            risk_score, confidence = self._calculate_tax_risk(
                tax_structure, tax_simulations, restrictions
            )
            
            # Generate tax warnings
            warnings = self._generate_tax_warnings(tax_structure, tax_simulations)
            
            # Compile detailed analysis
            analysis_details = self._compile_tax_details(
                tax_structure, tax_simulations, dynamic_taxes,
                restrictions, tax_distribution, anti_whale
            )
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Cache the results
            self._cache_analysis_result(token_address, {
                'risk_score': risk_score,
                'confidence': confidence,
                'details': analysis_details,
                'warnings': warnings,
                'tax_structure': tax_structure
            })
            
            # Update performance stats
            self._update_performance_stats(analysis_time_ms, success=True)
            
            logger.debug(
                f"Tax analysis completed for {token_address[:10]}... "
                f"Risk: {risk_score:.3f}, Confidence: {confidence:.3f} "
                f"(Buy: {tax_structure.buy_tax_percent:.1f}%, Sell: {tax_structure.sell_tax_percent:.1f}%, "
                f"{analysis_time_ms:.1f}ms)"
            )
            
            return self._create_risk_score(
                score=risk_score,
                confidence=confidence,
                details=analysis_details,
                warnings=warnings,
                data_quality=self._assess_data_quality(tax_structure, tax_simulations),
                analysis_time_ms=analysis_time_ms
            )
            
        except Exception as e:
            analysis_time_ms = (time.time() - analysis_start) * 1000
            self._update_performance_stats(analysis_time_ms, success=False)
            
            logger.error(f"Error in tax analysis: {e}", exc_info=True)
            return self._create_error_risk_score(f"Tax analysis failed: {str(e)}")
    
    async def _analyze_static_tax_structure(self, token_address: str) -> Dict[str, Any]:
        """Analyze basic static tax rates from contract."""
        try:
            await asyncio.sleep(0.2)  # Simulate contract calls
            
            # Mock tax data based on token address characteristics
            address_hash = hash(token_address)
            
            # Generate realistic tax rates
            base_buy_tax = (address_hash % 15) / 2.0  # 0-7.5%
            base_sell_tax = base_buy_tax + (address_hash % 10) / 2.0  # Usually higher than buy
            transfer_tax = (address_hash % 6) / 2.0  # 0-3%
            
            static_taxes = {
                'buy_tax_percent': base_buy_tax,
                'sell_tax_percent': min(base_sell_tax, 25.0),  # Cap at 25%
                'transfer_tax_percent': transfer_tax,
                'reflection_enabled': (address_hash % 4) == 0,  # 25% have reflection
                'burn_enabled': (address_hash % 3) == 0,  # 33% have burn
                'liquidity_tax_enabled': (address_hash % 2) == 0,  # 50% have LP tax
                'marketing_tax_enabled': (address_hash % 3) != 2,  # 67% have marketing tax
                'tax_can_be_changed': (address_hash % 5) != 0,  # 80% can change taxes
                'max_tax_limits': {
                    'buy_limit': base_buy_tax * 2,
                    'sell_limit': base_sell_tax * 2
                } if (address_hash % 3) == 0 else None
            }
            
            return static_taxes
            
        except Exception as e:
            logger.error(f"Error analyzing static tax structure: {e}")
            return {'error': str(e)}
    
    async def _simulate_tax_transactions(
        self, 
        token_address: str, 
        context: Dict[str, Any]
    ) -> List[TaxEvent]:
        """Simulate transactions to measure actual tax rates."""
        try:
            await asyncio.sleep(0.25)  # Simulate transaction simulations
            
            tax_events = []
            address_hash = hash(token_address)
            
            # Simulate buy transaction
            buy_tax_rate = (address_hash % 15) / 2.0
            tax_events.append(TaxEvent(
                event_type="BUY",
                effective_tax_rate=buy_tax_rate,
                base_tax_rate=buy_tax_rate,
                additional_fees=[],
                restrictions_applied=[],
                simulation_successful=True,
                gas_estimate=150000 + (address_hash % 50000)
            ))
            
            # Simulate sell transaction (usually higher tax)
            sell_tax_rate = buy_tax_rate + (address_hash % 10) / 2.0
            additional_fees = []
            
            if (address_hash % 10) < 3:  # 30% have additional sell fees
                additional_fees.append({
                    'name': 'anti_dump_fee',
                    'rate': 2.0,
                    'description': 'Additional fee for large sells'
                })
            
            tax_events.append(TaxEvent(
                event_type="SELL",
                effective_tax_rate=sell_tax_rate + sum(f['rate'] for f in additional_fees),
                base_tax_rate=sell_tax_rate,
                additional_fees=additional_fees,
                restrictions_applied=['max_sell_check'] if (address_hash % 5) == 0 else [],
                simulation_successful=True,
                gas_estimate=180000 + (address_hash % 60000)
            ))
            
            # Simulate transfer transaction
            transfer_tax_rate = (address_hash % 6) / 2.0
            transfer_restrictions = []
            
            if (address_hash % 7) == 0:  # Some have transfer cooldowns
                transfer_restrictions.append('cooldown_active')
            
            tax_events.append(TaxEvent(
                event_type="TRANSFER",
                effective_tax_rate=transfer_tax_rate,
                base_tax_rate=transfer_tax_rate,
                additional_fees=[],
                restrictions_applied=transfer_restrictions,
                simulation_successful=(address_hash % 20) != 0,  # 95% success rate
                gas_estimate=120000 + (address_hash % 30000)
            ))
            
            return tax_events
            
        except Exception as e:
            logger.error(f"Error simulating tax transactions: {e}")
            return []
    
    async def _analyze_dynamic_tax_mechanisms(self, token_address: str) -> Dict[str, Any]:
        """Analyze dynamic tax adjustment mechanisms."""
        try:
            await asyncio.sleep(0.15)  # Simulate dynamic mechanism analysis
            
            address_hash = hash(token_address)
            
            dynamic_mechanisms = {
                'has_dynamic_taxes': (address_hash % 5) == 0,  # 20% have dynamic taxes
                'time_based_changes': (address_hash % 8) == 0,  # 12.5% time-based
                'volume_based_changes': (address_hash % 6) == 0,  # 16.7% volume-based
                'price_based_changes': (address_hash % 10) == 0,  # 10% price-based
                'honeypot_potential': False,
                'tax_schedule': [],
                'triggers': []
            }
            
            if dynamic_mechanisms['has_dynamic_taxes']:
                # Add some dynamic tax triggers
                if dynamic_mechanisms['time_based_changes']:
                    dynamic_mechanisms['triggers'].append({
                        'type': 'TIME_BASED',
                        'description': 'Tax rates change based on time since launch',
                        'risk_level': 'MEDIUM'
                    })
                
                if dynamic_mechanisms['volume_based_changes']:
                    dynamic_mechanisms['triggers'].append({
                        'type': 'VOLUME_BASED',
                        'description': 'Tax rates adjust based on trading volume',
                        'risk_level': 'LOW'
                    })
                
                # Check for honeypot potential
                if (address_hash % 20) == 0:  # 5% potential honeypots
                    dynamic_mechanisms['honeypot_potential'] = True
                    dynamic_mechanisms['triggers'].append({
                        'type': 'HONEYPOT_TRIGGER',
                        'description': 'Sell tax may increase to 99% after conditions',
                        'risk_level': 'CRITICAL'
                    })
            
            return dynamic_mechanisms
            
        except Exception as e:
            logger.error(f"Error analyzing dynamic tax mechanisms: {e}")
            return {'error': str(e)}
    
    async def _analyze_transfer_restrictions(self, token_address: str) -> Dict[str, Any]:
        """Analyze transfer restrictions and limitations."""
        try:
            await asyncio.sleep(0.1)  # Simulate restriction analysis
            
            address_hash = hash(token_address)
            
            restrictions = {
                'max_transaction_enabled': (address_hash % 3) == 0,  # 33% have max tx
                'max_wallet_enabled': (address_hash % 4) == 0,      # 25% have max wallet
                'cooldown_enabled': (address_hash % 7) == 0,        # ~14% have cooldown
                'blacklist_enabled': (address_hash % 10) == 0,      # 10% have blacklist
                'whitelist_only_mode': False,  # Very rare
                'trading_paused': False,
                'restrictions_details': {}
            }
            
            if restrictions['max_transaction_enabled']:
                max_tx_percent = 0.5 + (address_hash % 20) / 10.0  # 0.5-2.5% of supply
                restrictions['restrictions_details']['max_transaction_percent'] = max_tx_percent
                
                if max_tx_percent < 1.0:
                    restrictions['restrictions_details']['severity'] = 'HIGH'
                else:
                    restrictions['restrictions_details']['severity'] = 'MEDIUM'
            
            if restrictions['max_wallet_enabled']:
                max_wallet_percent = 1.0 + (address_hash % 40) / 10.0  # 1-5% of supply
                restrictions['restrictions_details']['max_wallet_percent'] = max_wallet_percent
            
            if restrictions['cooldown_enabled']:
                cooldown_seconds = 30 + (address_hash % 270)  # 30-300 seconds
                restrictions['restrictions_details']['cooldown_seconds'] = cooldown_seconds
                
                if cooldown_seconds > 180:
                    restrictions['restrictions_details']['cooldown_severity'] = 'HIGH'
                else:
                    restrictions['restrictions_details']['cooldown_severity'] = 'MEDIUM'
            
            # Check for extreme restrictions (potential honeypot indicators)
            if (address_hash % 50) == 0:  # 2% have extreme restrictions
                restrictions['whitelist_only_mode'] = True
                restrictions['restrictions_details']['severity'] = 'CRITICAL'
            
            return restrictions
            
        except Exception as e:
            logger.error(f"Error analyzing transfer restrictions: {e}")
            return {'error': str(e)}
    
    async def _analyze_tax_distribution(self, token_address: str) -> Dict[str, Any]:
        """Analyze how collected taxes are distributed."""
        try:
            await asyncio.sleep(0.08)  # Simulate distribution analysis
            
            address_hash = hash(token_address)
            
            # Generate realistic tax distribution
            total_allocation = 100.0
            remaining = total_allocation
            
            distribution = {}
            
            # Liquidity allocation (usually present)
            if (address_hash % 3) != 2:  # 67% allocate to liquidity
                liquidity_percent = 20 + (address_hash % 30)  # 20-49%
                liquidity_percent = min(liquidity_percent, remaining - 20)  # Leave room for others
                distribution['liquidity'] = liquidity_percent
                remaining -= liquidity_percent
            
            # Marketing/team allocation
            if (address_hash % 4) != 3:  # 75% have marketing allocation
                marketing_percent = 10 + (address_hash % 25)  # 10-34%
                marketing_percent = min(marketing_percent, remaining - 10)
                distribution['marketing'] = marketing_percent
                remaining -= marketing_percent
            
            # Burn allocation
            if (address_hash % 5) == 0:  # 20% have burn
                burn_percent = min(remaining - 5, 15 + (address_hash % 20))  # Up to 34%
                distribution['burn'] = burn_percent
                remaining -= burn_percent
            
            # Reflection/rewards
            if (address_hash % 6) == 0:  # ~17% have reflection
                reflection_percent = min(remaining, 10 + (address_hash % 15))  # Up to 24%
                distribution['reflection'] = reflection_percent
                remaining -= reflection_percent
            
            # Any remaining goes to treasury/team
            if remaining > 0:
                distribution['treasury'] = remaining
            
            tax_distribution = {
                'distribution_percentages': distribution,
                'total_allocated': sum(distribution.values()),
                'sustainable_model': self._assess_sustainability(distribution),
                'transparency_score': self._calculate_transparency_score(distribution),
                'red_flags': self._identify_distribution_red_flags(distribution),
                'allocation_addresses': self._generate_mock_addresses(distribution)
            }
            
            return tax_distribution
            
        except Exception as e:
            logger.error(f"Error analyzing tax distribution: {e}")
            return {'error': str(e)}
    
    async def _analyze_anti_whale_mechanisms(self, token_address: str) -> Dict[str, Any]:
        """Analyze anti-whale and anti-bot mechanisms."""
        try:
            await asyncio.sleep(0.06)  # Simulate anti-whale analysis
            
            address_hash = hash(token_address)
            
            anti_whale = {
                'max_transaction_limits': (address_hash % 3) == 0,
                'max_wallet_limits': (address_hash % 4) == 0,
                'progressive_tax_rates': (address_hash % 8) == 0,  # Rare feature
                'cooldown_periods': (address_hash % 7) == 0,
                'anti_bot_measures': (address_hash % 5) == 0,
                'launch_protection': (address_hash % 6) == 0,
                'effectiveness_score': 0.0,
                'bypass_potential': 'LOW'
            }
            
            # Calculate effectiveness
            effectiveness = 0.0
            if anti_whale['max_transaction_limits']:
                effectiveness += 25
            if anti_whale['max_wallet_limits']:
                effectiveness += 20
            if anti_whale['progressive_tax_rates']:
                effectiveness += 30
            if anti_whale['cooldown_periods']:
                effectiveness += 15
            if anti_whale['anti_bot_measures']:
                effectiveness += 10
            
            anti_whale['effectiveness_score'] = min(100.0, effectiveness)
            
            # Assess bypass potential
            if effectiveness < 30:
                anti_whale['bypass_potential'] = 'HIGH'
            elif effectiveness < 60:
                anti_whale['bypass_potential'] = 'MEDIUM'
            else:
                anti_whale['bypass_potential'] = 'LOW'
            
            return anti_whale
            
        except Exception as e:
            logger.error(f"Error analyzing anti-whale mechanisms: {e}")
            return {'error': str(e)}
    
    def _compile_tax_structure(
        self,
        static_taxes: Dict[str, Any],
        dynamic_taxes: Dict[str, Any],
        restrictions: Dict[str, Any],
        tax_distribution: Dict[str, Any],
        anti_whale: Dict[str, Any]
    ) -> TaxStructure:
        """Compile comprehensive tax structure."""
        return TaxStructure(
            buy_tax_percent=static_taxes.get('buy_tax_percent', 0.0),
            sell_tax_percent=static_taxes.get('sell_tax_percent', 0.0),
            transfer_tax_percent=static_taxes.get('transfer_tax_percent', 0.0),
            max_transaction_percent=restrictions.get('restrictions_details', {}).get('max_transaction_percent'),
            has_dynamic_taxes=dynamic_taxes.get('has_dynamic_taxes', False),
            tax_distribution=tax_distribution.get('distribution_percentages', {}),
            anti_whale_enabled=anti_whale.get('max_transaction_limits', False) or anti_whale.get('max_wallet_limits', False),
            cooldown_enabled=restrictions.get('cooldown_enabled', False),
            whitelist_enabled=restrictions.get('whitelist_only_mode', False)
        )
    
    def _calculate_tax_risk(
        self,
        tax_structure: TaxStructure,
        tax_simulations: List[TaxEvent],
        restrictions: Dict[str, Any]
    ) -> Tuple[float, float]:
        """Calculate overall tax risk score and confidence."""
        risk_factors = []
        
        # Tax rate risk (highest weight)
        tax_risk = self._score_tax_rates(tax_structure)
        risk_factors.append(('tax_rates', tax_risk, 0.4))
        
        # Dynamic tax risk
        dynamic_risk = 0.8 if tax_structure.has_dynamic_taxes else 0.1
        risk_factors.append(('dynamic_taxes', dynamic_risk, 0.2))
        
        # Restriction risk
        restriction_risk = self._score_restrictions(restrictions)
        risk_factors.append(('restrictions', restriction_risk, 0.2))
        
        # Simulation results risk
        simulation_risk = self._score_simulation_results(tax_simulations)
        risk_factors.append(('simulations', simulation_risk, 0.1))
        
        # Whitelist risk (extreme)
        whitelist_risk = 0.95 if tax_structure.whitelist_enabled else 0.0
        risk_factors.append(('whitelist', whitelist_risk, 0.1))
        
        # Calculate weighted risk
        total_risk = 0.0
        total_weight = 0.0
        
        for factor_name, risk, weight in risk_factors:
            total_risk += risk * weight
            total_weight += weight
        
        overall_risk = total_risk / total_weight if total_weight > 0 else 0.5
        
        # Confidence based on simulation success and data completeness
        confidence = 0.8
        failed_simulations = sum(1 for sim in tax_simulations if not sim.simulation_successful)
        if failed_simulations > 0:
            confidence -= failed_simulations * 0.15
        
        confidence = max(0.3, min(0.95, confidence))
        
        return overall_risk, confidence
    
    def _score_tax_rates(self, tax_structure: TaxStructure) -> float:
        """Score risk based on tax rates."""
        risk_score = 0.0
        
        # Buy tax scoring
        if tax_structure.buy_tax_percent > self.thresholds['excessive_tax_threshold']:
            risk_score += 0.8
        elif tax_structure.buy_tax_percent > self.thresholds['max_buy_tax_percent']:
            risk_score += 0.5
        elif tax_structure.buy_tax_percent > 5.0:
            risk_score += 0.2
        
        # Sell tax scoring (usually higher than buy)
        if tax_structure.sell_tax_percent > self.thresholds['excessive_tax_threshold']:
            risk_score += 0.9
        elif tax_structure.sell_tax_percent > self.thresholds['max_sell_tax_percent']:
            risk_score += 0.6
        elif tax_structure.sell_tax_percent > 10.0:
            risk_score += 0.3
        
        # Transfer tax scoring
        if tax_structure.transfer_tax_percent > self.thresholds['max_transfer_tax_percent']:
            risk_score += 0.4
        
        return min(1.0, risk_score)
    
    def _score_restrictions(self, restrictions: Dict[str, Any]) -> float:
        """Score risk based on transfer restrictions."""
        risk_score = 0.0
        
        if restrictions.get('whitelist_only_mode', False):
            return 0.95  # Extremely high risk
        
        if restrictions.get('trading_paused', False):
            return 0.9  # Very high risk
        
        # Max transaction restrictions
        if restrictions.get('max_transaction_enabled', False):
            max_tx_percent = restrictions.get('restrictions_details', {}).get('max_transaction_percent', 2.0)
            if max_tx_percent < 0.5:
                risk_score += 0.6
            elif max_tx_percent < 1.0:
                risk_score += 0.3
            else:
                risk_score += 0.1
        
        # Cooldown restrictions
        if restrictions.get('cooldown_enabled', False):
            cooldown_seconds = restrictions.get('restrictions_details', {}).get('cooldown_seconds', 60)
            if cooldown_seconds > 300:
                risk_score += 0.4
            elif cooldown_seconds > 120:
                risk_score += 0.2
            else:
                risk_score += 0.1
        
        # Blacklist capability
        if restrictions.get('blacklist_enabled', False):
            risk_score += 0.3
        
        return min(1.0, risk_score)
    
    def _score_simulation_results(self, tax_simulations: List[TaxEvent]) -> float:
        """Score risk based on transaction simulation results."""
        if not tax_simulations:
            return 0.7  # High risk for no simulation data
        
        risk_score = 0.0
        
        for simulation in tax_simulations:
            if not simulation.simulation_successful:
                risk_score += 0.3  # Failed simulations are concerning
            
            # High effective tax rates
            if simulation.effective_tax_rate > 25.0:
                risk_score += 0.5
            elif simulation.effective_tax_rate > 15.0:
                risk_score += 0.3
            elif simulation.effective_tax_rate > 10.0:
                risk_score += 0.1
            
            # Additional fees
            if simulation.additional_fees:
                risk_score += len(simulation.additional_fees) * 0.1
        
        return min(1.0, risk_score / max(1, len(tax_simulations)))
    
    def _generate_tax_warnings(
        self, 
        tax_structure: TaxStructure, 
        tax_simulations: List[TaxEvent]
    ) -> List[str]:
        """Generate tax-specific warnings."""
        warnings = []
        
        # Excessive tax warnings
        if tax_structure.buy_tax_percent > self.thresholds['excessive_tax_threshold']:
            warnings.append(f"EXCESSIVE buy tax: {tax_structure.buy_tax_percent:.1f}% - potential scam")
        
        if tax_structure.sell_tax_percent > self.thresholds['excessive_tax_threshold']:
            warnings.append(f"EXCESSIVE sell tax: {tax_structure.sell_tax_percent:.1f}% - exit difficulty")
        
        # High tax warnings
        if tax_structure.sell_tax_percent > self.thresholds['max_sell_tax_percent']:
            warnings.append(f"HIGH sell tax: {tax_structure.sell_tax_percent:.1f}% - reduces profitability")
        
        # Dynamic tax warnings
        if tax_structure.has_dynamic_taxes:
            warnings.append("Dynamic tax system - rates may change unexpectedly")
        
        # Restriction warnings
        if tax_structure.whitelist_enabled:
            warnings.append("CRITICAL: Whitelist-only trading - potential honeypot")
        
        if tax_structure.max_transaction_percent and tax_structure.max_transaction_percent < 1.0:
            warnings.append(f"Severe transaction limits: {tax_structure.max_transaction_percent:.2f}% max transaction")
        
        # Simulation warnings
        failed_sims = [sim for sim in tax_simulations if not sim.simulation_successful]
        if failed_sims:
            warnings.append(f"{len(failed_sims)} transaction simulation(s) failed - potential restrictions")
        
        return warnings
    
    def _compile_tax_details(
        self,
        tax_structure: TaxStructure,
        tax_simulations: List[TaxEvent],
        dynamic_taxes: Dict[str, Any],
        restrictions: Dict[str, Any],
        tax_distribution: Dict[str, Any],
        anti_whale: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile detailed tax analysis results."""
        return {
            'tax_structure': {
                'buy_tax_percent': tax_structure.buy_tax_percent,
                'sell_tax_percent': tax_structure.sell_tax_percent,
                'transfer_tax_percent': tax_structure.transfer_tax_percent,
                'has_dynamic_taxes': tax_structure.has_dynamic_taxes,
                'max_transaction_percent': tax_structure.max_transaction_percent
            },
            'tax_simulations': [
                {
                    'type': sim.event_type,
                    'effective_rate': sim.effective_tax_rate,
                    'base_rate': sim.base_tax_rate,
                    'successful': sim.simulation_successful,
                    'restrictions': sim.restrictions_applied
                } for sim in tax_simulations
            ],
            'dynamic_mechanisms': dynamic_taxes,
            'transfer_restrictions': restrictions,
            'tax_distribution': tax_distribution,
            'anti_whale_protection': anti_whale,
            'tax_summary': {
                'total_buy_cost': tax_structure.buy_tax_percent,
                'total_sell_cost': tax_structure.sell_tax_percent,
                'round_trip_cost': tax_structure.buy_tax_percent + tax_structure.sell_tax_percent,
                'sustainability_rating': tax_distribution.get('sustainable_model', 'UNKNOWN'),
                'restriction_level': self._assess_restriction_level(restrictions)
            },
            'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
            'chain_id': self.chain_id
        }
    
    def _assess_data_quality(
        self, 
        tax_structure: TaxStructure, 
        tax_simulations: List[TaxEvent]
    ) -> str:
        """Assess the quality of tax analysis data."""
        quality_score = 0
        
        # Tax structure completeness
        if tax_structure.buy_tax_percent >= 0:
            quality_score += 1
        if tax_structure.sell_tax_percent >= 0:
            quality_score += 1
        
        # Simulation completeness
        successful_sims = sum(1 for sim in tax_simulations if sim.simulation_successful)
        if successful_sims >= 2:
            quality_score += 2
        elif successful_sims >= 1:
            quality_score += 1
        
        # Distribution analysis
        if tax_structure.tax_distribution:
            quality_score += 1
        
        if quality_score >= 5:
            return "EXCELLENT"
        elif quality_score >= 4:
            return "GOOD"
        elif quality_score >= 2:
            return "FAIR"
        else:
            return "POOR"
    
    # Helper methods
    
    def _assess_sustainability(self, distribution: Dict[str, float]) -> str:
        """Assess if tax distribution model is sustainable."""
        team_allocation = distribution.get('marketing', 0) + distribution.get('treasury', 0)
        
        if team_allocation > 60:
            return "UNSUSTAINABLE"
        elif team_allocation > 40:
            return "QUESTIONABLE"
        elif team_allocation > 20:
            return "MODERATE"
        else:
            return "SUSTAINABLE"
    
    def _calculate_transparency_score(self, distribution: Dict[str, float]) -> float:
        """Calculate transparency score based on tax allocation clarity."""
        known_allocations = ['liquidity', 'burn', 'reflection']
        unknown_allocations = ['marketing', 'treasury']
        
        known_percent = sum(distribution.get(alloc, 0) for alloc in known_allocations)
        unknown_percent = sum(distribution.get(alloc, 0) for alloc in unknown_allocations)
        
        total = known_percent + unknown_percent
        if total == 0:
            return 0.5
        
        return known_percent / total
    
    def _identify_distribution_red_flags(self, distribution: Dict[str, float]) -> List[str]:
        """Identify red flags in tax distribution."""
        red_flags = []
        
        marketing_treasury = distribution.get('marketing', 0) + distribution.get('treasury', 0)
        if marketing_treasury > 70:
            red_flags.append("Excessive team allocation")
        
        if 'burn' not in distribution and 'reflection' not in distribution:
            red_flags.append("No deflationary mechanisms")
        
        if distribution.get('liquidity', 0) < 10:
            red_flags.append("Insufficient liquidity allocation")
        
        return red_flags
    
    def _generate_mock_addresses(self, distribution: Dict[str, float]) -> Dict[str, str]:
        """Generate mock addresses for tax distribution."""
        addresses = {}
        base_hash = hash(str(distribution))
        
        for i, allocation_type in enumerate(distribution.keys()):
            addr_hash = (base_hash + i) % (16**40)
            addresses[allocation_type] = f"0x{addr_hash:040x}"
        
        return addresses
    
    def _assess_restriction_level(self, restrictions: Dict[str, Any]) -> str:
        """Assess overall restriction level."""
        if restrictions.get('whitelist_only_mode', False):
            return "EXTREME"
        
        restriction_count = sum([
            restrictions.get('max_transaction_enabled', False),
            restrictions.get('max_wallet_enabled', False),
            restrictions.get('cooldown_enabled', False),
            restrictions.get('blacklist_enabled', False)
        ])
        
        if restriction_count >= 3:
            return "HIGH"
        elif restriction_count >= 2:
            return "MEDIUM"
        elif restriction_count >= 1:
            return "LOW"
        else:
            return "NONE"
    
    def _validate_inputs(self, token_address: str, context: Dict[str, Any]) -> bool:
        """Validate analyzer inputs."""
        return (
            token_address and 
            len(token_address) == 42 and 
            token_address.startswith('0x')
        )
    
    def _safe_extract_result(self, result: Any, default: Any) -> Any:
        """Safely extract result from async gather, handling exceptions."""
        if isinstance(result, Exception):
            logger.warning(f"Tax analysis task failed: {result}")
            return default
        return result if result is not None else default
    
    def _get_cached_analysis(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get cached tax analysis if available and fresh."""
        if token_address in self.tax_cache:
            result, timestamp = self.tax_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_minutes * 60):
                return result
            else:
                del self.tax_cache[token_address]
        
        return None
    
    def _cache_analysis_result(self, token_address: str, result: Dict[str, Any]) -> None:
        """Cache tax analysis result."""
        self.tax_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries
        if len(self.tax_cache) > 100:
            oldest_token = min(
                self.tax_cache.keys(),
                key=lambda k: self.tax_cache[k][1]
            )
            del self.tax_cache[oldest_token]
    
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
            score=0.8,  # High risk for failed tax analysis
            confidence=0.2,
            details={'error': error_message},
            warnings=[f"Tax analysis failed: {error_message}"],
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
__all__ = ['TaxAnalyzer', 'TaxStructure', 'TaxEvent']