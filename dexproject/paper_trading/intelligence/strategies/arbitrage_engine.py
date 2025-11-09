"""
Unified Arbitrage Engine - Phase 2 Complete

Merges arbitrage_detector.py and smart_arbitrage_engine.py into a single,
comprehensive arbitrage detection system.

Features from BOTH implementations:
- Simple detection from DEXPriceComparison (arbitrage_detector style)
- Advanced detection from DEX price dictionary (smart_arbitrage_engine style)
- Comprehensive cost accounting (gas, slippage)
- MEV risk assessment
- Liquidity-based trade sizing
- Confidence scoring
- Performance tracking

File: paper_trading/intelligence/arbitrage_engine.py
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

# Import DEX price comparison classes
from paper_trading.intelligence.dex_price_comparator import (
    DEXPriceComparison,
    DEXPrice
)

# Import constants and defaults
from paper_trading.constants import ArbitrageFields
from paper_trading.defaults import (
    DEXComparisonDefaults,
    ArbitrageDefaults
)

# Import gas estimates from centralized analyzers constants (Phase 3)
from paper_trading.intelligence.dex_integrations.constants import (
    GAS_ESTIMATES_PER_CHAIN,
    DEFAULT_GAS_ESTIMATE,
    get_gas_estimate
)

logger = logging.getLogger(__name__)


# =============================================================================
# UNIFIED DATA CLASS - Best of Both Worlds
# =============================================================================

@dataclass
class ArbitrageOpportunity:
    """
    Unified arbitrage opportunity representation.
    
    Combines fields from both arbitrage_detector.py and smart_arbitrage_engine.py
    to provide comprehensive arbitrage analysis.
    
    Pricing Information:
        token_address: Token contract address
        token_symbol: Token symbol
        buy_dex: DEX to buy from (lower price)
        sell_dex: DEX to sell on (higher price)
        buy_price: Buy price in USD
        sell_price: Sell price in USD
        buy_liquidity: Buy DEX liquidity in USD
        sell_liquidity: Sell DEX liquidity in USD
    
    Profitability Metrics:
        gross_spread_percent: Price difference percentage
        gross_profit_usd: Profit before costs
        estimated_gas_cost: Gas cost in USD
        estimated_slippage: Slippage cost in USD
        net_profit_usd: Profit after all costs
        profit_margin_percent: Net profit as % of trade
    
    Risk Assessment:
        mev_risk_score: MEV/frontrunning risk (0-100)
        liquidity_risk: Liquidity risk level (low/medium/high)
        confidence_score: Overall confidence (0-100)
        risk_factors: List of specific risk considerations
    
    Trade Sizing:
        trade_amount_usd: Proposed trade amount
        max_trade_size: Maximum recommended tokens
        recommended_size: Conservative trade size
    
    Execution:
        is_profitable: Whether arbitrage is profitable after costs
        detected_at: When opportunity was detected
    """
    # Token information
    token_address: str
    token_symbol: str
    
    # Pricing
    buy_dex: str
    buy_price: Decimal
    buy_liquidity: Decimal
    
    sell_dex: str
    sell_price: Decimal
    sell_liquidity: Decimal
    
    # Profitability
    gross_spread_percent: Decimal
    gross_profit_usd: Decimal
    estimated_gas_cost: Decimal
    estimated_slippage: Decimal
    net_profit_usd: Decimal
    profit_margin_percent: Decimal = Decimal('0')
    
    # Risk assessment
    mev_risk_score: int = 0  # 0-100
    liquidity_risk: str = 'unknown'  # low/medium/high
    confidence_score: int = 0  # 0-100
    risk_factors: List[str] = field(default_factory=list)
    
    # Trade sizing
    trade_amount_usd: Decimal = Decimal('1000')
    max_trade_size: Decimal = Decimal('0')
    recommended_size: Decimal = Decimal('0')
    
    # Status
    is_profitable: bool = False
    detected_at: datetime = None
    
    def __post_init__(self):
        """Calculate derived metrics after initialization."""
        if self.detected_at is None:
            self.detected_at = timezone.now()
        
        # Calculate profit margin percentage
        if self.trade_amount_usd > 0:
            self.profit_margin_percent = (
                (self.net_profit_usd / self.trade_amount_usd) * Decimal('100')
            )
        
        # Determine profitability
        min_profit = DEXComparisonDefaults.MIN_ARBITRAGE_PROFIT_USD
        self.is_profitable = self.net_profit_usd >= min_profit
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'token_address': self.token_address,
            'token_symbol': self.token_symbol,
            'buy_dex': self.buy_dex,
            'buy_price': float(self.buy_price),
            'buy_liquidity': float(self.buy_liquidity),
            'sell_dex': self.sell_dex,
            'sell_price': float(self.sell_price),
            'sell_liquidity': float(self.sell_liquidity),
            'gross_spread_percent': float(self.gross_spread_percent),
            'gross_profit_usd': float(self.gross_profit_usd),
            'estimated_gas_cost': float(self.estimated_gas_cost),
            'estimated_slippage': float(self.estimated_slippage),
            'net_profit_usd': float(self.net_profit_usd),
            'profit_margin_percent': float(self.profit_margin_percent),
            'mev_risk_score': self.mev_risk_score,
            'liquidity_risk': self.liquidity_risk,
            'confidence_score': self.confidence_score,
            'risk_factors': self.risk_factors,
            'trade_amount_usd': float(self.trade_amount_usd),
            'max_trade_size': float(self.max_trade_size),
            'recommended_size': float(self.recommended_size),
            'is_profitable': self.is_profitable,
            'detected_at': self.detected_at.isoformat() if self.detected_at else None
        }


# =============================================================================
# UNIFIED ARBITRAGE ENGINE - Best of Both Worlds
# =============================================================================

class ArbitrageEngine:
    """
    Unified arbitrage detection engine.
    
    Combines features from both ArbitrageDetector and SmartArbitrageEngine:
    - Two detection methods (from DEXPriceComparison or dict of prices)
    - Comprehensive cost accounting (gas, slippage)
    - MEV risk assessment
    - Liquidity-based trade sizing
    - Confidence scoring
    - Performance tracking
    
    Usage Examples:
        # Method 1: From DEXPriceComparison (original style)
        engine = ArbitrageEngine(chain_id=8453, gas_price_gwei=Decimal('1.0'))
        opportunity = engine.detect_from_comparison(price_comparison)
        
        # Method 2: From DEX prices dict (smart engine style)
        opportunity = engine.detect_from_prices(
            dex_prices={'uniswap_v3': price1, 'sushiswap': price2},
            token_symbol='WETH',
            token_address='0x...'
        )
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        gas_price_gwei: Optional[Decimal] = None,
        min_spread_percent: Optional[Decimal] = None,
        min_profit_usd: Optional[Decimal] = None,
        max_gas_cost_percent: Decimal = Decimal('20')
    ):
        """
        Initialize unified arbitrage engine.
        
        Args:
            chain_id: Blockchain chain ID (default: Base mainnet)
            gas_price_gwei: Current gas price in gwei
            min_spread_percent: Minimum price spread to consider
            min_profit_usd: Minimum net profit threshold
            max_gas_cost_percent: Max gas cost as % of profit
        """
        self.chain_id = chain_id
        self.gas_price_gwei = gas_price_gwei or Decimal('1.0')
        self.eth_price_usd = Decimal('2500')  # Approximate ETH price
        
        # Thresholds
        self.min_spread_percent = (
            min_spread_percent or
            DEXComparisonDefaults.MIN_ARBITRAGE_SPREAD_PERCENT
        )
        self.min_profit_usd = (
            min_profit_usd or
            DEXComparisonDefaults.MIN_ARBITRAGE_PROFIT_USD
        )
        self.max_gas_price_gwei = DEXComparisonDefaults.MAX_ARBITRAGE_GAS_PRICE_GWEI
        self.max_gas_cost_percent = max_gas_cost_percent
        
        # NOTE: Gas estimates now imported from centralized constants (Phase 3)
        # See: paper_trading.intelligence.analyzers.constants.GAS_ESTIMATES_PER_CHAIN
        
        # Performance tracking
        self.opportunities_detected = 0
        self.profitable_opportunities = 0
        self.total_potential_profit = Decimal('0')
        
        self.logger = logging.getLogger(f'{__name__}.ArbitrageEngine')
        
        self.logger.info(
            f"[ARBITRAGE ENGINE] Initialized: "
            f"Chain {chain_id}, Min spread: {self.min_spread_percent}%, "
            f"Min profit: ${self.min_profit_usd}, Gas: {self.gas_price_gwei} gwei"
        )
    
    # =========================================================================
    # DETECTION METHOD 1: From DEXPriceComparison (original style)
    # =========================================================================
    
    def detect_from_comparison(
        self,
        price_comparison: DEXPriceComparison,
        trade_amount_usd: Decimal = Decimal('1000')
    ) -> Optional[ArbitrageOpportunity]:
        """
        Detect arbitrage from DEXPriceComparison object.
        
        This is the original arbitrage_detector.py style interface
        for backward compatibility.
        
        Args:
            price_comparison: DEXPriceComparison with prices from all DEXs
            trade_amount_usd: Proposed trade amount in USD
            
        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        try:
            # Get successful prices
            successful_prices = [
                p for p in price_comparison.dex_prices
                if p.success and p.price_usd
            ]
            
            if len(successful_prices) < 2:
                self.logger.debug(
                    f"[ARBITRAGE] {price_comparison.token_symbol}: "
                    f"Need 2+ DEXes, got {len(successful_prices)}"
                )
                return None
            
            # Find best buy (lowest) and sell (highest)
            buy_price_obj = min(successful_prices, key=lambda p: p.price_usd)
            sell_price_obj = max(successful_prices, key=lambda p: p.price_usd)
            
            buy_dex = buy_price_obj.dex_name
            sell_dex = sell_price_obj.dex_name
            buy_price = buy_price_obj.price_usd
            sell_price = sell_price_obj.price_usd
            
            # Calculate price spread
            price_spread_percent = (
                ((sell_price - buy_price) / buy_price) * Decimal('100')
            )
            
            # Check if spread exceeds minimum
            if price_spread_percent < self.min_spread_percent:
                self.logger.debug(
                    f"[ARBITRAGE] Spread too small for {price_comparison.token_symbol}: "
                    f"{price_spread_percent:.2f}% < {self.min_spread_percent}%"
                )
                return None
            
            # Estimate costs
            gas_cost = self._estimate_gas_cost()
            slippage_cost = self._estimate_slippage(buy_price_obj, sell_price_obj, trade_amount_usd)
            
            # Calculate MEV risk
            mev_risk = self._assess_mev_risk(buy_price_obj, sell_price_obj)
            
            # Assess liquidity risk
            liquidity_risk = self._assess_liquidity_risk(
                buy_price_obj.liquidity_usd,
                sell_price_obj.liquidity_usd,
                trade_amount_usd
            )
            
            # Calculate trade sizes
            max_size, recommended_size = self._calculate_trade_sizes(
                buy_price_obj,
                sell_price_obj,
                trade_amount_usd
            )
            
            # Calculate profit
            gross_profit = (
                (sell_price - buy_price) / buy_price
            ) * trade_amount_usd
            net_profit = gross_profit - gas_cost - slippage_cost
            
            # Calculate confidence score
            confidence = self._calculate_confidence(
                spread_percent=price_spread_percent,
                mev_risk=mev_risk,
                liquidity_score=self._liquidity_score(
                    min(
                        buy_price_obj.liquidity_usd or Decimal('0'),
                        sell_price_obj.liquidity_usd or Decimal('0')
                    )
                )
            )
            
            # Build risk factors list
            risk_factors = []
            
            # Gas price risk
            if self.gas_price_gwei > self.max_gas_price_gwei:
                risk_factors.append(
                    f"High gas price: {self.gas_price_gwei} gwei > "
                    f"{self.max_gas_price_gwei} gwei threshold"
                )
            
            # Liquidity risks
            if buy_price_obj.liquidity_usd:
                if buy_price_obj.liquidity_usd < trade_amount_usd * 2:
                    risk_factors.append(
                        f"Low liquidity on {buy_dex}: "
                        f"${buy_price_obj.liquidity_usd:,.0f}"
                    )
            
            if sell_price_obj.liquidity_usd:
                if sell_price_obj.liquidity_usd < trade_amount_usd * 2:
                    risk_factors.append(
                        f"Low liquidity on {sell_dex}: "
                        f"${sell_price_obj.liquidity_usd:,.0f}"
                    )
            
            # MEV risk warning
            if mev_risk > 60:
                risk_factors.append(
                    f"High MEV risk ({mev_risk}%) - Use protection"
                )
            
            # Create opportunity
            opportunity = ArbitrageOpportunity(
                token_address=price_comparison.token_address,
                token_symbol=price_comparison.token_symbol,
                buy_dex=buy_dex,
                buy_price=buy_price,
                buy_liquidity=buy_price_obj.liquidity_usd or Decimal('0'),
                sell_dex=sell_dex,
                sell_price=sell_price,
                sell_liquidity=sell_price_obj.liquidity_usd or Decimal('0'),
                gross_spread_percent=price_spread_percent,
                gross_profit_usd=gross_profit,
                estimated_gas_cost=gas_cost,
                estimated_slippage=slippage_cost,
                net_profit_usd=net_profit,
                mev_risk_score=mev_risk,
                liquidity_risk=liquidity_risk,
                confidence_score=confidence,
                risk_factors=risk_factors,
                trade_amount_usd=trade_amount_usd,
                max_trade_size=max_size,
                recommended_size=recommended_size
            )
            
            # Track statistics
            self._track_opportunity(opportunity)
            
            return opportunity
        
        except Exception as e:
            self.logger.error(
                f"[ARBITRAGE] Error detecting from comparison for "
                f"{price_comparison.token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    # =========================================================================
    # DETECTION METHOD 2: From DEX prices dict (smart engine style)
    # =========================================================================
    
    def detect_from_prices(
        self,
        dex_prices: Dict[str, DEXPrice],
        token_symbol: str,
        token_address: str,
        trade_amount_usd: Decimal = Decimal('1000')
    ) -> Optional[ArbitrageOpportunity]:
        """
        Detect arbitrage from dictionary of DEX prices.
        
        This is the smart_arbitrage_engine.py style interface.
        
        Args:
            dex_prices: Dict of {dex_name: DEXPrice}
            token_symbol: Token symbol
            token_address: Token address
            trade_amount_usd: Proposed trade amount
            
        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        try:
            # Filter successful prices
            valid_prices = {
                dex: price for dex, price in dex_prices.items()
                if price.success and price.price_usd
            }
            
            if len(valid_prices) < 2:
                self.logger.debug(
                    f"[ARBITRAGE] {token_symbol}: Need 2+ DEXes, got {len(valid_prices)}"
                )
                return None
            
            # Find best buy (lowest) and sell (highest)
            buy_dex = min(valid_prices, key=lambda d: valid_prices[d].price_usd)
            sell_dex = max(valid_prices, key=lambda d: valid_prices[d].price_usd)
            
            buy_price_obj = valid_prices[buy_dex]
            sell_price_obj = valid_prices[sell_dex]
            
            # Calculate spread
            spread_percent = (
                (sell_price_obj.price_usd - buy_price_obj.price_usd) /
                buy_price_obj.price_usd * 100
            )
            
            if spread_percent < self.min_spread_percent:
                self.logger.debug(
                    f"[ARBITRAGE] {token_symbol}: Spread {spread_percent:.2f}% "
                    f"< min {self.min_spread_percent}%"
                )
                return None
            
            # Estimate costs
            gas_cost = self._estimate_gas_cost()
            slippage_cost = self._estimate_slippage(buy_price_obj, sell_price_obj, trade_amount_usd)
            mev_risk = self._assess_mev_risk(buy_price_obj, sell_price_obj)
            
            # Calculate trade sizes
            max_size, recommended_size = self._calculate_trade_sizes(
                buy_price_obj,
                sell_price_obj,
                trade_amount_usd
            )
            
            # Use recommended size for profit calculation
            actual_trade_size = min(recommended_size, trade_amount_usd)
            
            # Calculate profit
            gross_profit = (
                (sell_price_obj.price_usd - buy_price_obj.price_usd) /
                buy_price_obj.price_usd
            ) * actual_trade_size
            net_profit = gross_profit - gas_cost - slippage_cost
            
            # Check profitability
            if net_profit < self.min_profit_usd:
                self.logger.info(
                    f"[ARBITRAGE] {token_symbol}: Net profit ${net_profit:.2f} "
                    f"< min ${self.min_profit_usd}"
                )
                return None
            
            # Check gas cost ratio
            if gas_cost > (gross_profit * self.max_gas_cost_percent / 100):
                self.logger.info(
                    f"[ARBITRAGE] {token_symbol}: Gas ${gas_cost:.2f} > "
                    f"{self.max_gas_cost_percent}% of profit ${gross_profit:.2f}"
                )
                return None
            
            # Calculate confidence
            liquidity_score = min(
                self._liquidity_score(buy_price_obj.liquidity_usd),
                self._liquidity_score(sell_price_obj.liquidity_usd)
            )
            confidence = self._calculate_confidence(
                spread_percent=spread_percent,
                mev_risk=mev_risk,
                liquidity_score=liquidity_score
            )
            
            # Assess liquidity risk
            liquidity_risk = self._assess_liquidity_risk(
                buy_price_obj.liquidity_usd,
                sell_price_obj.liquidity_usd,
                actual_trade_size
            )
            
            # Build risk factors
            risk_factors = []
            if mev_risk > 60:
                risk_factors.append(f"High MEV risk ({mev_risk}%)")
            if liquidity_risk == 'high':
                risk_factors.append("High liquidity risk")
            if self.gas_price_gwei > self.max_gas_price_gwei:
                risk_factors.append(f"High gas price ({self.gas_price_gwei} gwei)")
            
            # Create opportunity
            opportunity = ArbitrageOpportunity(
                token_symbol=token_symbol,
                token_address=token_address,
                buy_dex=buy_dex,
                buy_price=buy_price_obj.price_usd,
                buy_liquidity=buy_price_obj.liquidity_usd or Decimal('0'),
                sell_dex=sell_dex,
                sell_price=sell_price_obj.price_usd,
                sell_liquidity=sell_price_obj.liquidity_usd or Decimal('0'),
                gross_spread_percent=spread_percent,
                gross_profit_usd=gross_profit,
                estimated_gas_cost=gas_cost,
                estimated_slippage=slippage_cost,
                net_profit_usd=net_profit,
                mev_risk_score=mev_risk,
                liquidity_risk=liquidity_risk,
                confidence_score=confidence,
                risk_factors=risk_factors,
                trade_amount_usd=actual_trade_size,
                max_trade_size=max_size,
                recommended_size=recommended_size
            )
            
            # Track statistics
            self._track_opportunity(opportunity)
            
            # Log success
            self.logger.info(
                f"[ARBITRAGE] 💰 OPPORTUNITY: {token_symbol}\n"
                f"  Buy:  {buy_dex} @ ${buy_price_obj.price_usd:.4f}\n"
                f"  Sell: {sell_dex} @ ${sell_price_obj.price_usd:.4f}\n"
                f"  Spread: {spread_percent:.2f}%\n"
                f"  Net Profit: ${net_profit:.2f} ✅\n"
                f"  Confidence: {confidence}%\n"
                f"  MEV Risk: {mev_risk}%"
            )
            
            return opportunity
        
        except Exception as e:
            self.logger.error(
                f"[ARBITRAGE] Error detecting from prices for {token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    # =========================================================================
    # COST ESTIMATION - Unified from Both Implementations
    # =========================================================================
    
    def _estimate_gas_cost(self) -> Decimal:
        """
        Estimate total gas cost for arbitrage execution.
        
        Uses per-chain gas estimates for accuracy (Phase 3: centralized).
        Assumes 2 swaps (buy + sell) with approval if needed.
        
        Returns:
            Estimated gas cost in USD
        """
        # Get chain-specific gas estimate from centralized constants
        gas_units = get_gas_estimate(self.chain_id)
        
        # Add approval cost (50k gas units)
        total_gas_units = Decimal(gas_units) + Decimal('50000')
        
        # Convert gas price from gwei to ETH
        gwei_to_eth = Decimal('0.000000001')
        gas_price_eth = self.gas_price_gwei * gwei_to_eth
        
        # Calculate total cost in ETH
        gas_cost_eth = total_gas_units * gas_price_eth
        
        # Convert to USD
        gas_cost_usd = gas_cost_eth * self.eth_price_usd
        
        return gas_cost_usd
    
    def _estimate_slippage(
        self,
        buy_price_obj: DEXPrice,
        sell_price_obj: DEXPrice,
        trade_amount_usd: Decimal
    ) -> Decimal:
        """
        Estimate slippage cost based on liquidity and trade size.
        
        Args:
            buy_price_obj: DEXPrice for buy DEX
            sell_price_obj: DEXPrice for sell DEX
            trade_amount_usd: Trade amount in USD
            
        Returns:
            Estimated slippage cost in USD
        """
        # Get liquidity values
        buy_liquidity = buy_price_obj.liquidity_usd or Decimal('100000')
        sell_liquidity = sell_price_obj.liquidity_usd or Decimal('100000')
        
        # Calculate slippage percentage based on trade size vs liquidity
        # Larger trades relative to liquidity = more slippage
        buy_slippage_pct = (trade_amount_usd / buy_liquidity) * Decimal('0.5')  # 0.5% per 1% of pool
        sell_slippage_pct = (trade_amount_usd / sell_liquidity) * Decimal('0.5')
        
        # Cap slippage at reasonable levels
        buy_slippage_pct = min(buy_slippage_pct, Decimal('5.0'))  # Max 5%
        sell_slippage_pct = min(sell_slippage_pct, Decimal('5.0'))
        
        # Calculate slippage cost
        avg_price = (buy_price_obj.price_usd + sell_price_obj.price_usd) / 2
        total_slippage_pct = buy_slippage_pct + sell_slippage_pct
        slippage_cost = (avg_price * total_slippage_pct / 100)
        
        return slippage_cost
    
    # =========================================================================
    # RISK ASSESSMENT - From smart_arbitrage_engine.py
    # =========================================================================
    
    def _assess_mev_risk(
        self,
        buy_price_obj: DEXPrice,
        sell_price_obj: DEXPrice
    ) -> int:
        """
        Assess MEV/frontrunning risk (0-100).
        
        Higher spread = higher risk (more attractive to MEV bots).
        
        Args:
            buy_price_obj: DEXPrice for buy DEX
            sell_price_obj: DEXPrice for sell DEX
            
        Returns:
            MEV risk score (0-100)
        """
        spread_percent = (
            (sell_price_obj.price_usd - buy_price_obj.price_usd) /
            buy_price_obj.price_usd * 100
        )
        
        if spread_percent < 0.5:
            return 10  # Low risk
        elif spread_percent < 1.0:
            return 30
        elif spread_percent < 2.0:
            return 50
        elif spread_percent < 5.0:
            return 70
        else:
            return 90  # High risk - very attractive to MEV
    
    def _assess_liquidity_risk(
        self,
        buy_liquidity: Optional[Decimal],
        sell_liquidity: Optional[Decimal],
        trade_amount: Decimal
    ) -> str:
        """
        Assess liquidity risk level.
        
        Args:
            buy_liquidity: Buy DEX liquidity in USD
            sell_liquidity: Sell DEX liquidity in USD
            trade_amount: Trade amount in USD
            
        Returns:
            Risk level: 'low', 'medium', or 'high'
        """
        if not buy_liquidity or not sell_liquidity:
            return 'high'
        
        min_liquidity = min(buy_liquidity, sell_liquidity)
        
        # Calculate trade size as percentage of liquidity
        trade_pct = (trade_amount / min_liquidity) * 100
        
        if trade_pct < 1:
            return 'low'  # < 1% of pool
        elif trade_pct < 5:
            return 'medium'  # 1-5% of pool
        else:
            return 'high'  # > 5% of pool
    
    # =========================================================================
    # TRADE SIZING - From smart_arbitrage_engine.py
    # =========================================================================
    
    def _calculate_trade_sizes(
        self,
        buy_price_obj: DEXPrice,
        sell_price_obj: DEXPrice,
        desired_amount_usd: Decimal
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate maximum and recommended trade sizes based on liquidity.
        
        Args:
            buy_price_obj: DEXPrice for buy DEX
            sell_price_obj: DEXPrice for sell DEX
            desired_amount_usd: Desired trade amount in USD
            
        Returns:
            Tuple of (max_size, recommended_size) in token units
        """
        buy_liquidity = buy_price_obj.liquidity_usd or Decimal('0')
        sell_liquidity = sell_price_obj.liquidity_usd or Decimal('0')
        
        if buy_liquidity == 0 or sell_liquidity == 0:
            # No liquidity data - use desired amount
            avg_price = (buy_price_obj.price_usd + sell_price_obj.price_usd) / 2
            tokens = desired_amount_usd / avg_price
            return tokens, tokens * Decimal('0.5')
        
        # Use 10% of minimum liquidity to minimize price impact
        min_liquidity = min(buy_liquidity, sell_liquidity)
        max_size_usd = min_liquidity * Decimal('0.1')
        
        # Convert to token amount
        avg_price = (buy_price_obj.price_usd + sell_price_obj.price_usd) / 2
        max_tokens = max_size_usd / avg_price
        
        # Recommended is 50% of max (conservative)
        recommended_tokens = max_tokens * Decimal('0.5')
        
        return max_tokens, recommended_tokens
    
    def _liquidity_score(self, liquidity_usd: Optional[Decimal]) -> int:
        """
        Score liquidity (0-100).
        
        Args:
            liquidity_usd: Liquidity in USD
            
        Returns:
            Liquidity score (0-100)
        """
        if not liquidity_usd:
            return 0
        
        if liquidity_usd > 1000000:
            return 100
        elif liquidity_usd > 100000:
            return 80
        elif liquidity_usd > 25000:
            return 60
        elif liquidity_usd > 10000:
            return 40
        else:
            return 20
    
    # =========================================================================
    # CONFIDENCE SCORING - From smart_arbitrage_engine.py
    # =========================================================================
    
    def _calculate_confidence(
        self,
        spread_percent: Decimal,
        mev_risk: int,
        liquidity_score: int
    ) -> int:
        """
        Calculate overall confidence score (0-100).
        
        Weighted combination of:
        - Spread size (30%): Higher spread = more confident
        - MEV risk (30%): Lower MEV risk = more confident
        - Liquidity (40%): Higher liquidity = more confident
        
        Args:
            spread_percent: Price spread percentage
            mev_risk: MEV risk score (0-100)
            liquidity_score: Liquidity score (0-100)
            
        Returns:
            Confidence score (0-100)
        """
        # Higher spread = more confident (cap at 40 points)
        spread_score = min(int(spread_percent * 10), 40)
        
        # Lower MEV risk = more confident
        mev_score = 100 - mev_risk
        
        # Weighted average
        confidence = int(
            spread_score * 0.3 +
            mev_score * 0.3 +
            liquidity_score * 0.4
        )
        
        return min(confidence, 100)
    
    # =========================================================================
    # PERFORMANCE TRACKING - From arbitrage_detector.py
    # =========================================================================
    
    def _track_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """Track opportunity statistics."""
        self.opportunities_detected += 1
        
        if opportunity.is_profitable:
            self.profitable_opportunities += 1
            self.total_potential_profit += opportunity.net_profit_usd
            
            self.logger.info(
                f"[ARBITRAGE] 🎯 Profitable: {opportunity.token_symbol} - "
                f"Buy {opportunity.buy_dex} @ ${opportunity.buy_price:.4f}, "
                f"Sell {opportunity.sell_dex} @ ${opportunity.sell_price:.4f}, "
                f"Net: ${opportunity.net_profit_usd:.2f}"
            )
        else:
            self.logger.debug(
                f"[ARBITRAGE] Unprofitable: {opportunity.token_symbol} - "
                f"${opportunity.net_profit_usd:.2f} < ${self.min_profit_usd}"
            )
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get arbitrage detection performance statistics.
        
        Returns:
            Dictionary with performance metrics
        """
        profitability_rate = (
            (self.profitable_opportunities / max(self.opportunities_detected, 1)) * 100
            if self.opportunities_detected > 0
            else 0
        )
        
        avg_profit = (
            self.total_potential_profit / max(self.profitable_opportunities, 1)
            if self.profitable_opportunities > 0
            else Decimal('0')
        )
        
        return {
            'opportunities_detected': self.opportunities_detected,
            'profitable_opportunities': self.profitable_opportunities,
            'profitability_rate_percent': round(float(profitability_rate), 2),
            'total_potential_profit_usd': float(self.total_potential_profit),
            'average_profit_usd': float(avg_profit),
            'min_spread_percent': float(self.min_spread_percent),
            'min_profit_usd': float(self.min_profit_usd),
            'current_gas_price_gwei': float(self.gas_price_gwei),
            'chain_id': self.chain_id
        }
    
    # =========================================================================
    # CONFIGURATION UPDATES - From arbitrage_detector.py
    # =========================================================================
    
    def update_gas_price(self, gas_price_gwei: Decimal) -> None:
        """
        Update current gas price for cost calculations.
        
        Args:
            gas_price_gwei: New gas price in gwei
        """
        self.gas_price_gwei = gas_price_gwei
        self.logger.info(
            f"[ARBITRAGE ENGINE] Updated gas price to {gas_price_gwei} gwei"
        )
    
    def update_eth_price(self, eth_price_usd: Decimal) -> None:
        """
        Update ETH price for gas cost calculations.
        
        Args:
            eth_price_usd: New ETH price in USD
        """
        self.eth_price_usd = eth_price_usd
        self.logger.info(
            f"[ARBITRAGE ENGINE] Updated ETH price to ${eth_price_usd}"
        )