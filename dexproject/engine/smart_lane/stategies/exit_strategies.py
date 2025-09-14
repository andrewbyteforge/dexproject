"""
Smart Lane Exit Strategy Manager

Advanced exit strategy system that creates comprehensive exit plans
based on risk analysis, technical levels, and market conditions.
Provides multiple exit scenarios and dynamic adjustment capabilities.

Path: engine/smart_lane/strategy/exit_strategies.py
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone, timedelta

from .. import TechnicalSignal

logger = logging.getLogger(__name__)


class ExitTrigger(Enum):
    """Types of exit triggers."""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_BASED = "TIME_BASED"
    RISK_CHANGE = "RISK_CHANGE"
    TECHNICAL_REVERSAL = "TECHNICAL_REVERSAL"
    VOLUME_DECLINE = "VOLUME_DECLINE"
    MARKET_STRUCTURE_BREAK = "MARKET_STRUCTURE_BREAK"


class ExitMethod(Enum):
    """Exit execution methods."""
    MARKET_ORDER = "MARKET_ORDER"
    LIMIT_ORDER = "LIMIT_ORDER"
    SCALED_EXIT = "SCALED_EXIT"
    CONDITIONAL_ORDER = "CONDITIONAL_ORDER"


@dataclass
class ExitLevel:
    """Individual exit level definition."""
    trigger_type: ExitTrigger
    trigger_price_percent: float  # Percentage from entry
    position_percent: float       # Percentage of position to exit
    execution_method: ExitMethod
    priority: int                 # 1=highest priority
    conditions: Dict[str, Any]    # Additional conditions
    description: str


@dataclass
class ExitStrategy:
    """Complete exit strategy definition."""
    strategy_name: str
    exit_levels: List[ExitLevel]
    max_hold_time_hours: Optional[int]
    stop_loss_percent: Optional[float]
    take_profit_targets: List[float]
    trailing_stop_config: Dict[str, Any]
    emergency_exit_conditions: List[Dict[str, Any]]
    strategy_rationale: str
    risk_management_notes: List[str]


class ExitStrategyManager:
    """
    Advanced exit strategy manager for Smart Lane trades.
    
    Creates comprehensive exit plans with multiple scenarios,
    technical level integration, and dynamic risk adjustment.
    """
    
    def __init__(self, config: Any):
        """
        Initialize exit strategy manager.
        
        Args:
            config: Smart Lane configuration object
        """
        self.config = config
        
        # Default exit parameters
        self.default_stop_loss_percent = 15.0  # 15% stop loss
        self.default_take_profit_percent = 25.0  # 25% take profit
        self.default_max_hold_hours = 72  # 3 days max hold
        
        # Risk-based adjustments
        self.risk_adjustments = {
            'stop_loss_multipliers': {
                'LOW': 0.7,      # Tighter stops for low risk
                'MEDIUM': 1.0,   # Default stops
                'HIGH': 1.3,     # Wider stops for high risk
                'CRITICAL': 1.5  # Very wide stops
            },
            'take_profit_multipliers': {
                'LOW': 1.5,      # Higher targets for low risk
                'MEDIUM': 1.0,   # Default targets
                'HIGH': 0.8,     # Lower targets for high risk
                'CRITICAL': 0.6  # Conservative targets
            },
            'hold_time_multipliers': {
                'LOW': 1.5,      # Longer hold for low risk
                'MEDIUM': 1.0,   # Default hold time
                'HIGH': 0.7,     # Shorter hold for high risk
                'CRITICAL': 0.5  # Very short hold
            }
        }
        
        logger.info("Exit strategy manager initialized")
    
    def create_exit_strategy(
        self,
        risk_score: float,
        technical_signals: List[TechnicalSignal],
        market_conditions: Dict[str, Any],
        position_context: Dict[str, Any]
    ) -> ExitStrategy:
        """
        Create comprehensive exit strategy based on analysis.
        
        Args:
            risk_score: Overall risk score (0-1)
            technical_signals: Technical analysis signals
            market_conditions: Current market conditions
            position_context: Position-specific context
            
        Returns:
            Complete exit strategy with multiple levels
        """
        try:
            logger.debug("Creating exit strategy...")
            
            # Categorize risk level
            risk_category = self._categorize_risk(risk_score)
            
            # Extract technical levels
            technical_levels = self._extract_technical_levels(technical_signals)
            
            # Generate stop loss configuration
            stop_loss_config = self._generate_stop_loss_config(
                risk_score, technical_levels, market_conditions
            )
            
            # Generate take profit targets
            take_profit_config = self._generate_take_profit_targets(
                risk_score, technical_levels, market_conditions
            )
            
            # Generate trailing stop configuration
            trailing_stop_config = self._generate_trailing_stop_config(
                risk_score, technical_levels
            )
            
            # Determine maximum hold time
            max_hold_hours = self._calculate_max_hold_time(risk_score, market_conditions)
            
            # Create exit levels
            exit_levels = self._create_exit_levels(
                stop_loss_config, take_profit_config, trailing_stop_config
            )
            
            # Generate emergency exit conditions
            emergency_conditions = self._generate_emergency_conditions(
                risk_score, market_conditions
            )
            
            # Create strategy rationale
            strategy_rationale = self._generate_strategy_rationale(
                risk_category, technical_levels, market_conditions
            )
            
            # Generate risk management notes
            risk_notes = self._generate_risk_notes(
                risk_score, technical_signals, market_conditions
            )
            
            strategy = ExitStrategy(
                strategy_name=f"Smart Lane Exit - {risk_category} Risk",
                exit_levels=exit_levels,
                max_hold_time_hours=max_hold_hours,
                stop_loss_percent=stop_loss_config['stop_loss_percent'],
                take_profit_targets=take_profit_config['targets'],
                trailing_stop_config=trailing_stop_config,
                emergency_exit_conditions=emergency_conditions,
                strategy_rationale=strategy_rationale,
                risk_management_notes=risk_notes
            )
            
            logger.info(f"Exit strategy created: {strategy.strategy_name}")
            return strategy
            
        except Exception as e:
            logger.error(f"Error creating exit strategy: {e}", exc_info=True)
            return self._create_default_exit_strategy(risk_score)
    
    def _categorize_risk(self, risk_score: float) -> str:
        """Categorize risk score into risk levels."""
        if risk_score < 0.25:
            return 'LOW'
        elif risk_score < 0.5:
            return 'MEDIUM'
        elif risk_score < 0.75:
            return 'HIGH'
        else:
            return 'CRITICAL'
    
    def _extract_technical_levels(self, technical_signals: List[TechnicalSignal]) -> Dict[str, Any]:
        """Extract key technical levels from signals."""
        support_levels = []
        resistance_levels = []
        trend_direction = 'NEUTRAL'
        
        for signal in technical_signals:
            # Extract support and resistance from price targets
            if 'support' in signal.price_targets:
                support_levels.append(signal.price_targets['support'])
            if 'resistance' in signal.price_targets:
                resistance_levels.append(signal.price_targets['resistance'])
            
            # Determine overall trend
            if signal.signal == 'BUY' and signal.strength > 0.6:
                trend_direction = 'BULLISH'
            elif signal.signal == 'SELL' and signal.strength > 0.6:
                trend_direction = 'BEARISH'
        
        return {
            'support_levels': sorted(set(support_levels)),
            'resistance_levels': sorted(set(resistance_levels)),
            'trend_direction': trend_direction
        }
    
    def _generate_stop_loss_config(
        self,
        risk_score: float,
        technical_levels: Dict[str, Any],
        market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate stop loss configuration."""
        risk_category = self._categorize_risk(risk_score)
        
        # Base stop loss from risk category
        base_stop_percent = self.default_stop_loss_percent
        risk_multiplier = self.risk_adjustments['stop_loss_multipliers'][risk_category]
        
        # Adjust for technical support levels
        technical_stop = None
        if technical_levels['support_levels']:
            # Use nearest support level as technical stop
            current_price = market_conditions.get('current_price', 1.0)
            nearest_support = max([s for s in technical_levels['support_levels'] if s < current_price], default=None)
            
            if nearest_support:
                technical_stop_percent = (current_price - nearest_support) / current_price * 100
                if 5 <= technical_stop_percent <= 25:  # Reasonable range
                    technical_stop = technical_stop_percent
        
        # Choose between calculated and technical stop
        if technical_stop:
            # Blend calculated and technical stops
            calculated_stop = base_stop_percent * risk_multiplier
            final_stop = (calculated_stop * 0.6) + (technical_stop * 0.4)
        else:
            final_stop = base_stop_percent * risk_multiplier
        
        # Adjust for volatility
        volatility = market_conditions.get('volatility', 0.1)
        if volatility > 0.2:  # High volatility
            final_stop *= 1.2
        elif volatility < 0.05:  # Low volatility
            final_stop *= 0.8
        
        return {
            'stop_loss_percent': max(5.0, min(final_stop, 30.0)),  # 5-30% range
            'technical_stop': technical_stop,
            'volatility_adjusted': volatility > 0.1,
            'method': 'TECHNICAL_BLEND' if technical_stop else 'CALCULATED'
        }
    
    def _generate_take_profit_targets(
        self,
        risk_score: float,
        technical_levels: Dict[str, Any],
        market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate take profit target levels."""
        risk_category = self._categorize_risk(risk_score)
        
        # Base take profit from risk category
        base_tp_percent = self.default_take_profit_percent
        risk_multiplier = self.risk_adjustments['take_profit_multipliers'][risk_category]
        
        # Generate multiple take profit targets
        target_1 = base_tp_percent * risk_multiplier * 0.5   # First target at 50% of full target
        target_2 = base_tp_percent * risk_multiplier * 0.8   # Second target at 80%
        target_3 = base_tp_percent * risk_multiplier * 1.2   # Third target at 120%
        
        # Adjust for technical resistance levels
        if technical_levels['resistance_levels']:
            # Use technical resistance as targets if available
            resistance_targets = []
            current_price = market_conditions.get('current_price', 1.0)
            
            for resistance in technical_levels['resistance_levels'][:3]:  # Use top 3
                resistance_percent = (resistance - current_price) / current_price * 100
                if resistance_percent > 5.0:  # Must be at least 5% upside
                    resistance_targets.append(resistance_percent)
            
            if resistance_targets:
                # Blend technical and calculated targets
                blended_targets = []
                calc_targets = [target_1, target_2, target_3]
                
                for i in range(min(len(calc_targets), len(resistance_targets))):
                    # Weight 60% calculated, 40% technical
                    blended = (calc_targets[i] * 0.6) + (resistance_targets[i] * 0.4)
                    blended_targets.append(blended)
                
                # Add any remaining calculated targets
                if len(calc_targets) > len(resistance_targets):
                    blended_targets.extend(calc_targets[len(resistance_targets):])
                
                final_targets = blended_targets
            else:
                final_targets = [target_1, target_2, target_3]
        else:
            final_targets = [target_1, target_2, target_3]
        
        # Ensure targets are reasonable and ascending
        final_targets = [max(5.0, target) for target in final_targets]  # Min 5% profit
        final_targets = sorted(list(set(final_targets)))  # Remove duplicates and sort
        
        return {
            'targets': final_targets[:4],  # Maximum 4 targets
            'base_target': base_tp_percent,
            'risk_adjustment': risk_multiplier,
            'technical_influenced': len(technical_levels['resistance_levels']) > 0
        }
    
    def _generate_trailing_stop_config(
        self,
        risk_score: float,
        technical_levels: Dict[str, float]
    ) -> Dict[str, Any]:
        """Generate trailing stop configuration."""
        risk_category = self._categorize_risk(risk_score)
        
        # Base trailing stop parameters
        base_trail_percent = 8.0  # 8% trailing distance
        activation_profit = 15.0  # Activate after 15% profit
        
        # Adjust for risk
        if risk_category == 'LOW':
            trail_percent = base_trail_percent * 0.8
            activation_profit *= 0.7
        elif risk_category == 'HIGH':
            trail_percent = base_trail_percent * 1.3
            activation_profit *= 1.2
        elif risk_category == 'CRITICAL':
            trail_percent = base_trail_percent * 1.5
            activation_profit *= 1.5
        else:
            trail_percent = base_trail_percent
        
        return {
            'enabled': True,
            'trail_percent': trail_percent,
            'activation_profit_percent': activation_profit,
            'trail_method': 'PERCENTAGE',
            'update_frequency': 'REAL_TIME'
        }
    
    def _calculate_max_hold_time(
        self,
        risk_score: float,
        market_conditions: Dict[str, Any]
    ) -> int:
        """Calculate maximum hold time based on risk and conditions."""
        risk_category = self._categorize_risk(risk_score)
        
        base_hours = self.default_max_hold_hours
        risk_multiplier = self.risk_adjustments['hold_time_multipliers'][risk_category]
        
        # Adjust for market conditions
        volatility = market_conditions.get('volatility', 0.1)
        if volatility > 0.2:  # High volatility = shorter hold
            volatility_multiplier = 0.7
        elif volatility < 0.05:  # Low volatility = longer hold
            volatility_multiplier = 1.3
        else:
            volatility_multiplier = 1.0
        
        max_hours = int(base_hours * risk_multiplier * volatility_multiplier)
        return max(6, min(max_hours, 168))  # 6 hours to 1 week range
    
    def _create_exit_levels(
        self,
        stop_loss_config: Dict[str, Any],
        take_profit_config: Dict[str, Any],
        trailing_stop_config: Dict[str, Any]
    ) -> List[ExitLevel]:
        """Create individual exit levels."""
        exit_levels = []
        
        # Stop loss level
        exit_levels.append(ExitLevel(
            trigger_type=ExitTrigger.STOP_LOSS,
            trigger_price_percent=-stop_loss_config['stop_loss_percent'],
            position_percent=100.0,  # Exit entire position
            execution_method=ExitMethod.MARKET_ORDER,
            priority=1,  # Highest priority
            conditions={'method': stop_loss_config['method']},
            description=f"Stop loss at -{stop_loss_config['stop_loss_percent']:.1f}%"
        ))
        
        # Take profit levels
        for i, target in enumerate(take_profit_config['targets']):
            # Scale position size (25%, 50%, remaining)
            if i == 0:
                position_percent = 25.0
            elif i == 1:
                position_percent = 50.0
            else:
                position_percent = 100.0  # Remaining position
            
            exit_levels.append(ExitLevel(
                trigger_type=ExitTrigger.TAKE_PROFIT,
                trigger_price_percent=target,
                position_percent=position_percent,
                execution_method=ExitMethod.LIMIT_ORDER,
                priority=i + 2,
                conditions={'target_level': i + 1},
                description=f"Take profit {i+1} at +{target:.1f}% ({position_percent}% of position)"
            ))
        
        # Trailing stop level
        if trailing_stop_config['enabled']:
            exit_levels.append(ExitLevel(
                trigger_type=ExitTrigger.TRAILING_STOP,
                trigger_price_percent=trailing_stop_config['trail_percent'],
                position_percent=100.0,
                execution_method=ExitMethod.MARKET_ORDER,
                priority=10,
                conditions=trailing_stop_config,
                description=f"Trailing stop -{trailing_stop_config['trail_percent']:.1f}% after +{trailing_stop_config['activation_profit_percent']:.1f}% profit"
            ))
        
        return exit_levels
    
    def _generate_emergency_conditions(
        self,
        risk_score: float,
        market_conditions: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate emergency exit conditions."""
        conditions = []
        
        # Risk score escalation
        conditions.append({
            'condition_type': 'RISK_ESCALATION',
            'trigger': f'risk_score > {min(risk_score + 0.2, 0.95)}',
            'action': 'IMMEDIATE_EXIT',
            'description': 'Exit if risk score increases significantly'
        })
        
        # Volume collapse
        conditions.append({
            'condition_type': 'VOLUME_COLLAPSE',
            'trigger': 'volume_24h < 50% of average',
            'action': 'GRADUAL_EXIT',
            'description': 'Exit gradually if trading volume collapses'
        })
        
        # Technical breakdown
        conditions.append({
            'condition_type': 'TECHNICAL_BREAKDOWN',
            'trigger': 'break_below_key_support',
            'action': 'IMMEDIATE_EXIT',
            'description': 'Exit immediately if key support levels break'
        })
        
        # Time-based exit
        conditions.append({
            'condition_type': 'TIME_LIMIT',
            'trigger': 'max_hold_time_exceeded',
            'action': 'FORCED_EXIT',
            'description': 'Force exit when maximum hold time is reached'
        })
        
        return conditions
    
    def _generate_strategy_rationale(
        self,
        risk_category: str,
        technical_levels: Dict[str, Any],
        market_conditions: Dict[str, Any]
    ) -> str:
        """Generate human-readable strategy rationale."""
        rationale_parts = []
        
        # Risk-based rationale
        if risk_category == 'LOW':
            rationale_parts.append("Conservative exit strategy with wider targets due to low risk assessment")
        elif risk_category == 'HIGH':
            rationale_parts.append("Defensive exit strategy with tight stops due to elevated risk")
        elif risk_category == 'CRITICAL':
            rationale_parts.append("Ultra-defensive strategy with very tight controls due to critical risk level")
        else:
            rationale_parts.append("Balanced exit strategy appropriate for medium risk level")
        
        # Technical rationale
        if technical_levels['support_levels']:
            rationale_parts.append(f"Stop loss adjusted for {len(technical_levels['support_levels'])} technical support levels")
        
        if technical_levels['resistance_levels']:
            rationale_parts.append(f"Take profit targets aligned with {len(technical_levels['resistance_levels'])} resistance levels")
        
        # Market condition rationale
        volatility = market_conditions.get('volatility', 0.1)
        if volatility > 0.2:
            rationale_parts.append("Wider stops and shorter hold time due to high market volatility")
        elif volatility < 0.05:
            rationale_parts.append("Tighter management with longer hold potential in low volatility environment")
        
        return ". ".join(rationale_parts) + "."
    
    def _generate_risk_notes(
        self,
        risk_score: float,
        technical_signals: List[TechnicalSignal],
        market_conditions: Dict[str, Any]
    ) -> List[str]:
        """Generate risk management notes."""
        notes = []
        
        # Risk score notes
        if risk_score > 0.8:
            notes.append("CRITICAL RISK: Consider position sizing reduction or avoiding trade")
        elif risk_score > 0.6:
            notes.append("HIGH RISK: Use smaller position sizes and tight risk management")
        elif risk_score < 0.3:
            notes.append("LOW RISK: Suitable for larger position sizes with extended targets")
        
        # Technical signal notes
        bullish_signals = len([s for s in technical_signals if s.signal == 'BUY'])
        bearish_signals = len([s for s in technical_signals if s.signal == 'SELL'])
        
        if bearish_signals > bullish_signals:
            notes.append("Mixed technical signals: Monitor price action closely for exit triggers")
        elif bullish_signals > bearish_signals * 2:
            notes.append("Strong technical support: Consider holding through minor retracements")
        
        # Market condition notes
        volatility = market_conditions.get('volatility', 0.1)
        if volatility > 0.15:
            notes.append("High volatility environment: Expect wider price swings and adjust accordingly")
        
        # General risk management
        notes.append("Monitor position regularly and adjust exit levels based on evolving conditions")
        notes.append("Never risk more than planned maximum loss regardless of conviction level")
        
        return notes
    
    def _create_default_exit_strategy(self, risk_score: float) -> ExitStrategy:
        """Create a default exit strategy when normal creation fails."""
        risk_category = self._categorize_risk(risk_score)
        
        # Simple default exit levels
        default_levels = [
            ExitLevel(
                trigger_type=ExitTrigger.STOP_LOSS,
                trigger_price_percent=-15.0,
                position_percent=100.0,
                execution_method=ExitMethod.MARKET_ORDER,
                priority=1,
                conditions={},
                description="Default stop loss at -15%"
            ),
            ExitLevel(
                trigger_type=ExitTrigger.TAKE_PROFIT,
                trigger_price_percent=25.0,
                position_percent=100.0,
                execution_method=ExitMethod.LIMIT_ORDER,
                priority=2,
                conditions={},
                description="Default take profit at +25%"
            )
        ]
        
        return ExitStrategy(
            strategy_name=f"Default Exit Strategy - {risk_category} Risk",
            exit_levels=default_levels,
            max_hold_time_hours=48,
            stop_loss_percent=15.0,
            take_profit_targets=[25.0],
            trailing_stop_config={'enabled': False},
            emergency_exit_conditions=[],
            strategy_rationale="Default conservative exit strategy due to analysis error",
            risk_management_notes=["Using default parameters - review and adjust as needed"]
        )


# Export main class
__all__ = ['ExitStrategyManager', 'ExitStrategy', 'ExitLevel', 'ExitTrigger', 'ExitMethod']