"""
Smart Lane Exit Strategy Manager

Advanced exit strategy system that creates comprehensive exit plans
based on risk analysis, technical levels, and market conditions.
Includes stop-loss, take-profit, trailing stops, and time-based exits.

Path: engine/smart_lane/strategy/exit_strategies.py
"""

import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from . import ExitTrigger, ExitMethod, StrategyMetrics

logger = logging.getLogger(__name__)


@dataclass
class ExitLevel:
    """Individual exit level definition."""
    trigger_type: ExitTrigger
    trigger_price_percent: float  # Percent from entry price
    exit_size_percent: float      # Percent of position to exit
    execution_method: ExitMethod
    priority: int                 # 1 = highest priority
    conditions: Dict[str, Any]    # Additional trigger conditions
    description: str


@dataclass
class ExitStrategy:
    """Complete exit strategy definition."""
    strategy_name: str
    strategy_type: str  # CONSERVATIVE, MODERATE, AGGRESSIVE
    
    # Core exit levels
    exit_levels: List[ExitLevel]
    
    # Key parameters
    stop_loss_percent: Optional[float]
    take_profit_targets: List[float]  # Multiple TP levels
    trailing_stop_config: Optional[Dict[str, Any]]
    
    # Time-based exits
    max_hold_time_hours: Optional[int]
    time_decay_schedule: Optional[List[Dict[str, Any]]]
    
    # Emergency exits
    emergency_exit_conditions: List[Dict[str, Any]]
    circuit_breaker_config: Optional[Dict[str, Any]]
    
    # Strategy metadata
    expected_return: float
    risk_reward_ratio: float
    win_probability: float
    
    # Reasoning
    strategy_rationale: str
    risk_management_notes: List[str]
    optimization_suggestions: List[str]


class ExitStrategyManager:
    """
    Advanced exit strategy manager for Smart Lane trades.
    
    Creates comprehensive exit plans with multiple exit levels,
    risk management, and adaptive strategies based on market conditions.
    """
    
    def __init__(self, config: Any):
        """
        Initialize exit strategy manager.
        
        Args:
            config: Smart Lane configuration object
        """
        self.config = config
        
        # Default exit parameters
        self.default_stop_loss_percent = 15.0
        self.default_take_profit_percent = 30.0
        self.default_trailing_stop_percent = 10.0
        self.default_max_hold_hours = 168  # 1 week
        
        # Risk management thresholds
        self.max_loss_percent = 25.0           # Absolute maximum loss
        self.profit_lock_threshold = 20.0      # Lock in profits above this
        self.breakeven_move_threshold = 10.0   # Move stop to breakeven
        
        # Strategy type mappings
        self.strategy_types = {
            'CONSERVATIVE': {
                'stop_loss_mult': 0.7,    # Tighter stops
                'take_profit_mult': 0.8,   # Lower targets
                'trailing_start': 15.0,    # Start trailing earlier
                'position_scaling': True   # Scale out of positions
            },
            'MODERATE': {
                'stop_loss_mult': 1.0,
                'take_profit_mult': 1.0,
                'trailing_start': 20.0,
                'position_scaling': True
            },
            'AGGRESSIVE': {
                'stop_loss_mult': 1.3,     # Wider stops
                'take_profit_mult': 1.5,    # Higher targets
                'trailing_start': 30.0,     # Trail only after big moves
                'position_scaling': False   # All-or-nothing
            }
        }
        
        # Performance tracking
        self.strategy_stats = {
            'total_created': 0,
            'by_type': {'CONSERVATIVE': 0, 'MODERATE': 0, 'AGGRESSIVE': 0},
            'avg_risk_reward': 0,
            'avg_hold_time_hours': 0
        }
        
        logger.info("ExitStrategyManager initialized with default SL: "
                   f"{self.default_stop_loss_percent}%, TP: {self.default_take_profit_percent}%")
    
    def create_exit_strategy(
        self,
        risk_score: float,
        technical_signals: List[Any],
        market_conditions: Dict[str, Any],
        position_context: Dict[str, Any]
    ) -> ExitStrategy:
        """
        Create comprehensive exit strategy based on analysis.
        
        Args:
            risk_score: Overall risk assessment (0-1)
            technical_signals: Technical analysis signals
            market_conditions: Current market condition data
            position_context: Position entry context
            
        Returns:
            Complete exit strategy with multiple exit levels
        """
        logger.debug(f"Creating exit strategy for risk={risk_score:.2f}")
        
        # Determine strategy type based on risk and conditions
        strategy_type = self._determine_strategy_type(
            risk_score,
            market_conditions,
            position_context
        )
        
        # Get strategy parameters
        strategy_params = self.strategy_types[strategy_type]
        
        # Calculate base exit levels
        stop_loss = self._calculate_stop_loss(
            risk_score,
            technical_signals,
            strategy_params
        )
        
        take_profit_targets = self._calculate_take_profit_targets(
            risk_score,
            technical_signals,
            market_conditions,
            strategy_params
        )
        
        # Create exit levels
        exit_levels = self._create_exit_levels(
            stop_loss,
            take_profit_targets,
            technical_signals,
            strategy_type
        )
        
        # Configure trailing stop
        trailing_stop_config = self._configure_trailing_stop(
            risk_score,
            market_conditions,
            strategy_params
        )
        
        # Calculate time-based exits
        max_hold_time, time_decay = self._calculate_time_exits(
            risk_score,
            market_conditions,
            position_context
        )
        
        # Define emergency exit conditions
        emergency_conditions = self._define_emergency_conditions(
            risk_score,
            position_context
        )
        
        # Configure circuit breaker
        circuit_breaker = self._configure_circuit_breaker(
            risk_score,
            market_conditions
        )
        
        # Calculate expected metrics
        expected_return, risk_reward, win_prob = self._calculate_expected_metrics(
            stop_loss,
            take_profit_targets,
            risk_score,
            technical_signals
        )
        
        # Generate strategy rationale
        rationale = self._generate_strategy_rationale(
            strategy_type,
            risk_score,
            stop_loss,
            take_profit_targets
        )
        
        # Identify risk management notes
        risk_notes = self._generate_risk_notes(
            risk_score,
            stop_loss,
            market_conditions
        )
        
        # Generate optimization suggestions
        optimization_suggestions = self._generate_optimization_suggestions(
            strategy_type,
            risk_score,
            technical_signals,
            market_conditions
        )
        
        # Update statistics
        self._update_statistics(strategy_type, risk_reward, max_hold_time)
        
        # Create strategy name
        strategy_name = self._generate_strategy_name(strategy_type, risk_score)
        
        return ExitStrategy(
            strategy_name=strategy_name,
            strategy_type=strategy_type,
            exit_levels=exit_levels,
            stop_loss_percent=stop_loss,
            take_profit_targets=take_profit_targets,
            trailing_stop_config=trailing_stop_config,
            max_hold_time_hours=max_hold_time,
            time_decay_schedule=time_decay,
            emergency_exit_conditions=emergency_conditions,
            circuit_breaker_config=circuit_breaker,
            expected_return=expected_return,
            risk_reward_ratio=risk_reward,
            win_probability=win_prob,
            strategy_rationale=rationale,
            risk_management_notes=risk_notes,
            optimization_suggestions=optimization_suggestions
        )
    
    def _determine_strategy_type(
        self,
        risk_score: float,
        market_conditions: Dict[str, Any],
        position_context: Dict[str, Any]
    ) -> str:
        """Determine appropriate strategy type."""
        # High risk = Conservative strategy
        if risk_score > 0.7:
            return 'CONSERVATIVE'
        
        # High volatility = Conservative
        if market_conditions.get('volatility', 0) > 0.3:
            return 'CONSERVATIVE'
        
        # Large position = Conservative
        if position_context.get('position_size_percent', 0) > 7:
            return 'CONSERVATIVE'
        
        # Low risk + good conditions = Aggressive
        if risk_score < 0.3 and market_conditions.get('trend_strength', 0) > 0.6:
            return 'AGGRESSIVE'
        
        # Default to moderate
        return 'MODERATE'
    
    def _calculate_stop_loss(
        self,
        risk_score: float,
        technical_signals: List[Any],
        strategy_params: Dict[str, Any]
    ) -> float:
        """Calculate stop loss percentage."""
        # Base stop loss
        base_stop = self.default_stop_loss_percent
        
        # Adjust for risk
        risk_adjustment = 1 - (risk_score * 0.5)  # Tighter stops for higher risk
        base_stop *= risk_adjustment
        
        # Apply strategy multiplier
        base_stop *= strategy_params['stop_loss_mult']
        
        # Check technical levels
        technical_stop = self._find_technical_stop_level(technical_signals)
        if technical_stop:
            # Use technical level if it's reasonable
            if 5 <= technical_stop <= self.max_loss_percent:
                base_stop = technical_stop
        
        # Ensure within limits
        base_stop = max(5.0, min(base_stop, self.max_loss_percent))
        
        return round(base_stop, 2)
    
    def _calculate_take_profit_targets(
        self,
        risk_score: float,
        technical_signals: List[Any],
        market_conditions: Dict[str, Any],
        strategy_params: Dict[str, Any]
    ) -> List[float]:
        """Calculate multiple take profit targets."""
        targets = []
        
        # Base target
        base_target = self.default_take_profit_percent
        
        # Adjust for risk (lower targets for higher risk)
        risk_adjustment = 1 - (risk_score * 0.3)
        base_target *= risk_adjustment
        
        # Apply strategy multiplier
        base_target *= strategy_params['take_profit_mult']
        
        # Adjust for market conditions
        if market_conditions.get('trend_strength', 0) > 0.5:
            base_target *= 1.2  # Higher targets in strong trends
        
        # Create multiple targets
        if strategy_params.get('position_scaling', True):
            # Scale out strategy: 3 targets
            targets = [
                round(base_target * 0.5, 2),   # TP1: 50% of target
                round(base_target * 1.0, 2),   # TP2: Full target
                round(base_target * 1.5, 2)    # TP3: Stretch target
            ]
        else:
            # Single target strategy
            targets = [round(base_target, 2)]
        
        # Add technical resistance levels
        technical_targets = self._find_technical_target_levels(technical_signals)
        if technical_targets:
            # Merge with technical levels
            targets = self._merge_target_levels(targets, technical_targets)
        
        return sorted(targets)[:3]  # Maximum 3 targets
    
    def _create_exit_levels(
        self,
        stop_loss: float,
        take_profits: List[float],
        technical_signals: List[Any],
        strategy_type: str
    ) -> List[ExitLevel]:
        """Create detailed exit levels."""
        levels = []
        
        # Stop loss level
        levels.append(ExitLevel(
            trigger_type=ExitTrigger.STOP_LOSS,
            trigger_price_percent=-stop_loss,
            exit_size_percent=100.0,
            execution_method=ExitMethod.MARKET_ORDER,
            priority=1,
            conditions={'immediate': True},
            description=f"Stop loss at -{stop_loss}% from entry"
        ))
        
        # Take profit levels
        if strategy_type in ['CONSERVATIVE', 'MODERATE'] and len(take_profits) > 1:
            # Scale out approach
            exit_sizes = [40.0, 30.0, 30.0]  # Exit 40%, 30%, 30%
            for i, target in enumerate(take_profits[:3]):
                levels.append(ExitLevel(
                    trigger_type=ExitTrigger.TAKE_PROFIT,
                    trigger_price_percent=target,
                    exit_size_percent=exit_sizes[i] if i < len(exit_sizes) else 100.0,
                    execution_method=ExitMethod.LIMIT_ORDER,
                    priority=2 + i,
                    conditions={'partial_exit': True},
                    description=f"Take profit {i+1} at +{target}%"
                ))
        else:
            # Single exit approach
            if take_profits:
                levels.append(ExitLevel(
                    trigger_type=ExitTrigger.TAKE_PROFIT,
                    trigger_price_percent=take_profits[0],
                    exit_size_percent=100.0,
                    execution_method=ExitMethod.LIMIT_ORDER,
                    priority=2,
                    conditions={'full_exit': True},
                    description=f"Take profit at +{take_profits[0]}%"
                ))
        
        # Breakeven stop level (if price moves favorably)
        if strategy_type in ['CONSERVATIVE', 'MODERATE']:
            levels.append(ExitLevel(
                trigger_type=ExitTrigger.TRAILING_STOP,
                trigger_price_percent=0.0,  # Breakeven
                exit_size_percent=100.0,
                execution_method=ExitMethod.MARKET_ORDER,
                priority=5,
                conditions={'min_profit_reached': self.breakeven_move_threshold},
                description=f"Move stop to breakeven after +{self.breakeven_move_threshold}% move"
            ))
        
        return sorted(levels, key=lambda x: x.priority)
    
    def _configure_trailing_stop(
        self,
        risk_score: float,
        market_conditions: Dict[str, Any],
        strategy_params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Configure trailing stop parameters."""
        if risk_score > 0.8:
            # No trailing stop for very high risk
            return None
        
        trailing_config = {
            'enabled': True,
            'activation_profit_percent': strategy_params['trailing_start'],
            'trail_distance_percent': self.default_trailing_stop_percent,
            'trail_method': 'PERCENTAGE',  # vs DOLLAR, ATR
            'update_frequency': 'ON_CLOSE',  # vs REAL_TIME
            'partial_trail': strategy_params.get('position_scaling', False)
        }
        
        # Adjust for volatility
        volatility = market_conditions.get('volatility', 0.1)
        if volatility > 0.2:
            # Wider trail in volatile markets
            trailing_config['trail_distance_percent'] *= 1.5
        
        # Adjust for trend
        if market_conditions.get('trend_strength', 0) > 0.6:
            # Tighter trail in strong trends
            trailing_config['trail_distance_percent'] *= 0.8
            trailing_config['activation_profit_percent'] *= 0.8
        
        return trailing_config
    
    def _calculate_time_exits(
        self,
        risk_score: float,
        market_conditions: Dict[str, Any],
        position_context: Dict[str, Any]
    ) -> Tuple[Optional[int], Optional[List[Dict[str, Any]]]]:
        """Calculate time-based exit parameters."""
        # Base hold time
        max_hold_hours = self.default_max_hold_hours
        
        # Adjust for risk (shorter holds for higher risk)
        if risk_score > 0.6:
            max_hold_hours = int(max_hold_hours * 0.5)
        elif risk_score > 0.4:
            max_hold_hours = int(max_hold_hours * 0.75)
        
        # Adjust for market conditions
        if market_conditions.get('volatility', 0) > 0.3:
            max_hold_hours = int(max_hold_hours * 0.7)
        
        # Time decay schedule (reduce position over time)
        time_decay = None
        if risk_score > 0.5:
            time_decay = [
                {'hours': 24, 'reduce_percent': 25},    # Reduce 25% after 1 day
                {'hours': 72, 'reduce_percent': 50},    # Reduce 50% after 3 days
                {'hours': max_hold_hours, 'reduce_percent': 100}  # Full exit at max
            ]
        
        return max_hold_hours, time_decay
    
    def _define_emergency_conditions(
        self,
        risk_score: float,
        position_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Define emergency exit conditions."""
        conditions = []
        
        # Liquidity crisis condition
        conditions.append({
            'name': 'liquidity_crisis',
            'trigger': 'liquidity_drop',
            'threshold': 50,  # 50% liquidity drop
            'action': 'immediate_market_exit',
            'description': 'Exit if liquidity drops 50%'
        })
        
        # Volatility spike condition
        conditions.append({
            'name': 'volatility_spike',
            'trigger': 'volatility_increase',
            'threshold': 300,  # 300% volatility increase
            'action': 'immediate_market_exit',
            'description': 'Exit if volatility triples'
        })
        
        # Risk score increase condition
        if risk_score > 0.5:
            conditions.append({
                'name': 'risk_escalation',
                'trigger': 'risk_score_increase',
                'threshold': 0.2,  # 20% risk increase
                'action': 'scaled_exit',
                'description': 'Scale out if risk increases 20%'
            })
        
        # Contract security alert
        conditions.append({
            'name': 'security_alert',
            'trigger': 'contract_vulnerability',
            'threshold': 'any',
            'action': 'immediate_market_exit',
            'description': 'Exit on any security vulnerability'
        })
        
        return conditions
    
    def _configure_circuit_breaker(
        self,
        risk_score: float,
        market_conditions: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Configure circuit breaker for extreme moves."""
        if risk_score < 0.3:
            # No circuit breaker for low risk
            return None
        
        return {
            'enabled': True,
            'price_drop_threshold': 30.0,  # 30% flash crash
            'time_window_seconds': 300,    # Within 5 minutes
            'action': 'immediate_exit',
            'override_slippage': True,      # Exit at any price
            'alert_enabled': True
        }
    
    def _calculate_expected_metrics(
        self,
        stop_loss: float,
        take_profits: List[float],
        risk_score: float,
        technical_signals: List[Any]
    ) -> Tuple[float, float, float]:
        """Calculate expected return, risk/reward, and win probability."""
        # Average take profit
        avg_take_profit = sum(take_profits) / len(take_profits) if take_profits else 30.0
        
        # Expected return (probability-weighted)
        win_prob = self._estimate_win_probability(risk_score, technical_signals)
        expected_return = (win_prob * avg_take_profit) - ((1 - win_prob) * stop_loss)
        
        # Risk/reward ratio
        risk_reward = avg_take_profit / stop_loss if stop_loss > 0 else 2.0
        
        return expected_return, risk_reward, win_prob
    
    def _estimate_win_probability(
        self,
        risk_score: float,
        technical_signals: List[Any]
    ) -> float:
        """Estimate probability of successful trade."""
        # Base probability from risk score
        base_prob = 1 - risk_score
        
        # Adjust for technical signals
        if technical_signals:
            bullish_signals = sum(1 for s in technical_signals 
                                if hasattr(s, 'signal') and s.signal == 'BUY')
            signal_ratio = bullish_signals / len(technical_signals)
            base_prob = (base_prob + signal_ratio) / 2
        
        # Ensure reasonable range
        return max(0.2, min(0.8, base_prob))
    
    def _find_technical_stop_level(self, technical_signals: List[Any]) -> Optional[float]:
        """Find stop loss level from technical analysis."""
        if not technical_signals:
            return None
        
        stop_levels = []
        for signal in technical_signals:
            if hasattr(signal, 'price_targets'):
                targets = signal.price_targets
                if 'support' in targets:
                    # Calculate % from current price
                    support_percent = abs(targets['support'])
                    stop_levels.append(support_percent * 1.02)  # 2% below support
        
        return min(stop_levels) if stop_levels else None
    
    def _find_technical_target_levels(
        self,
        technical_signals: List[Any]
    ) -> Optional[List[float]]:
        """Find take profit levels from technical analysis."""
        if not technical_signals:
            return None
        
        target_levels = []
        for signal in technical_signals:
            if hasattr(signal, 'price_targets'):
                targets = signal.price_targets
                if 'resistance' in targets:
                    resistance_percent = targets['resistance']
                    target_levels.append(resistance_percent * 0.98)  # 2% below resistance
        
        return sorted(target_levels) if target_levels else None
    
    def _merge_target_levels(
        self,
        calculated_targets: List[float],
        technical_targets: List[float]
    ) -> List[float]:
        """Merge calculated and technical target levels."""
        all_targets = calculated_targets + technical_targets
        
        # Remove duplicates within 2% of each other
        unique_targets = []
        for target in sorted(all_targets):
            if not unique_targets or target > unique_targets[-1] * 1.02:
                unique_targets.append(target)
        
        return unique_targets
    
    def _generate_strategy_name(self, strategy_type: str, risk_score: float) -> str:
        """Generate descriptive strategy name."""
        risk_level = "High" if risk_score > 0.6 else "Medium" if risk_score > 0.3 else "Low"
        return f"{strategy_type.title()} {risk_level}-Risk Exit Strategy"
    
    def _generate_strategy_rationale(
        self,
        strategy_type: str,
        risk_score: float,
        stop_loss: float,
        take_profits: List[float]
    ) -> str:
        """Generate human-readable strategy rationale."""
        rationale = f"Using {strategy_type.lower()} exit strategy based on "
        rationale += f"{risk_score:.0%} risk assessment. "
        
        if strategy_type == 'CONSERVATIVE':
            rationale += "Prioritizing capital preservation with tight stops and scaled exits. "
        elif strategy_type == 'AGGRESSIVE':
            rationale += "Maximizing profit potential with wider stops and higher targets. "
        else:
            rationale += "Balanced approach between risk management and profit optimization. "
        
        rationale += f"Stop loss at -{stop_loss}% protects against significant losses. "
        
        if len(take_profits) > 1:
            rationale += f"Multiple take-profit levels ({', '.join([f'+{tp}%' for tp in take_profits])}) "
            rationale += "allow for partial profit-taking while maintaining upside exposure."
        else:
            rationale += f"Single take-profit at +{take_profits[0]}% for simplified execution."
        
        return rationale
    
    def _generate_risk_notes(
        self,
        risk_score: float,
        stop_loss: float,
        market_conditions: Dict[str, Any]
    ) -> List[str]:
        """Generate risk management notes."""
        notes = []
        
        if risk_score > 0.7:
            notes.append("⚠️ High risk position - consider reducing size or avoiding entry")
        
        if stop_loss > 20:
            notes.append("⚠️ Wide stop loss - increased capital at risk")
        
        if market_conditions.get('volatility', 0) > 0.3:
            notes.append("⚠️ High volatility - expect larger price swings")
        
        if market_conditions.get('liquidity_score', 1) < 0.5:
            notes.append("⚠️ Low liquidity - exit slippage likely")
        
        notes.append(f"💡 Maximum risk per trade: {stop_loss}% of position")
        notes.append("💡 Use trailing stop once in profit to protect gains")
        
        return notes
    
    def _generate_optimization_suggestions(
        self,
        strategy_type: str,
        risk_score: float,
        technical_signals: List[Any],
        market_conditions: Dict[str, Any]
    ) -> List[str]:
        """Generate optimization suggestions."""
        suggestions = []
        
        if strategy_type == 'CONSERVATIVE' and risk_score < 0.3:
            suggestions.append("📈 Low risk detected - consider more aggressive targets")
        
        if market_conditions.get('trend_strength', 0) > 0.7:
            suggestions.append("📈 Strong trend - consider pyramiding into position")
        
        if len(technical_signals) > 3:
            suggestions.append("📈 Multiple confirmations - consider larger position size")
        
        if market_conditions.get('volatility', 0) < 0.1:
            suggestions.append("📈 Low volatility - tighten stops for better risk/reward")
        
        return suggestions
    
    def _update_statistics(
        self,
        strategy_type: str,
        risk_reward: float,
        max_hold_hours: Optional[int]
    ) -> None:
        """Update internal statistics."""
        self.strategy_stats['total_created'] += 1
        self.strategy_stats['by_type'][strategy_type] += 1
        
        # Update rolling averages
        total = self.strategy_stats['total_created']
        
        # Risk/reward average
        current_rr = self.strategy_stats['avg_risk_reward']
        new_rr = ((current_rr * (total - 1)) + risk_reward) / total
        self.strategy_stats['avg_risk_reward'] = new_rr
        
        # Hold time average
        if max_hold_hours:
            current_hold = self.strategy_stats['avg_hold_time_hours']
            new_hold = ((current_hold * (total - 1)) + max_hold_hours) / total
            self.strategy_stats['avg_hold_time_hours'] = new_hold