"""
Smart Lane Analysis Pipeline

Main orchestration system for comprehensive token analysis. Coordinates
all analysis components to provide strategic trading recommendations
within the <5s performance target.

Path: engine/smart_lane/pipeline.py
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from . import (
    SmartLaneConfig, SmartLaneAnalysis, RiskScore, TechnicalSignal,
    AnalysisDepth, RiskCategory, SmartLaneAction, DecisionConfidence,
    DEFAULT_CONFIG, MAX_CONCURRENT_ANALYSES
)
from .cache import SmartLaneCache
from .thought_log import ThoughtLogGenerator
from .strategy.position_sizing import PositionSizer
from .strategy.exit_strategies import ExitStrategyManager

logger = logging.getLogger(__name__)


class PipelineStatus:
    """Pipeline execution status tracking."""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class SmartLanePipeline:
    """
    Main Smart Lane analysis pipeline orchestrator.
    
    Coordinates all analysis components to provide comprehensive token
    analysis and strategic trading recommendations within performance targets.
    """
    
    def __init__(
        self,
        config: SmartLaneConfig = None,
        chain_id: int = 1,
        enable_caching: bool = True
    ):
        """
        Initialize the Smart Lane pipeline.
        
        Args:
            config: Pipeline configuration settings
            chain_id: Blockchain chain identifier
            enable_caching: Whether to enable analysis result caching
        """
        self.config = config or DEFAULT_CONFIG
        self.chain_id = chain_id
        self.enable_caching = enable_caching
        
        # Pipeline state management
        self.status = PipelineStatus.INITIALIZING
        self.active_analyses: Set[str] = set()
        self.analysis_history: Dict[str, SmartLaneAnalysis] = {}
        
        # Component initialization
        self.cache = SmartLaneCache(chain_id=chain_id) if enable_caching else None
        self.thought_log_generator = ThoughtLogGenerator(config=config)
        self.position_sizer = PositionSizer(config=config)
        self.exit_strategy_manager = ExitStrategyManager(config=config)
        
        # Performance tracking
        self.performance_metrics = {
            'total_analyses': 0,
            'successful_analyses': 0,
            'failed_analyses': 0,
            'timeout_analyses': 0,
            'average_analysis_time_ms': 0.0,
            'cache_hit_ratio': 0.0
        }
        
        # Thread pool for concurrent analysis
        self.thread_pool = ThreadPoolExecutor(
            max_workers=MAX_CONCURRENT_ANALYSES,
            thread_name_prefix="SmartLane"
        )
        
        logger.info(f"Smart Lane pipeline initialized for chain {chain_id}")
    
    async def analyze_token(
        self,
        token_address: str,
        context: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False
    ) -> SmartLaneAnalysis:
        """
        Perform comprehensive token analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context for analysis (price, volume, etc.)
            force_refresh: Force fresh analysis, bypassing cache
            
        Returns:
            Complete Smart Lane analysis with recommendation
            
        Raises:
            TimeoutError: If analysis exceeds configured time limit
            ValueError: If token_address is invalid
        """
        analysis_start = time.time()
        analysis_id = str(uuid.uuid4())
        
        try:
            logger.info(f"Starting Smart Lane analysis: {token_address[:10]}... (ID: {analysis_id})")
            
            # Input validation
            if not token_address or len(token_address) != 42:
                raise ValueError(f"Invalid token address: {token_address}")
            
            # Check if we're at capacity
            if len(self.active_analyses) >= MAX_CONCURRENT_ANALYSES:
                logger.warning("Pipeline at maximum capacity, queuing analysis")
                await self._wait_for_capacity()
            
            self.active_analyses.add(analysis_id)
            self.performance_metrics['total_analyses'] += 1
            
            # Check cache first (if enabled and not forcing refresh)
            cached_result = None
            if self.cache and not force_refresh:
                cached_result = await self.cache.get_analysis(token_address)
                if cached_result:
                    logger.debug(f"Using cached analysis for {token_address[:10]}...")
                    self.active_analyses.remove(analysis_id)
                    return cached_result
            
            # Perform comprehensive analysis with timeout protection
            analysis_task = asyncio.create_task(
                self._perform_comprehensive_analysis(
                    token_address=token_address,
                    analysis_id=analysis_id,
                    context=context or {}
                )
            )
            
            try:
                # Wait for analysis with timeout
                analysis_result = await asyncio.wait_for(
                    analysis_task,
                    timeout=self.config.max_analysis_time_seconds
                )
                
                # Cache successful result
                if self.cache:
                    await self.cache.store_analysis(token_address, analysis_result)
                
                # Update performance metrics
                analysis_time = (time.time() - analysis_start) * 1000
                self._update_performance_metrics(analysis_time, success=True)
                
                logger.info(
                    f"Smart Lane analysis completed: {token_address[:10]}... "
                    f"({analysis_time:.1f}ms, {analysis_result.recommended_action.value})"
                )
                
                return analysis_result
                
            except asyncio.TimeoutError:
                analysis_task.cancel()
                self.performance_metrics['timeout_analyses'] += 1
                logger.error(f"Analysis timeout for {token_address[:10]}... after {self.config.max_analysis_time_seconds}s")
                raise TimeoutError(f"Analysis exceeded {self.config.max_analysis_time_seconds}s timeout")
                
        except Exception as e:
            self.performance_metrics['failed_analyses'] += 1
            logger.error(f"Analysis failed for {token_address[:10]}...: {e}", exc_info=True)
            raise
            
        finally:
            # Cleanup
            self.active_analyses.discard(analysis_id)
    
    async def _perform_comprehensive_analysis(
        self,
        token_address: str,
        analysis_id: str,
        context: Dict[str, Any]
    ) -> SmartLaneAnalysis:
        """
        Execute the comprehensive analysis pipeline.
        
        This is the core analysis orchestration method that coordinates
        all risk assessment categories and technical analysis.
        """
        analysis_start_time = time.time()
        
        logger.debug(f"Executing comprehensive analysis pipeline for {token_address[:10]}...")
        
        # Initialize analysis result structure
        analysis_result = SmartLaneAnalysis(
            token_address=token_address,
            chain_id=self.chain_id,
            analysis_id=analysis_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            risk_scores={},
            overall_risk_score=0.0,
            overall_confidence=0.0,
            technical_signals=[],
            technical_summary={},
            recommended_action=SmartLaneAction.HOLD,
            position_size_percent=0.0,
            confidence_level=DecisionConfidence.LOW,
            stop_loss_percent=None,
            take_profit_targets=[],
            max_hold_time_hours=None,
            total_analysis_time_ms=0.0,
            cache_hit_ratio=0.0,
            data_freshness_score=1.0,
            critical_warnings=[],
            informational_notes=[]
        )
        
        try:
            # Phase 1: Parallel Risk Analysis (target: <3s)
            logger.debug("Phase 1: Executing parallel risk analysis...")
            risk_analysis_start = time.time()
            
            risk_scores = await self._execute_parallel_risk_analysis(
                token_address=token_address,
                context=context
            )
            
            analysis_result.risk_scores = risk_scores
            analysis_result.overall_risk_score = self._calculate_overall_risk_score(risk_scores)
            analysis_result.overall_confidence = self._calculate_overall_confidence(risk_scores)
            
            risk_analysis_time = (time.time() - risk_analysis_start) * 1000
            logger.debug(f"Risk analysis completed in {risk_analysis_time:.1f}ms")
            
            # Phase 2: Technical Analysis (target: <1s)
            logger.debug("Phase 2: Executing technical analysis...")
            technical_start = time.time()
            
            technical_signals = await self._execute_technical_analysis(
                token_address=token_address,
                context=context
            )
            
            analysis_result.technical_signals = technical_signals
            analysis_result.technical_summary = self._summarize_technical_signals(technical_signals)
            
            technical_time = (time.time() - technical_start) * 1000
            logger.debug(f"Technical analysis completed in {technical_time:.1f}ms")
            
            # Phase 3: Strategic Decision Making (target: <1s)
            logger.debug("Phase 3: Generating strategic recommendation...")
            strategy_start = time.time()
            
            # Generate position sizing recommendation
            position_size = self.position_sizer.calculate_position_size(
                overall_overall_risk_score=analysis_result.overall_risk_score,
                analysis_confidence=analysis_result.overall_confidence,
                technical_signals=technical_signals,
                context=context
            )
            
            # Generate exit strategy
            exit_strategy = await self.exit_strategy_manager.generate_exit_strategy(
                risk_score=analysis_result.overall_risk_score,
                technical_signals=technical_signals,
                position_size=position_size,
                context=context
            )
            
            # Make final recommendation
            recommendation = self._make_strategic_recommendation(
                risk_scores=risk_scores,
                technical_signals=technical_signals,
                position_size=position_size,
                context=context
            )
            
            # Update analysis result with strategic components
            analysis_result.recommended_action = recommendation['action']
            analysis_result.confidence_level = recommendation['confidence']
            analysis_result.position_size_percent = position_size
            analysis_result.stop_loss_percent = exit_strategy.get('stop_loss_percent')
            analysis_result.take_profit_targets = exit_strategy.get('take_profit_targets', [])
            analysis_result.max_hold_time_hours = exit_strategy.get('max_hold_time_hours')
            
            strategy_time = (time.time() - strategy_start) * 1000
            logger.debug(f"Strategic decision making completed in {strategy_time:.1f}ms")
            
            # Phase 4: Generate AI Thought Log (target: <500ms)
            if self.config.thought_log_enabled:
                logger.debug("Phase 4: Generating AI thought log...")
                thought_log_start = time.time()
                
                thought_log = await self.thought_log_generator.generate_thought_log(
                    analysis_result=analysis_result,
                    context=context
                )
                
                analysis_result.informational_notes.append(f"AI Thought Log: {thought_log}")
                
                thought_log_time = (time.time() - thought_log_start) * 1000
                logger.debug(f"Thought log generation completed in {thought_log_time:.1f}ms")
            
            # Finalize analysis
            total_analysis_time = (time.time() - analysis_start_time) * 1000
            analysis_result.total_analysis_time_ms = total_analysis_time
            
            # Store in history
            self.analysis_history[analysis_id] = analysis_result
            
            logger.info(
                f"Comprehensive analysis completed for {token_address[:10]}... "
                f"in {total_analysis_time:.1f}ms - Recommendation: {analysis_result.recommended_action.value}"
            )
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error in comprehensive analysis pipeline: {e}", exc_info=True)
            
            # Add error information to result
            analysis_result.critical_warnings.append(f"Analysis pipeline error: {str(e)}")
            analysis_result.recommended_action = SmartLaneAction.AVOID
            analysis_result.confidence_level = DecisionConfidence.LOW
            
            return analysis_result
    
    async def _execute_parallel_risk_analysis(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> Dict[RiskCategory, RiskScore]:
        """
        Execute all risk analysis categories in parallel for performance.
        
        This method coordinates the parallel execution of all 8 risk categories
        to meet the <3s performance target for comprehensive analysis.
        """
        risk_tasks = []
        enabled_categories = self.config.enabled_categories
        
        logger.debug(f"Starting parallel risk analysis for {len(enabled_categories)} categories")
        
        # Create analysis tasks for each enabled category
        for category in enabled_categories:
            task = asyncio.create_task(
                self._analyze_risk_category(
                    category=category,
                    token_address=token_address,
                    context=context
                ),
                name=f"risk_{category.value.lower()}"
            )
            risk_tasks.append((category, task))
        
        # Execute all risk analyses concurrently
        risk_scores = {}
        
        try:
            # Wait for all tasks to complete
            for category, task in risk_tasks:
                try:
                    risk_score = await task
                    risk_scores[category] = risk_score
                    logger.debug(f"Risk category {category.value} completed: score={risk_score.score:.3f}")
                    
                except Exception as e:
                    logger.warning(f"Risk category {category.value} failed: {e}")
                    # Create a failed risk score
                    risk_scores[category] = RiskScore(
                        category=category,
                        score=1.0,  # Maximum risk for failed analysis
                        confidence=0.0,  # Zero confidence
                        details={'error': str(e)},
                        analysis_time_ms=0.0,
                        warnings=[f"Analysis failed: {str(e)}"],
                        data_quality="POOR"
                    )
            
            logger.debug(f"Parallel risk analysis completed: {len(risk_scores)} categories processed")
            return risk_scores
            
        except Exception as e:
            logger.error(f"Critical error in parallel risk analysis: {e}", exc_info=True)
            raise
    
    async def _analyze_risk_category(
        self,
        category: RiskCategory,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Analyze a specific risk category.
        
        This method will import and execute the appropriate analyzer
        based on the risk category.
        """
        category_start = time.time()
        
        try:
            # Import the appropriate analyzer (dynamic import for performance)
            if category == RiskCategory.HONEYPOT_DETECTION:
                from .analyzers.honeypot_analyzer import HoneypotAnalyzer
                analyzer = HoneypotAnalyzer(chain_id=self.chain_id)
                
            elif category == RiskCategory.LIQUIDITY_ANALYSIS:
                from .analyzers.liquidity_analyzer import LiquidityAnalyzer
                analyzer = LiquidityAnalyzer(chain_id=self.chain_id)
                
            elif category == RiskCategory.SOCIAL_SENTIMENT:
                from .analyzers.social_analyzer import SocialAnalyzer
                analyzer = SocialAnalyzer(chain_id=self.chain_id)
                
            elif category == RiskCategory.TECHNICAL_ANALYSIS:
                from .analyzers.technical_analyzer import TechnicalAnalyzer
                analyzer = TechnicalAnalyzer(chain_id=self.chain_id)
                
            elif category == RiskCategory.TOKEN_TAX_ANALYSIS:
                from .analyzers.tax_analyzer import TaxAnalyzer
                analyzer = TaxAnalyzer(chain_id=self.chain_id)
                
            elif category == RiskCategory.CONTRACT_SECURITY:
                from .analyzers.contract_analyzer import ContractAnalyzer
                analyzer = ContractAnalyzer(chain_id=self.chain_id)
                
            elif category == RiskCategory.HOLDER_DISTRIBUTION:
                from .analyzers.holder_analyzer import HolderAnalyzer
                analyzer = HolderAnalyzer(chain_id=self.chain_id)
                
            elif category == RiskCategory.MARKET_STRUCTURE:
                from .analyzers.market_analyzer import MarketAnalyzer
                analyzer = MarketAnalyzer(chain_id=self.chain_id)
                
            else:
                raise ValueError(f"Unknown risk category: {category}")
            
            # Execute the analysis
            risk_score = await analyzer.analyze(token_address, context)
            
            # Add timing information
            analysis_time = (time.time() - category_start) * 1000
            risk_score.analysis_time_ms = analysis_time
            
            return risk_score
            
        except Exception as e:
            analysis_time = (time.time() - category_start) * 1000
            logger.error(f"Risk category {category.value} analysis failed: {e}")
            
            # Return a failure risk score
            return RiskScore(
                category=category,
                score=1.0,  # Maximum risk
                confidence=0.0,  # Zero confidence
                details={'error': str(e)},
                analysis_time_ms=analysis_time,
                warnings=[f"Category analysis failed: {str(e)}"],
                data_quality="POOR"
            )
    
    async def _execute_technical_analysis(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> List[TechnicalSignal]:
        """
        Execute multi-timeframe technical analysis.
        
        Returns technical signals for configured timeframes.
        """
        try:
            from .analyzers.technical_analyzer import TechnicalAnalyzer
            
            technical_analyzer = TechnicalAnalyzer(chain_id=self.chain_id)
            
            # Get technical signals for all configured timeframes
            signals = []
            for timeframe in self.config.technical_timeframes:
                try:
                    signal = await technical_analyzer.analyze_timeframe(
                        token_address=token_address,
                        timeframe=timeframe,
                        context=context
                    )
                    signals.append(signal)
                    
                except Exception as e:
                    logger.warning(f"Technical analysis failed for timeframe {timeframe}: {e}")
            
            logger.debug(f"Technical analysis completed: {len(signals)} timeframes analyzed")
            return signals
            
        except Exception as e:
            logger.error(f"Technical analysis execution failed: {e}")
            return []
    
    def _calculate_overall_risk_score(self, risk_scores: Dict[RiskCategory, RiskScore]) -> float:
        """Calculate weighted overall risk score from category scores."""
        if not risk_scores:
            return 1.0  # Maximum risk if no scores available
        
        # Risk category weights (can be made configurable)
        category_weights = {
            RiskCategory.HONEYPOT_DETECTION: 0.25,
            RiskCategory.LIQUIDITY_ANALYSIS: 0.20,
            RiskCategory.CONTRACT_SECURITY: 0.15,
            RiskCategory.TOKEN_TAX_ANALYSIS: 0.15,
            RiskCategory.HOLDER_DISTRIBUTION: 0.10,
            RiskCategory.MARKET_STRUCTURE: 0.10,
            RiskCategory.SOCIAL_SENTIMENT: 0.03,
            RiskCategory.TECHNICAL_ANALYSIS: 0.02
        }
        
        weighted_score = 0.0
        total_weight = 0.0
        
        for category, risk_score in risk_scores.items():
            weight = category_weights.get(category, 0.1)  # Default weight
            confidence_adjusted_score = risk_score.score * risk_score.confidence
            
            weighted_score += confidence_adjusted_score * weight
            total_weight += weight * risk_score.confidence
        
        if total_weight > 0:
            return min(1.0, weighted_score / total_weight)
        else:
            return 1.0  # Maximum risk if no confident scores
    
    def _calculate_overall_confidence(self, risk_scores: Dict[RiskCategory, RiskScore]) -> float:
        """Calculate overall confidence from individual category confidences."""
        if not risk_scores:
            return 0.0
        
        confidences = [score.confidence for score in risk_scores.values()]
        return sum(confidences) / len(confidences)
    
    def _summarize_technical_signals(self, signals: List[TechnicalSignal]) -> Dict[str, Any]:
        """Summarize technical signals across timeframes."""
        if not signals:
            return {'overall_signal': 'NEUTRAL', 'signal_count': 0}
        
        buy_signals = len([s for s in signals if s.signal == 'BUY'])
        sell_signals = len([s for s in signals if s.signal == 'SELL'])
        neutral_signals = len([s for s in signals if s.signal == 'NEUTRAL'])
        
        # Determine overall signal
        if buy_signals > sell_signals + neutral_signals:
            overall_signal = 'BUY'
        elif sell_signals > buy_signals + neutral_signals:
            overall_signal = 'SELL'
        else:
            overall_signal = 'NEUTRAL'
        
        avg_strength = sum(s.strength for s in signals) / len(signals) if signals else 0.0
        avg_confidence = sum(s.confidence for s in signals) / len(signals) if signals else 0.0
        
        return {
            'overall_signal': overall_signal,
            'signal_count': len(signals),
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'neutral_signals': neutral_signals,
            'average_strength': avg_strength,
            'average_confidence': avg_confidence
        }
    
    def _make_strategic_recommendation(
        self,
        risk_scores: Dict[RiskCategory, RiskScore],
        technical_signals: List[TechnicalSignal],
        position_size: float,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate final strategic recommendation based on all analysis.
        
        This is the core decision-making logic that combines risk assessment,
        technical analysis, and position sizing into a final recommendation.
        """
        overall_risk = self._calculate_overall_risk_score(risk_scores)
        overall_confidence = self._calculate_overall_confidence(risk_scores)
        
        # Technical signal consensus
        technical_summary = self._summarize_technical_signals(technical_signals)
        technical_signal = technical_summary.get('overall_signal', 'NEUTRAL')
        technical_strength = technical_summary.get('average_strength', 0.0)
        
        # Decision matrix based on risk and technical signals
        if overall_risk > self.config.max_acceptable_risk_score:
            # High risk - avoid or minimal exposure
            action = SmartLaneAction.AVOID
            confidence = DecisionConfidence.HIGH if overall_confidence > 0.7 else DecisionConfidence.MEDIUM
            
        elif overall_confidence < self.config.min_confidence_threshold:
            # Low confidence - wait for better data
            action = SmartLaneAction.WAIT_FOR_BETTER_ENTRY
            confidence = DecisionConfidence.LOW
            
        elif technical_signal == 'BUY' and technical_strength > 0.6:
            # Strong buy signal with acceptable risk
            if position_size > 5.0:
                action = SmartLaneAction.BUY
            else:
                action = SmartLaneAction.PARTIAL_BUY
            confidence = DecisionConfidence.HIGH if overall_confidence > 0.8 else DecisionConfidence.MEDIUM
            
        elif technical_signal == 'SELL' and technical_strength > 0.6:
            # Strong sell signal
            action = SmartLaneAction.SELL
            confidence = DecisionConfidence.HIGH if overall_confidence > 0.8 else DecisionConfidence.MEDIUM
            
        elif overall_risk < 0.3 and technical_strength > 0.4:
            # Low risk with moderate technical signal
            action = SmartLaneAction.SCALE_IN
            confidence = DecisionConfidence.MEDIUM
            
        else:
            # Default to hold/wait
            action = SmartLaneAction.HOLD
            confidence = DecisionConfidence.LOW
        
        return {
            'action': action,
            'confidence': confidence,
            'reasoning': {
                'overall_risk': overall_risk,
                'overall_confidence': overall_confidence,
                'technical_signal': technical_signal,
                'technical_strength': technical_strength,
                'position_size': position_size
            }
        }
    
    async def _wait_for_capacity(self) -> None:
        """Wait for pipeline capacity to become available."""
        while len(self.active_analyses) >= MAX_CONCURRENT_ANALYSES:
            await asyncio.sleep(0.1)
    
    def _update_performance_metrics(self, analysis_time_ms: float, success: bool) -> None:
        """Update performance tracking metrics."""
        if success:
            self.performance_metrics['successful_analyses'] += 1
        else:
            self.performance_metrics['failed_analyses'] += 1
        
        # Update rolling average analysis time
        total_analyses = self.performance_metrics['total_analyses']
        current_avg = self.performance_metrics['average_analysis_time_ms']
        
        new_avg = ((current_avg * (total_analyses - 1)) + analysis_time_ms) / total_analyses
        self.performance_metrics['average_analysis_time_ms'] = new_avg
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current pipeline performance metrics."""
        success_rate = 0.0
        if self.performance_metrics['total_analyses'] > 0:
            success_rate = (
                self.performance_metrics['successful_analyses'] / 
                self.performance_metrics['total_analyses']
            ) * 100
        
        return {
            'status': self.status,
            'active_analyses': len(self.active_analyses),
            'total_analyses': self.performance_metrics['total_analyses'],
            'success_rate_percent': success_rate,
            'average_analysis_time_ms': self.performance_metrics['average_analysis_time_ms'],
            'cache_enabled': self.cache is not None,
            'config_analysis_depth': self.config.analysis_depth.value,
            'max_analysis_time_s': self.config.max_analysis_time_seconds
        }
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the pipeline."""
        logger.info("Shutting down Smart Lane pipeline...")
        
        # Wait for active analyses to complete (with timeout)
        if self.active_analyses:
            logger.info(f"Waiting for {len(self.active_analyses)} active analyses to complete...")
            
            timeout = 10.0  # 10 second shutdown timeout
            start_time = time.time()
            
            while self.active_analyses and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.5)
        
        # Shutdown thread pool
        self.thread_pool.shutdown(wait=True)
        
        # Close cache connections
        if self.cache:
            await self.cache.close()
        
        self.status = "SHUTDOWN"
        logger.info("Smart Lane pipeline shutdown completed")


# Module-level pipeline instance (singleton pattern)
_pipeline_instance: Optional[SmartLanePipeline] = None


def get_pipeline(
    config: SmartLaneConfig = None,
    chain_id: int = 1
) -> SmartLanePipeline:
    """Get or create the singleton Smart Lane pipeline instance."""
    global _pipeline_instance
    
    if _pipeline_instance is None:
        _pipeline_instance = SmartLanePipeline(
            config=config or DEFAULT_CONFIG,
            chain_id=chain_id
        )
    
    return _pipeline_instance


# Export key classes
__all__ = [
    'SmartLanePipeline',
    'PipelineStatus',
    'get_pipeline'
]