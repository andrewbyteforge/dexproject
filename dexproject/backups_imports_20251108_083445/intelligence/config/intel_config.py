"""
Intelligence Level Configurations for Paper Trading Bot

This module defines the configuration settings for each intelligence level (1-10),
controlling risk tolerance, position sizing, and trading behavior.

File: dexproject/paper_trading/intelligence/intel_config.py
"""

from decimal import Decimal
from dataclasses import dataclass
from typing import Dict


@dataclass
class IntelLevelConfig:
    """
    Configuration for each intelligence level.
    
    Attributes:
        level: Intelligence level (1-10)
        name: Human-readable name for this level
        description: Description of trading behavior
        risk_tolerance: Risk tolerance percentage (0-100)
        max_position_percent: Maximum position size as % of portfolio
        min_confidence_required: Minimum confidence required to trade (0-100)
        min_position_usd: Minimum position size in USD
        use_mev_protection: Whether to use MEV protection
        gas_aggressiveness: Gas strategy ('minimal', 'low', 'standard', 'aggressive', 'ultra_aggressive')
        trade_frequency: How often to trade ('very_low', 'low', 'moderate', 'high', 'very_high')
        decision_speed: Decision making speed ('slow', 'moderate', 'fast')
    """
    
    level: int
    name: str
    description: str
    risk_tolerance: Decimal
    max_position_percent: Decimal
    min_confidence_required: Decimal
    min_position_usd: Decimal = Decimal('10')
    use_mev_protection: bool = True
    gas_aggressiveness: str = "standard"
    trade_frequency: str = "moderate"
    decision_speed: str = "moderate"


# Intelligence level configurations (1-10)
INTEL_CONFIGS: Dict[int, IntelLevelConfig] = {
    1: IntelLevelConfig(
        level=1,
        name="Ultra Cautious - Maximum Safety",
        description="Extreme caution, misses opportunities for safety",
        risk_tolerance=Decimal('20'),
        max_position_percent=Decimal('2'),
        min_confidence_required=Decimal('95'),
        min_position_usd=Decimal('10'),
        use_mev_protection=True,
        gas_aggressiveness="minimal",
        trade_frequency="very_low",
        decision_speed="slow"
    ),
    2: IntelLevelConfig(
        level=2,
        name="Very Cautious - High Safety",
        description="Very conservative, only obvious opportunities",
        risk_tolerance=Decimal('25'),
        max_position_percent=Decimal('3'),
        min_confidence_required=Decimal('90'),
        min_position_usd=Decimal('20'),
        use_mev_protection=True,
        gas_aggressiveness="low",
        trade_frequency="low",
        decision_speed="slow"
    ),
    3: IntelLevelConfig(
        level=3,
        name="Cautious - Safety First",
        description="Conservative approach with careful risk management",
        risk_tolerance=Decimal('30'),
        max_position_percent=Decimal('5'),
        min_confidence_required=Decimal('85'),
        min_position_usd=Decimal('30'),
        use_mev_protection=True,
        gas_aggressiveness="standard",
        trade_frequency="low",
        decision_speed="moderate"
    ),
    4: IntelLevelConfig(
        level=4,
        name="Moderately Cautious",
        description="Balanced with slight bias toward safety",
        risk_tolerance=Decimal('40'),
        max_position_percent=Decimal('7'),
        min_confidence_required=Decimal('75'),
        min_position_usd=Decimal('50'),
        use_mev_protection=True,
        gas_aggressiveness="standard",
        trade_frequency="moderate",
        decision_speed="moderate"
    ),
    5: IntelLevelConfig(
        level=5,
        name="Balanced - Default",
        description="Optimal balance of risk and reward",
        risk_tolerance=Decimal('50'),
        max_position_percent=Decimal('10'),
        min_confidence_required=Decimal('70'),
        min_position_usd=Decimal('75'),
        use_mev_protection=True,
        gas_aggressiveness="standard",
        trade_frequency="moderate",
        decision_speed="moderate"
    ),
    6: IntelLevelConfig(
        level=6,
        name="Moderately Aggressive",
        description="Balanced with slight bias toward opportunity",
        risk_tolerance=Decimal('60'),
        max_position_percent=Decimal('12'),
        min_confidence_required=Decimal('65'),
        min_position_usd=Decimal('100'),
        use_mev_protection=True,
        gas_aggressiveness="aggressive",
        trade_frequency="moderate",
        decision_speed="fast"
    ),
    7: IntelLevelConfig(
        level=7,
        name="Aggressive",
        description="Prioritizes opportunities, accepts higher risk",
        risk_tolerance=Decimal('70'),
        max_position_percent=Decimal('15'),
        min_confidence_required=Decimal('60'),
        min_position_usd=Decimal('150'),
        use_mev_protection=True,
        gas_aggressiveness="aggressive",
        trade_frequency="high",
        decision_speed="fast"
    ),
    8: IntelLevelConfig(
        level=8,
        name="Very Aggressive",
        description="High risk tolerance for maximum returns",
        risk_tolerance=Decimal('80'),
        max_position_percent=Decimal('18'),
        min_confidence_required=Decimal('55'),
        min_position_usd=Decimal('200'),
        use_mev_protection=False,
        gas_aggressiveness="ultra_aggressive",
        trade_frequency="high",
        decision_speed="fast"
    ),
    9: IntelLevelConfig(
        level=9,
        name="Ultra Aggressive",
        description="Maximum aggression, minimal hesitation",
        risk_tolerance=Decimal('90'),
        max_position_percent=Decimal('20'),
        min_confidence_required=Decimal('50'),
        min_position_usd=Decimal('250'),
        use_mev_protection=False,
        gas_aggressiveness="ultra_aggressive",
        trade_frequency="very_high",
        decision_speed="fast"
    ),
    10: IntelLevelConfig(
        level=10,
        name="Autonomous AI",
        description="Full AI control with machine learning optimization",
        risk_tolerance=Decimal('100'),
        max_position_percent=Decimal('25'),
        min_confidence_required=Decimal('45'),
        min_position_usd=Decimal('300'),
        use_mev_protection=False,
        gas_aggressiveness="ultra_aggressive",
        trade_frequency="very_high",
        decision_speed="fast"
    )
}