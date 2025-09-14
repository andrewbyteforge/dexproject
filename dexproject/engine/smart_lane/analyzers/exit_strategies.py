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
            config: Smart Lane configuration
        """
        self.config = config
        
        # Default exit parameters
        self.default_stop_loss_percent = 8.0
        self.default_take_profit_percent = 20.0
        self.default_max_hold_hours = 72
        self.trailing_stop_activation = 15.0  # Activate trailing stop after 15% gain
        self.trailing_stop_distance = 8.0     # Trail 8% behind peak
        
        # Risk-based adjustments
        self.risk_adjustments = {
            'stop_loss_multipliers': {
                'low_risk': 1.2,      # Wider stops for low risk
                'medium_risk': 1.0,   # Normal stops
                'high_risk': 0.6,     # Tighter stops for high risk
                'critical_risk': 0.3  # Very tight stops
            },
            'take_profit_multipliers': {
                'low_risk': 1.5,      # Higher targets for low risk
                'medium_risk': 1.0,   # Normal targets
                'high_risk': 0.8,     # Lower targets for high risk
                'critical_risk': 0.5  # Conservative targets
            }
        }
        
        logger.info("Exit strategy manager initialized")
    
    async def generate_exit_strategy(
        self,
        risk_score: float,
        technical_signals: List[TechnicalSignal],
        position_size: float,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate comprehensive exit strategy.
        
        Args:
            risk_score: Overall risk score (0-1)
            technical_signals: Technical analysis signals
            position_size: Position size percentage
            context: Additional context for strategy generation
            
        Returns:
            Dictionary with exit strategy components
        """
        try:
            logger.debug(f"Generating exit strategy for risk_score={risk_score:.3f}")
            
            # Determine risk category
            risk_category = self._categorize_risk(risk_score)
            
            # Extract technical levels
            technical_levels = self._extract_technical_levels(technical_signals)
            
            # Generate stop loss strategy
            stop_loss_config = self._generate_stop_loss_strategy(
                risk_score, technical_levels, context
            )
            
            # Generate take profit strategy
            take_profit_config = self._generate_take_profit_strategy(
                risk_score, technical_levels, position_size, context
            )
            
            # Generate trailing stop configuration
            trailing_stop_config = self._generate_trailing_stop_config(
                risk_score, technical_levels
            )
            
            # Generate time-based exits
            time_based_config = self._generate_time_based_exits(
                risk_score, position_size
            )
            
            # Generate emergency exit conditions
            emergency_conditions = self._generate_emergency_conditions(
                risk_score, context
            )
            
            # Combine into comprehensive strategy
            exit_strategy = {
                'stop_loss_percent': stop_loss_config['percent'],
                'take_profit_targets': take_profit_config['targets'],
                'max_hold_time_hours': time_based_config['max_hours'],
                'trailing_stop': trailing_stop_config,
                'emergency_conditions': emergency_conditions,
                'exit_levels': self._create_exit_levels(
                    stop_loss_config, take_profit_config, trailing_stop_config
                ),
                'risk_category': risk_category,
                'technical_levels': technical_levels,
                'strategy_notes': self._generate_strategy_notes(
                    risk_score, technical_signals, position_size
                )
            }
            
            logger.debug(f"Exit strategy generated with {len(exit_strategy['exit_levels'])} exit levels")
            
            return exit_strategy
            
        except Exception as e:
            logger.error(f"Error generating exit strategy: {e}", exc_info=True)
            
            # Return conservative fallback strategy
            return self._create_fallback_strategy(risk_score)
    
    async def create_detailed_exit_strategy(
        self,
        risk_score: float,
        technical_signals: List[TechnicalSignal],
        position_size: float,
        context: Dict[str, Any]
    ) -> ExitStrategy:
        """
        Create detailed exit strategy object with full configuration.
        
        Args:
            risk_score: Overall risk score
            technical_signals: Technical analysis signals
            position_size: Position size percentage
            context: Additional context
            
        Returns:
            Detailed ExitStrategy object
        """
        try:
            # Generate base strategy
            base_strategy = await self.generate_exit_strategy(
                risk_score, technical_signals, position_size, context
            )
            
            # Create detailed exit levels
            exit_levels = self._create_detailed_exit_levels(base_strategy, technical_signals)
            
            # Generate comprehensive rationale
            rationale = self._create_strategy_rationale(
                risk_score, technical_signals, position_size, base_strategy
            )
            
            # Generate risk management notes
            risk_notes = self._create_risk_management_notes(
                risk_score, base_strategy, context
            )
            
            return ExitStrategy(
                strategy_name=f"Smart_Lane_Exit_{self._categorize_risk(risk_score)}",
                exit_levels=exit_levels,
                max_hold_time_hours=base_strategy['max_hold_time_hours'],
                stop_loss_percent=base_strategy['stop_loss_percent'],
                take_profit_targets=base_strategy['take_profit_targets'],
                trailing_stop_config=base_strategy['trailing_stop'],
                emergency_exit_conditions=base_strategy['emergency_conditions'],
                strategy_rationale=rationale,
                risk_management_notes=risk_notes
            )
            
        except Exception as e:
            logger.error(f"Error creating detailed exit strategy: {e}", exc_info=True)
            
            # Return minimal fallback strategy
            return self._create_minimal_exit_strategy(risk_score)
    
    def _categorize_risk(self, risk_score: float) -> str:
        """Categorize risk score into discrete levels."""
        if risk_score >= 0.8:
            return "critical_risk"
        elif risk_score >= 0.6:
            return "high_risk"
        elif risk_score >= 0.4:
            return "medium_risk"
        else:
            return "low_risk"
    
    def _extract_technical_levels(self, technical_signals: List[TechnicalSignal]) -> Dict[str, float]:
        """Extract key technical levels from signals."""
        levels = {
            'support_levels': [],
            'resistance_levels': [],
            'trend_line_support': None,
            'trend_line_resistance': None,
            'moving_average_support': None,
            'moving_average_resistance': None
        }
        
        for signal in technical_signals:
            if hasattr(signal, 'price_targets') and signal.price_targets:
                # Extract support and resistance levels
                for level_type, price in signal.price_targets.items():
                    if 'support' in level_type.lower():
                        levels['support_levels'].append(price)
                    elif 'resistance' in level_type.lower():
                        levels['resistance_levels'].append(price)
            
            # Extract other technical levels from indicators
            if hasattr(signal, 'indicators') and signal.indicators:
                indicators = signal.indicators
                
                # Moving average levels
                if 'ma_20' in indicators:
                    levels['moving_average_support'] = indicators['ma_20']
                if 'ma_50' in indicators:
                    levels['moving_average_resistance'] = indicators['ma_50']
                
                # Trend line levels
                if 'trend_support' in indicators:
                    levels['trend_line_support'] = indicators['trend_support']
                if 'trend_resistance' in indicators:
                    levels['trend_line_resistance'] = indicators['trend_resistance']
        
        # Clean up and sort levels
        levels['support_levels'] = sorted(list(set(levels['support_levels'])), reverse=True)
        levels['resistance_levels'] = sorted(list(set(levels['resistance_levels'])))
        
        return levels
    
    def _generate_stop_loss_strategy(
        self,
        risk_score: float,
        technical_levels: Dict[str, float],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate stop loss strategy based on risk and technical levels."""
        risk_category = self._categorize_risk(risk_score)
        
        # Base stop loss from risk category
        base_stop_percent = self.default_stop_loss_percent
        risk_multiplier = self.risk_adjustments['stop_loss_multipliers'][risk_category]
        adjusted_stop = base_stop_percent * risk_multiplier
        
        # Adjust for technical levels
        if technical_levels['support_levels']:
            # Use closest support level if it's reasonable
            closest_support = max(technical_levels['support_levels'])
            technical_stop_percent = (1.0 - closest_support) * 100
            
            # Use technical stop if it's within reasonable range of risk-based stop
            if 0.5 <= technical_stop_percent <= (adjusted_stop * 2):
                final_stop = technical_stop_percent
                stop_type = "technical_support"
            else:
                final_stop = adjusted_stop
                stop_type = "risk_based"
        else:
            final_stop = adjusted_stop
            stop_type = "risk_based"
        
        # Ensure stop loss is within reasonable bounds
        min_stop = 2.0  # Minimum 2% stop loss
        max_stop = 25.0 if risk_category == "critical_risk" else 15.0  # Maximum stop loss
        
        final_stop = max(min_stop, min(max_stop, final_stop))
        
        return {
            'percent': final_stop,
            'type': stop_type,
            'base_percent': base_stop_percent,
            'risk_adjustment': risk_multiplier,
            'technical_adjustment': stop_type == "technical_support"
        }
    
    def _generate_take_profit_strategy(
        self,
        risk_score: float,
        technical_levels: Dict[str, float],
        position_size: float,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate take profit strategy with multiple targets."""
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
            for resistance in technical_levels['resistance_levels'][:3]:  # Use top 3
                resistance_percent = (resistance - 1.0) * 100
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
        
        # Adjust trailing stop parameters based on risk
        if risk_category == "critical_risk":
            activation_percent = 8.0   # Activate earlier
            trail_distance = 12.0      # Trail further away
        elif risk_category == "high_risk":
            activation_percent = 10.0
            trail_distance = 10.0
        elif risk_category == "medium_risk":
            activation_percent = self.trailing_stop_activation
            trail_distance = self.trailing_stop_distance
        else:  # low_risk
            activation_percent = 20.0  # Let it run more
            trail_distance = 6.0       # Trail closer
        
        return {
            'enabled': True,
            'activation_percent': activation_percent,
            'trail_distance_percent': trail_distance,
            'step_size_percent': 1.0,  # Adjust in 1% increments
            'min_profit_lock': 5.0     # Always lock in at least 5% profit
        }
    
    def _generate_time_based_exits(
        self,
        risk_score: float,
        position_size: float
    ) -> Dict[str, Any]:
        """Generate time-based exit conditions."""
        risk_category = self._categorize_risk(risk_score)
        
        # Adjust max hold time based on risk
        if risk_category == "critical_risk":
            max_hours = 12  # Exit quickly for high-risk trades
        elif risk_category == "high_risk":
            max_hours = 24
        elif risk_category == "medium_risk":
            max_hours = self.default_max_hold_hours
        else:  # low_risk
            max_hours = 168  # 1 week for low-risk trades
        
        # Adjust for position size (larger positions = shorter holds)
        if position_size > 5.0:
            max_hours = int(max_hours * 0.8)
        elif position_size > 8.0:
            max_hours = int(max_hours * 0.6)
        
        return {
            'max_hours': max_hours,
            'partial_exit_hours': max_hours // 2,  # Partial exit at halfway point
            'review_intervals_hours': [max_hours // 4, max_hours // 2, int(max_hours * 0.75)]
        }
    
    def _generate_emergency_conditions(
        self,
        risk_score: float,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate emergency exit conditions."""
        conditions = []
        
        # Market structure break condition
        conditions.append({
            'trigger': ExitTrigger.MARKET_STRUCTURE_BREAK.value,
            'description': 'Exit if market structure breaks down',
            'conditions': {
                'volume_drop_percent': 70,  # 70% volume drop
                'price_drop_percent': 20,   # 20% price drop in short time
                'time_window_minutes': 30
            },
            'exit_percent': 100,  # Full exit
            'priority': 1
        })
        
        # Risk escalation condition
        if risk_score < 0.8:  # Only for non-critical risk trades
            conditions.append({
                'trigger': ExitTrigger.RISK_CHANGE.value,
                'description': 'Exit if risk profile deteriorates significantly',
                'conditions': {
                    'risk_increase_threshold': 0.3,  # Risk increases by 0.3
                    'new_risk_minimum': 0.8          # Or new risk > 0.8
                },
                'exit_percent': 50,  # Partial exit first
                'priority': 2
            })
        
        # Technical reversal condition
        conditions.append({
            'trigger': ExitTrigger.TECHNICAL_REVERSAL.value,
            'description': 'Exit on strong technical reversal signals',
            'conditions': {
                'reversal_strength_threshold': 0.8,
                'timeframes_confirming': 2,  # At least 2 timeframes
                'rsi_oversold_overbought': True
            },
            'exit_percent': 75,  # Mostly exit
            'priority': 3
        })
        
        return conditions
    
    def _create_exit_levels(
        self,
        stop_loss_config: Dict[str, Any],
        take_profit_config: Dict[str, Any],
        trailing_stop_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Create detailed exit level specifications."""
        exit_levels = []
        
        # Stop loss level
        exit_levels.append({
            'type': ExitTrigger.STOP_LOSS.value,
            'price_percent': -stop_loss_config['percent'],  # Negative for loss
            'position_percent': 100,  # Full exit
            'method': ExitMethod.MARKET_ORDER.value,
            'priority': 1,
            'description': f"Stop loss at -{stop_loss_config['percent']:.1f}%"
        })
        
        # Take profit levels
        for i, target in enumerate(take_profit_config['targets']):
            exit_levels.append({
                'type': ExitTrigger.TAKE_PROFIT.value,
                'price_percent': target,
                'position_percent': 33 if len(take_profit_config['targets']) > 1 else 100,
                'method': ExitMethod.LIMIT_ORDER.value,
                'priority': i + 2,
                'description': f"Take profit {i+1} at +{target:.1f}%"
            })
        
        # Trailing stop level
        if trailing_stop_config['enabled']:
            exit_levels.append({
                'type': ExitTrigger.TRAILING_STOP.value,
                'price_percent': trailing_stop_config['activation_percent'],
                'position_percent': 100,  # Full remaining position
                'method': ExitMethod.CONDITIONAL_ORDER.value,
                'priority': 10,
                'description': f"Trailing stop activates at +{trailing_stop_config['activation_percent']:.1f}%",
                'trail_distance': trailing_stop_config['trail_distance_percent']
            })
        
        return exit_levels
    
    def _create_detailed_exit_levels(
        self,
        base_strategy: Dict[str, Any],
        technical_signals: List[TechnicalSignal]
    ) -> List[ExitLevel]:
        """Create detailed ExitLevel objects."""
        exit_levels = []
        
        # Stop loss
        exit_levels.append(
            ExitLevel(
                trigger_type=ExitTrigger.STOP_LOSS,
                trigger_price_percent=-base_strategy['stop_loss_percent'],
                position_percent=100,
                execution_method=ExitMethod.MARKET_ORDER,
                priority=1,
                conditions={},
                description=f"Stop loss at -{base_strategy['stop_loss_percent']:.1f}%"
            )
        )
        
        # Take profit levels
        targets = base_strategy['take_profit_targets']
        position_per_target = 100 // len(targets) if targets else 100
        
        for i, target in enumerate(targets):
            exit_levels.append(
                ExitLevel(
                    trigger_type=ExitTrigger.TAKE_PROFIT,
                    trigger_price_percent=target,
                    position_percent=position_per_target,
                    execution_method=ExitMethod.LIMIT_ORDER,
                    priority=i + 2,
                    conditions={},
                    description=f"Take profit {i+1} at +{target:.1f}%"
                )
            )
        
        # Trailing stop
        trailing_config = base_strategy['trailing_stop']
        if trailing_config['enabled']:
            exit_levels.append(
                ExitLevel(
                    trigger_type=ExitTrigger.TRAILING_STOP,
                    trigger_price_percent=trailing_config['activation_percent'],
                    position_percent=100,
                    execution_method=ExitMethod.CONDITIONAL_ORDER,
                    priority=10,
                    conditions={
                        'trail_distance': trailing_config['trail_distance_percent'],
                        'step_size': trailing_config['step_size_percent'],
                        'min_profit_lock': trailing_config['min_profit_lock']
                    },
                    description=f"Trailing stop (activate: +{trailing_config['activation_percent']:.1f}%, trail: {trailing_config['trail_distance_percent']:.1f}%)"
                )
            )
        
        # Time-based exit
        if base_strategy.get('max_hold_time_hours'):
            exit_levels.append(
                ExitLevel(
                    trigger_type=ExitTrigger.TIME_BASED,
                    trigger_price_percent=0,  # Any price
                    position_percent=100,
                    execution_method=ExitMethod.MARKET_ORDER,
                    priority=20,
                    conditions={
                        'max_hold_hours': base_strategy['max_hold_time_hours']
                    },
                    description=f"Time-based exit after {base_strategy['max_hold_time_hours']} hours"
                )
            )
        
        return exit_levels
    
    def _create_strategy_rationale(
        self,
        risk_score: float,
        technical_signals: List[TechnicalSignal],
        position_size: float,
        strategy: Dict[str, Any]
    ) -> str:
        """Create comprehensive strategy rationale."""
        risk_category = self._categorize_risk(risk_score)
        
        rationale = f"""
        Exit strategy designed for {risk_category.replace('_', ' ')} scenario with {position_size:.1f}% position size.
        
        Key Components:
        • Stop Loss: {strategy['stop_loss_percent']:.1f}% to limit downside risk
        • Take Profit: {len(strategy['take_profit_targets'])} targets at {', '.join([f'{t:.1f}%' for t in strategy['take_profit_targets']])}
        • Trailing Stop: {'Enabled' if strategy['trailing_stop']['enabled'] else 'Disabled'} for profit protection
        • Max Hold Time: {strategy['max_hold_time_hours']} hours to prevent indefinite exposure
        • Emergency Exits: {len(strategy['emergency_conditions'])} conditions for exceptional circumstances
        
        Risk Management Philosophy:
        The strategy prioritizes capital preservation while allowing for profit maximization.
        Multiple exit levels provide flexibility and reduce emotional decision-making.
        Technical levels are integrated where available to improve exit timing.
        
        Strategy adapts to risk level with {'tighter' if risk_category in ['high_risk', 'critical_risk'] else 'standard'} 
        stops and {'conservative' if risk_category in ['high_risk', 'critical_risk'] else 'moderate'} profit targets.
        """.strip()
        
        return rationale
    
    def _create_risk_management_notes(
        self,
        risk_score: float,
        strategy: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[str]:
        """Create risk management guidance notes."""
        notes = []
        risk_category = self._categorize_risk(risk_score)
        
        # Risk-specific notes
        if risk_category == "critical_risk":
            notes.append("CRITICAL RISK: Monitor position closely and be prepared for immediate exit")
            notes.append("Consider reducing position size further or avoiding trade entirely")
            notes.append("Use market orders for exits to ensure execution")
        elif risk_category == "high_risk":
            notes.append("HIGH RISK: Tight stop losses and conservative profit targets applied")
            notes.append("Monitor for any deterioration in risk factors")
            notes.append("Consider partial profit-taking early")
        elif risk_category == "medium_risk":
            notes.append("MEDIUM RISK: Balanced approach with standard risk management")
            notes.append("Allow strategy to run its course unless emergency conditions trigger")
        else:
            notes.append("LOW RISK: Can afford to let profits run with trailing stops")
            notes.append("Consider holding longer for maximum profit potential")
        
        # Strategy-specific notes
        if strategy['trailing_stop']['enabled']:
            notes.append(f"Trailing stop activates after {strategy['trailing_stop']['activation_percent']:.1f}% gain")
            notes.append("Trailing stop helps capture maximum profits while protecting gains")
        
        # Time-based notes
        if strategy['max_hold_time_hours'] <= 24:
            notes.append("Short holding period requires active monitoring")
        elif strategy['max_hold_time_hours'] >= 168:
            notes.append("Extended holding period allows for longer-term development")
        
        # Emergency condition notes
        if strategy['emergency_conditions']:
            notes.append("Emergency exit conditions are in place for exceptional circumstances")
            notes.append("Monitor market structure and risk factor changes")
        
        return notes
    
    def _generate_strategy_notes(
        self,
        risk_score: float,
        technical_signals: List[TechnicalSignal],
        position_size: float
    ) -> List[str]:
        """Generate general strategy implementation notes."""
        notes = []
        
        # Position size notes
        if position_size > 5.0:
            notes.append("Large position requires extra attention to exit execution")
        elif position_size < 1.0:
            notes.append("Small position allows for more aggressive exit strategy")
        
        # Technical integration notes
        if technical_signals:
            notes.append(f"Strategy incorporates {len(technical_signals)} technical timeframes")
            if any('support' in str(s.price_targets) for s in technical_signals if hasattr(s, 'price_targets')):
                notes.append("Technical support levels integrated into stop loss calculation")
        else:
            notes.append("No technical signals available - using risk-based exits only")
        
        # Risk-based notes
        risk_category = self._categorize_risk(risk_score)
        notes.append(f"Exit strategy calibrated for {risk_category.replace('_', ' ')} profile")
        
        return notes
    
    def _create_fallback_strategy(self, risk_score: float) -> Dict[str, Any]:
        """Create conservative fallback strategy for error cases."""
        risk_category = self._categorize_risk(risk_score)
        
        # Very conservative parameters
        if risk_category == "critical_risk":
            stop_loss = 5.0
            take_profit = 8.0
            max_hours = 6
        else:
            stop_loss = 8.0
            take_profit = 15.0
            max_hours = 24
        
        return {
            'stop_loss_percent': stop_loss,
            'take_profit_targets': [take_profit],
            'max_hold_time_hours': max_hours,
            'trailing_stop': {'enabled': False},
            'emergency_conditions': [],
            'exit_levels': [
                {
                    'type': 'STOP_LOSS',
                    'price_percent': -stop_loss,
                    'position_percent': 100,
                    'description': f'Fallback stop loss at -{stop_loss}%'
                }
            ],
            'strategy_notes': ['Fallback strategy due to calculation error']
        }
    
    def _create_minimal_exit_strategy(self, risk_score: float) -> ExitStrategy:
        """Create minimal exit strategy for error cases."""
        fallback = self._create_fallback_strategy(risk_score)
        
        return ExitStrategy(
            strategy_name="Fallback_Conservative",
            exit_levels=[],
            max_hold_time_hours=fallback['max_hold_time_hours'],
            stop_loss_percent=fallback['stop_loss_percent'],
            take_profit_targets=fallback['take_profit_targets'],
            trailing_stop_config=fallback['trailing_stop'],
            emergency_exit_conditions=[],
            strategy_rationale="Conservative fallback strategy due to calculation error",
            risk_management_notes=["Use conservative approach due to system error"]
        )


# Export key classes
__all__ = [
    'ExitStrategyManager',
    'ExitStrategy',
    'ExitLevel',
    'ExitTrigger',
    'ExitMethod'
]