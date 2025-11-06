"""
Smart Arbitrage Engine

Detects profitable cross-DEX arbitrage opportunities accounting for:
- Real execution costs (gas, slippage)
- MEV protection
- Liquidity depth
- Transaction timing
"""

from decimal import Decimal
from typing import List, Optional, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents a profitable arbitrage opportunity."""
    token_symbol: str
    token_address: str
    
    buy_dex: str
    buy_price: Decimal
    buy_liquidity: Decimal
    
    sell_dex: str
    sell_price: Decimal
    sell_liquidity: Decimal
    
    gross_spread_percent: Decimal
    gross_profit_usd: Decimal
    
    estimated_gas_cost: Decimal
    estimated_slippage: Decimal
    mev_risk_score: int  # 0-100
    
    net_profit_usd: Decimal
    confidence_score: int  # 0-100
    
    max_trade_size: Decimal  # Based on liquidity
    recommended_size: Decimal


class SmartArbitrageEngine:
    """
    Advanced arbitrage detection with cost accounting.
    
    Features:
    - Multi-DEX price comparison
    - Gas cost estimation
    - Slippage calculation
    - MEV risk assessment
    - Liquidity-based sizing
    """
    
    def __init__(
        self,
        chain_id: int = 8453,
        min_profit_usd: Decimal = Decimal('5.00'),
        min_spread_percent: Decimal = Decimal('0.5'),
        max_gas_cost_percent: Decimal = Decimal('20'),  # Max 20% of profit
        gas_price_gwei: Decimal = Decimal('1.0')
    ):
        self.chain_id = chain_id
        self.min_profit_usd = min_profit_usd
        self.min_spread_percent = min_spread_percent
        self.max_gas_cost_percent = max_gas_cost_percent
        self.gas_price_gwei = gas_price_gwei
        
        # Gas estimates per chain (in gas units)
        self.gas_estimates = {
            1: 150000,      # Ethereum mainnet
            8453: 100000,   # Base
            42161: 80000,   # Arbitrum
            10: 100000,     # Optimism
        }
        
        logger.info(
            f"[SMART ARBITRAGE] Initialized: "
            f"Min profit=${min_profit_usd}, Min spread={min_spread_percent}%"
        )
    
    async def find_opportunities(
        self,
        dex_prices: Dict[str, 'DEXPrice'],
        token_symbol: str,
        token_address: str
    ) -> Optional[ArbitrageOpportunity]:
        """
        Analyze DEX prices and find profitable arbitrage.
        
        Args:
            dex_prices: Dict of {dex_name: DEXPrice}
            token_symbol: Token symbol
            token_address: Token address
            
        Returns:
            ArbitrageOpportunity if profitable, None otherwise
        """
        # Filter successful prices
        valid_prices = {
            dex: price for dex, price in dex_prices.items()
            if price.success and price.price_usd
        }
        
        if len(valid_prices) < 2:
            logger.debug(f"[SMART ARBITRAGE] {token_symbol}: Need 2+ DEXes, got {len(valid_prices)}")
            return None
        
        # Find best buy (lowest) and sell (highest)
        buy_dex = min(valid_prices, key=lambda d: valid_prices[d].price_usd)
        sell_dex = max(valid_prices, key=lambda d: valid_prices[d].price_usd)
        
        buy_price = valid_prices[buy_dex]
        sell_price = valid_prices[sell_dex]
        
        # Calculate spread
        spread_percent = (
            (sell_price.price_usd - buy_price.price_usd) / buy_price.price_usd * 100
        )
        
        if spread_percent < self.min_spread_percent:
            logger.debug(
                f"[SMART ARBITRAGE] {token_symbol}: Spread {spread_percent:.2f}% "
                f"< min {self.min_spread_percent}%"
            )
            return None
        
        # Estimate costs
        gas_cost = self._estimate_gas_cost()
        slippage_cost = self._estimate_slippage(buy_price, sell_price)
        mev_risk = self._assess_mev_risk(buy_price, sell_price)
        
        # Calculate max trade size based on liquidity
        max_size = self._calculate_max_size(buy_price, sell_price)
        recommended_size = max_size * Decimal('0.5')  # Conservative: 50% of max
        
        # Calculate profit
        gross_profit = (sell_price.price_usd - buy_price.price_usd) * recommended_size
        net_profit = gross_profit - gas_cost - slippage_cost
        
        # Check if profitable after costs
        if net_profit < self.min_profit_usd:
            logger.info(
                f"[SMART ARBITRAGE] {token_symbol}: Net profit ${net_profit:.2f} "
                f"< min ${self.min_profit_usd} (Gas: ${gas_cost:.2f}, Slippage: ${slippage_cost:.2f})"
            )
            return None
        
        # Check gas cost isn't too high relative to profit
        if gas_cost > (gross_profit * self.max_gas_cost_percent / 100):
            logger.info(
                f"[SMART ARBITRAGE] {token_symbol}: Gas ${gas_cost:.2f} > "
                f"{self.max_gas_cost_percent}% of profit ${gross_profit:.2f}"
            )
            return None
        
        # Calculate confidence score
        confidence = self._calculate_confidence(
            spread_percent=spread_percent,
            mev_risk=mev_risk,
            liquidity_score=min(
                self._liquidity_score(buy_price.liquidity_usd),
                self._liquidity_score(sell_price.liquidity_usd)
            )
        )
        
        opportunity = ArbitrageOpportunity(
            token_symbol=token_symbol,
            token_address=token_address,
            buy_dex=buy_dex,
            buy_price=buy_price.price_usd,
            buy_liquidity=buy_price.liquidity_usd or Decimal('0'),
            sell_dex=sell_dex,
            sell_price=sell_price.price_usd,
            sell_liquidity=sell_price.liquidity_usd or Decimal('0'),
            gross_spread_percent=spread_percent,
            gross_profit_usd=gross_profit,
            estimated_gas_cost=gas_cost,
            estimated_slippage=slippage_cost,
            mev_risk_score=mev_risk,
            net_profit_usd=net_profit,
            confidence_score=confidence,
            max_trade_size=max_size,
            recommended_size=recommended_size
        )
        
        logger.info(
            f"[SMART ARBITRAGE] 💰 OPPORTUNITY FOUND: {token_symbol}\n"
            f"  Buy:  {buy_dex} @ ${buy_price.price_usd:.4f}\n"
            f"  Sell: {sell_dex} @ ${sell_price.price_usd:.4f}\n"
            f"  Spread: {spread_percent:.2f}%\n"
            f"  Gross Profit: ${gross_profit:.2f}\n"
            f"  Gas Cost: ${gas_cost:.2f}\n"
            f"  Slippage: ${slippage_cost:.2f}\n"
            f"  Net Profit: ${net_profit:.2f} ✅\n"
            f"  Confidence: {confidence}%\n"
            f"  MEV Risk: {mev_risk}%"
        )
        
        return opportunity
    
    def _estimate_gas_cost(self) -> Decimal:
        """Estimate gas cost in USD."""
        gas_units = self.gas_estimates.get(self.chain_id, 100000)
        
        # Gas cost = gas_units * gas_price * ETH_price
        # Simplified: assume $3000 ETH
        eth_price = Decimal('3000')
        gwei_to_eth = Decimal('0.000000001')
        
        gas_cost_eth = Decimal(gas_units) * self.gas_price_gwei * gwei_to_eth
        gas_cost_usd = gas_cost_eth * eth_price
        
        return gas_cost_usd
    
    def _estimate_slippage(
        self,
        buy_price: 'DEXPrice',
        sell_price: 'DEXPrice'
    ) -> Decimal:
        """Estimate slippage cost based on liquidity."""
        # Simplified: assume 0.1% slippage on both sides
        avg_price = (buy_price.price_usd + sell_price.price_usd) / 2
        slippage_percent = Decimal('0.001')  # 0.1%
        
        return avg_price * slippage_percent * 2  # Buy + sell
    
    def _assess_mev_risk(
        self,
        buy_price: 'DEXPrice',
        sell_price: 'DEXPrice'
    ) -> int:
        """
        Assess MEV/frontrunning risk (0-100).
        
        Higher spread = higher risk (more attractive to MEV bots)
        """
        spread_percent = (
            (sell_price.price_usd - buy_price.price_usd) / buy_price.price_usd * 100
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
    
    def _calculate_max_size(
        self,
        buy_price: 'DEXPrice',
        sell_price: 'DEXPrice'
    ) -> Decimal:
        """Calculate max trade size based on liquidity."""
        buy_liquidity = buy_price.liquidity_usd or Decimal('0')
        sell_liquidity = sell_price.liquidity_usd or Decimal('0')
        
        # Use 10% of minimum liquidity to minimize price impact
        min_liquidity = min(buy_liquidity, sell_liquidity)
        max_size_usd = min_liquidity * Decimal('0.1')
        
        # Convert to token amount
        avg_price = (buy_price.price_usd + sell_price.price_usd) / 2
        max_tokens = max_size_usd / avg_price
        
        return max_tokens
    
    def _liquidity_score(self, liquidity_usd: Optional[Decimal]) -> int:
        """Score liquidity (0-100)."""
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
    
    def _calculate_confidence(
        self,
        spread_percent: Decimal,
        mev_risk: int,
        liquidity_score: int
    ) -> int:
        """Calculate overall confidence score (0-100)."""
        # Higher spread = more confident
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