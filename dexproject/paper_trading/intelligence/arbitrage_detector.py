"""
Arbitrage Detector for Multi-DEX Price Comparison

This module detects arbitrage opportunities by analyzing price differences across DEXs.
It calculates net profit after gas costs and applies profitability thresholds.

Phase 2: Multi-DEX Price Comparison
File: paper_trading/intelligence/arbitrage_detector.py
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

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ArbitrageOpportunity:
    """
    Detected arbitrage opportunity between two DEXs.
    
    Attributes:
        token_address: Token contract address
        token_symbol: Token symbol
        buy_dex: DEX to buy from (lower price)
        sell_dex: DEX to sell on (higher price)
        buy_price: Buy price (USD)
        sell_price: Sell price (USD)
        price_spread_percent: Price difference percentage
        trade_amount_usd: Suggested trade amount
        gross_profit_usd: Profit before costs
        gas_cost_usd: Estimated gas cost
        net_profit_usd: Profit after gas
        profit_margin_percent: Net profit as % of trade
        is_profitable: Whether arbitrage is profitable
        risk_factors: List of risk considerations
        detected_at: When opportunity was detected
    """
    token_address: str
    token_symbol: str
    buy_dex: str
    sell_dex: str
    buy_price: Decimal
    sell_price: Decimal
    price_spread_percent: Decimal
    trade_amount_usd: Decimal = Decimal('1000')
    gross_profit_usd: Decimal = Decimal('0')
    gas_cost_usd: Decimal = Decimal('0')
    net_profit_usd: Decimal = Decimal('0')
    profit_margin_percent: Decimal = Decimal('0')
    is_profitable: bool = False
    risk_factors: List[str] = field(default_factory=list)
    detected_at: datetime = None
    
    def __post_init__(self):
        """Calculate profitability metrics after initialization."""
        if self.detected_at is None:
            self.detected_at = timezone.now()
        
        # Calculate gross profit
        self.gross_profit_usd = (
            (self.sell_price - self.buy_price) / self.buy_price
        ) * self.trade_amount_usd
        
        # Calculate net profit
        self.net_profit_usd = self.gross_profit_usd - self.gas_cost_usd
        
        # Calculate profit margin
        if self.trade_amount_usd > 0:
            self.profit_margin_percent = (
                (self.net_profit_usd / self.trade_amount_usd) * Decimal('100')
            )
        
        # Determine if profitable
        min_profit = DEXComparisonDefaults.MIN_ARBITRAGE_PROFIT_USD
        self.is_profitable = self.net_profit_usd >= min_profit
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'token_address': self.token_address,
            'token_symbol': self.token_symbol,
            'buy_dex': self.buy_dex,
            'sell_dex': self.sell_dex,
            'buy_price': float(self.buy_price),
            'sell_price': float(self.sell_price),
            'price_spread_percent': float(self.price_spread_percent),
            'trade_amount_usd': float(self.trade_amount_usd),
            'gross_profit_usd': float(self.gross_profit_usd),
            'gas_cost_usd': float(self.gas_cost_usd),
            'net_profit_usd': float(self.net_profit_usd),
            'profit_margin_percent': float(self.profit_margin_percent),
            'is_profitable': self.is_profitable,
            'risk_factors': self.risk_factors,
            'detected_at': self.detected_at.isoformat() if self.detected_at else None
        }


# =============================================================================
# ARBITRAGE DETECTOR
# =============================================================================

class ArbitrageDetector:
    """
    Detects and evaluates arbitrage opportunities across DEXs.
    
    Features:
    - Identifies price discrepancies between DEXs
    - Calculates profit after gas costs
    - Applies profitability thresholds
    - Assesses execution risks
    - Tracks historical opportunities
    
    Usage:
        detector = ArbitrageDetector(gas_price_gwei=Decimal('1.0'))
        
        # From price comparison
        opportunity = detector.detect_arbitrage(price_comparison)
        
        if opportunity and opportunity.is_profitable:
            print(f"Arbitrage found: ${opportunity.net_profit_usd} profit!")
    """
    
    def __init__(
        self,
        gas_price_gwei: Optional[Decimal] = None,
        min_spread_percent: Optional[Decimal] = None,
        min_profit_usd: Optional[Decimal] = None
    ):
        """
        Initialize arbitrage detector.
        
        Args:
            gas_price_gwei: Current gas price in gwei (for cost calculation)
            min_spread_percent: Minimum price spread to consider
            min_profit_usd: Minimum net profit threshold
        """
        # Gas pricing
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
        
        # Performance tracking
        self.opportunities_detected = 0
        self.profitable_opportunities = 0
        self.total_potential_profit = Decimal('0')
        
        self.logger = logging.getLogger(f'{__name__}.Detector')
        
        self.logger.info(
            f"[ARBITRAGE] Initialized: "
            f"Min spread: {self.min_spread_percent}%, "
            f"Min profit: ${self.min_profit_usd}, "
            f"Gas price: {self.gas_price_gwei} gwei"
        )
    
    # =========================================================================
    # MAIN DETECTION METHOD
    # =========================================================================
    
    def detect_arbitrage(
        self,
        price_comparison: DEXPriceComparison,
        trade_amount_usd: Decimal = Decimal('1000')
    ) -> Optional[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunity from price comparison.
        
        This method:
        1. Finds lowest and highest prices
        2. Calculates price spread
        3. Checks if spread exceeds minimum
        4. Estimates gas costs
        5. Calculates net profit
        6. Assesses risks
        
        Args:
            price_comparison: DEXPriceComparison with prices from all DEXs
            trade_amount_usd: Proposed trade amount in USD
            
        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        try:
            # Need at least 2 successful prices
            successful_prices = [
                p for p in price_comparison.prices
                if p.success and p.price_usd
            ]
            
            if len(successful_prices) < 2:
                self.logger.debug(
                    f"[ARBITRAGE] Not enough prices for {price_comparison.token_symbol} "
                    f"({len(successful_prices)} < 2)"
                )
                return None
            
            # Find lowest price (buy here)
            buy_price_obj = min(successful_prices, key=lambda x: x.price_usd)
            buy_price = buy_price_obj.price_usd
            buy_dex = buy_price_obj.dex_name
            
            # Find highest price (sell here)
            sell_price_obj = max(successful_prices, key=lambda x: x.price_usd)
            sell_price = sell_price_obj.price_usd
            sell_dex = sell_price_obj.dex_name
            
            # Can't arbitrage same DEX
            if buy_dex == sell_dex:
                return None
            
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
            
            # Estimate gas cost
            gas_cost_usd = self._estimate_gas_cost()
            
            # Check if gas price is reasonable
            if self.gas_price_gwei > self.max_gas_price_gwei:
                risk_factor = (
                    f"High gas price: {self.gas_price_gwei} gwei > "
                    f"{self.max_gas_price_gwei} gwei threshold"
                )
            else:
                risk_factor = None
            
            # Create opportunity
            opportunity = ArbitrageOpportunity(
                token_address=price_comparison.token_address,
                token_symbol=price_comparison.token_symbol,
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                buy_price=buy_price,
                sell_price=sell_price,
                price_spread_percent=price_spread_percent,
                trade_amount_usd=trade_amount_usd,
                gas_cost_usd=gas_cost_usd
            )
            
            # Add risk factors
            if risk_factor:
                opportunity.risk_factors.append(risk_factor)
            
            # Add liquidity risks if available
            self._assess_liquidity_risks(opportunity, buy_price_obj, sell_price_obj)
            
            # Track statistics
            self.opportunities_detected += 1
            
            if opportunity.is_profitable:
                self.profitable_opportunities += 1
                self.total_potential_profit += opportunity.net_profit_usd
                
                self.logger.info(
                    f"[ARBITRAGE] 🎯 Profitable opportunity found for {opportunity.token_symbol}:"
                )
                self.logger.info(
                    f"[ARBITRAGE]    Buy on {buy_dex} at ${buy_price:.4f}"
                )
                self.logger.info(
                    f"[ARBITRAGE]    Sell on {sell_dex} at ${sell_price:.4f}"
                )
                self.logger.info(
                    f"[ARBITRAGE]    Spread: {price_spread_percent:.2f}%"
                )
                self.logger.info(
                    f"[ARBITRAGE]    Net profit: ${opportunity.net_profit_usd:.2f}"
                )
                self.logger.info(
                    f"[ARBITRAGE]    Profit margin: {opportunity.profit_margin_percent:.2f}%"
                )
            else:
                self.logger.debug(
                    f"[ARBITRAGE] Opportunity found but not profitable for "
                    f"{opportunity.token_symbol}: "
                    f"${opportunity.net_profit_usd:.2f} < ${self.min_profit_usd}"
                )
            
            return opportunity
        
        except Exception as e:
            self.logger.error(
                f"[ARBITRAGE] Error detecting arbitrage for "
                f"{price_comparison.token_symbol}: {e}",
                exc_info=True
            )
            return None
    
    # =========================================================================
    # GAS COST ESTIMATION
    # =========================================================================
    
    def _estimate_gas_cost(self) -> Decimal:
        """
        Estimate total gas cost for arbitrage execution.
        
        Assumes 2 swaps (buy + sell) with approval if needed.
        
        Returns:
            Estimated gas cost in USD
        """
        # Estimated gas units for arbitrage
        # - Token approval: ~50,000 gas
        # - Buy swap: ~150,000 gas
        # - Sell swap: ~150,000 gas
        # Total: ~350,000 gas
        total_gas_units = Decimal('350000')
        
        # Convert gas price from gwei to ETH
        gas_price_eth = self.gas_price_gwei / Decimal('1e9')
        
        # Calculate total cost in ETH
        gas_cost_eth = total_gas_units * gas_price_eth
        
        # Convert to USD
        gas_cost_usd = gas_cost_eth * self.eth_price_usd
        
        return gas_cost_usd
    
    # =========================================================================
    # RISK ASSESSMENT
    # =========================================================================
    
    def _assess_liquidity_risks(
        self,
        opportunity: ArbitrageOpportunity,
        buy_price_obj: DEXPrice,
        sell_price_obj: DEXPrice
    ) -> None:
        """
        Assess liquidity-related risks for arbitrage.
        
        Args:
            opportunity: ArbitrageOpportunity to assess
            buy_price_obj: DEXPrice for buy DEX
            sell_price_obj: DEXPrice for sell DEX
        """
        # Check liquidity on buy DEX
        if buy_price_obj.liquidity_usd:
            if buy_price_obj.liquidity_usd < opportunity.trade_amount_usd * 2:
                opportunity.risk_factors.append(
                    f"Low liquidity on {buy_price_obj.dex_name}: "
                    f"${buy_price_obj.liquidity_usd:,.0f}"
                )
        
        # Check liquidity on sell DEX
        if sell_price_obj.liquidity_usd:
            if sell_price_obj.liquidity_usd < opportunity.trade_amount_usd * 2:
                opportunity.risk_factors.append(
                    f"Low liquidity on {sell_price_obj.dex_name}: "
                    f"${sell_price_obj.liquidity_usd:,.0f}"
                )
    
    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================
    
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
            'current_gas_price_gwei': float(self.gas_price_gwei)
        }
    
    # =========================================================================
    # CONFIGURATION UPDATES
    # =========================================================================
    
    def update_gas_price(self, gas_price_gwei: Decimal) -> None:
        """
        Update current gas price for cost calculations.
        
        Args:
            gas_price_gwei: New gas price in gwei
        """
        self.gas_price_gwei = gas_price_gwei
        self.logger.info(
            f"[ARBITRAGE] Updated gas price to {gas_price_gwei} gwei"
        )
    
    def update_eth_price(self, eth_price_usd: Decimal) -> None:
        """
        Update ETH price for gas cost calculations.
        
        Args:
            eth_price_usd: New ETH price in USD
        """
        self.eth_price_usd = eth_price_usd
        self.logger.info(
            f"[ARBITRAGE] Updated ETH price to ${eth_price_usd}"
        )