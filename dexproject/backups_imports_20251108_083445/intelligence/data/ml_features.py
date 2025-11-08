"""
ML Feature Collector for Paper Trading Bot - Level 10 AI Learning

This module provides the MLFeatureCollector class for collecting
training data when intelligence level is set to 10 (Autonomous AI).

File: dexproject/paper_trading/intelligence/ml_features.py
"""

import logging
from typing import Dict, Any, List

# Django imports
from django.utils import timezone

# Import type utilities
from paper_trading.utils.type_utils import TypeConverter

# Import base classes
from dexproject.paper_trading.intelligence.core.base import MarketContext, TradingDecision

logger = logging.getLogger(__name__)


class MLFeatureCollector:
    """
    Collects ML training data for Level 10 AI learning.
    
    This class captures features from trading decisions and market
    contexts to build a dataset for machine learning models.
    
    Attributes:
        intel_level: Current intelligence level
        training_data: List of collected training samples
        max_samples: Maximum number of samples to keep in memory
        logger: Logger instance
    """
    
    def __init__(self, intel_level: int, max_samples: int = 1000):
        """
        Initialize the ML feature collector.
        
        Args:
            intel_level: Intelligence level (should be 10 for ML)
            max_samples: Maximum number of samples to keep
        """
        self.intel_level = intel_level
        self.training_data: List[Dict[str, Any]] = []
        self.max_samples = max_samples
        self.converter = TypeConverter()
        self.logger = logging.getLogger(f'{__name__}.MLFeatureCollector')
        
        if intel_level == 10:
            self.logger.info(
                f"[ML COLLECTOR] Initialized for Level 10 (max {max_samples} samples)"
            )
        else:
            self.logger.debug(
                f"[ML COLLECTOR] Initialized but inactive (Level {intel_level} != 10)"
            )
    
    def collect_features(
        self,
        context: MarketContext,
        decision: TradingDecision
    ) -> None:
        """
        Collect ML features from a trading decision.
        
        Only collects when intel_level is 10 (Autonomous AI).
        
        Args:
            context: Market context used for decision
            decision: Trading decision made
        """
        try:
            # Only collect for Level 10
            if self.intel_level != 10:
                return
            
            # Extract features
            features = self._extract_features(context, decision)
            
            # Add to training data
            self.training_data.append(features)
            
            # Trim if exceeding max samples
            if len(self.training_data) > self.max_samples:
                self.training_data.pop(0)
                self.logger.debug(
                    f"[ML COLLECTOR] Trimmed training data to {self.max_samples} samples"
                )
            
            self.logger.debug(
                f"[ML COLLECTOR] Collected features for {context.token_symbol} "
                f"({len(self.training_data)} total samples)"
            )
            
        except Exception as e:
            self.logger.error(
                f"[ML COLLECTOR] Error collecting features: {e}",
                exc_info=True
            )
    
    def _extract_features(
        self,
        context: MarketContext,
        decision: TradingDecision
    ) -> Dict[str, Any]:
        """
        Extract ML features from context and decision.
        
        Args:
            context: Market context
            decision: Trading decision
            
        Returns:
            Dictionary of features for ML training
        """
        try:
            features = {
                # Timestamp
                'timestamp': timezone.now().isoformat(),
                
                # Token info
                'token_symbol': context.token_symbol,
                'token_address': context.token_address,
                
                # Price features
                'current_price': float(context.current_price),
                'price_24h_ago': float(context.price_24h_ago),
                'volatility': float(context.volatility),
                'momentum': float(context.momentum),
                
                # Volume features
                'volume_24h': float(context.volume_24h),
                'volume_24h_change': float(context.volume_24h_change),
                
                # Liquidity features
                'pool_liquidity_usd': float(context.pool_liquidity_usd),
                'liquidity_depth_score': context.liquidity_depth_score,
                'expected_slippage': float(context.expected_slippage),
                
                # Market features
                'market_cap': float(context.market_cap),
                'holder_count': context.holder_count,
                'trend_direction': context.trend_direction,
                'volatility_index': context.volatility_index,
                
                # Network features
                'gas_price_gwei': float(context.gas_price_gwei),
                'network_congestion': context.network_congestion,
                'pending_tx_count': context.pending_tx_count,
                
                # MEV features
                'mev_threat_level': context.mev_threat_level,
                'sandwich_risk': context.sandwich_risk,
                'frontrun_probability': context.frontrun_probability,
                
                # Competition features
                'competing_bots_detected': context.competing_bots_detected,
                'bot_success_rate': context.bot_success_rate,
                
                # Risk indicators
                'chaos_event_detected': context.chaos_event_detected,
                
                # Historical performance
                'recent_failures': context.recent_failures,
                'success_rate_1h': context.success_rate_1h,
                'average_profit_1h': float(context.average_profit_1h),
                
                # Decision outputs (labels for supervised learning)
                'decision_action': decision.action,
                'position_size_percent': float(decision.position_size_percent),
                'position_size_usd': float(decision.position_size_usd),
                'stop_loss_percent': float(decision.stop_loss_percent) if decision.stop_loss_percent else None,
                'risk_score': float(decision.risk_score),
                'opportunity_score': float(decision.opportunity_score),
                'overall_confidence': float(decision.overall_confidence),
                
                # Execution strategy
                'execution_mode': decision.execution_mode,
                'use_private_relay': decision.use_private_relay,
                'gas_strategy': decision.gas_strategy,
                'max_gas_price_gwei': float(decision.max_gas_price_gwei),
                
                # Timing
                'time_sensitivity': decision.time_sensitivity,
                'max_execution_time_ms': decision.max_execution_time_ms,
                
                # Meta
                'decision_id': decision.decision_id,
                'processing_time_ms': decision.processing_time_ms
            }
            
            return features
            
        except Exception as e:
            self.logger.error(
                f"[ML COLLECTOR] Error extracting features: {e}",
                exc_info=True
            )
            return {}
    
    def get_training_data(self) -> List[Dict[str, Any]]:
        """
        Get all collected training data.
        
        Returns:
            List of training samples
        """
        try:
            if self.intel_level != 10:
                self.logger.warning(
                    f"[ML COLLECTOR] Training data only available at Level 10 "
                    f"(current: {self.intel_level})"
                )
                return []
            
            self.logger.info(
                f"[ML COLLECTOR] Retrieved {len(self.training_data)} training samples"
            )
            
            return self.training_data.copy()
            
        except Exception as e:
            self.logger.error(
                f"[ML COLLECTOR] Error retrieving training data: {e}",
                exc_info=True
            )
            return []
    
    def clear_training_data(self) -> None:
        """Clear all collected training data."""
        try:
            sample_count = len(self.training_data)
            self.training_data = []
            
            self.logger.info(
                f"[ML COLLECTOR] Cleared {sample_count} training samples"
            )
            
        except Exception as e:
            self.logger.error(
                f"[ML COLLECTOR] Error clearing training data: {e}",
                exc_info=True
            )
    
    def export_training_data(self, format: str = 'dict') -> Any:
        """
        Export training data in specified format.
        
        Args:
            format: Export format ('dict', 'json', 'csv')
            
        Returns:
            Training data in specified format
        """
        try:
            if self.intel_level != 10:
                self.logger.warning(
                    "[ML COLLECTOR] Training data only available at Level 10"
                )
                return None
            
            if format == 'dict':
                return self.training_data.copy()
            elif format == 'json':
                import json
                return json.dumps(self.training_data, indent=2)
            elif format == 'csv':
                # Convert to CSV format
                if not self.training_data:
                    return ""
                
                import csv
                import io
                
                output = io.StringIO()
                
                # Get all keys from first sample
                fieldnames = list(self.training_data[0].keys())
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                
                writer.writeheader()
                writer.writerows(self.training_data)
                
                return output.getvalue()
            else:
                self.logger.error(
                    f"[ML COLLECTOR] Unknown export format: {format}"
                )
                return None
                
        except Exception as e:
            self.logger.error(
                f"[ML COLLECTOR] Error exporting training data: {e}",
                exc_info=True
            )
            return None
    
    def get_feature_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about collected features.
        
        Returns:
            Dictionary with feature statistics
        """
        try:
            if not self.training_data:
                return {
                    'sample_count': 0,
                    'features_per_sample': 0
                }
            
            # Calculate statistics
            sample_count = len(self.training_data)
            features_per_sample = len(self.training_data[0])
            
            # Count actions
            action_counts = {}
            for sample in self.training_data:
                action = sample.get('decision_action', 'UNKNOWN')
                action_counts[action] = action_counts.get(action, 0) + 1
            
            # Average scores
            avg_risk = sum(
                s.get('risk_score', 0) for s in self.training_data
            ) / sample_count
            avg_opportunity = sum(
                s.get('opportunity_score', 0) for s in self.training_data
            ) / sample_count
            avg_confidence = sum(
                s.get('overall_confidence', 0) for s in self.training_data
            ) / sample_count
            
            stats = {
                'sample_count': sample_count,
                'features_per_sample': features_per_sample,
                'action_distribution': action_counts,
                'average_scores': {
                    'risk': round(avg_risk, 2),
                    'opportunity': round(avg_opportunity, 2),
                    'confidence': round(avg_confidence, 2)
                },
                'oldest_sample': self.training_data[0].get('timestamp'),
                'newest_sample': self.training_data[-1].get('timestamp')
            }
            
            self.logger.debug(
                f"[ML COLLECTOR] Statistics: {sample_count} samples, "
                f"{features_per_sample} features"
            )
            
            return stats
            
        except Exception as e:
            self.logger.error(
                f"[ML COLLECTOR] Error calculating statistics: {e}",
                exc_info=True
            )
            return {}