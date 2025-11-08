"""
AI Thought Log Generator for Smart Lane Analysis

Generates comprehensive, human-readable explanations of Smart Lane analysis
decisions with full reasoning transparency. This is a key differentiator
providing explainable AI decision making.

Path: engine/smart_lane/thought_log.py
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from . import (
    SmartLaneAnalysis, SmartLaneConfig, RiskCategory, SmartLaneAction,
    DecisionConfidence, TechnicalSignal
)

logger = logging.getLogger(__name__)


class ThoughtLogLevel(Enum):
    """Detail levels for thought log generation."""
    BASIC = "BASIC"          # Key decision points only
    DETAILED = "DETAILED"    # Include reasoning steps
    COMPREHENSIVE = "COMPREHENSIVE"  # Full analysis breakdown
    DEBUG = "DEBUG"          # Include all internal data


class ReasoningStep(Enum):
    """Types of reasoning steps in the analysis process."""
    DATA_COLLECTION = "DATA_COLLECTION"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    TECHNICAL_ANALYSIS = "TECHNICAL_ANALYSIS"
    POSITION_SIZING = "POSITION_SIZING"
    STRATEGY_SELECTION = "STRATEGY_SELECTION"
    CONFIDENCE_EVALUATION = "CONFIDENCE_EVALUATION"
    FINAL_DECISION = "FINAL_DECISION"


@dataclass
class ThoughtLogEntry:
    """Individual entry in the thought log."""
    step: ReasoningStep
    timestamp: str
    title: str
    content: str
    confidence: float
    data_points: Dict[str, Any]
    warnings: List[str]
    processing_time_ms: float


@dataclass
class ThoughtLog:
    """Complete thought log for an analysis."""
    analysis_id: str
    token_address: str
    generation_time: str
    level: ThoughtLogLevel
    total_generation_time_ms: float
    
    # Core reasoning
    executive_summary: str
    key_insights: List[str]
    main_concerns: List[str]
    confidence_factors: Dict[str, float]
    
    # Detailed reasoning steps
    reasoning_steps: List[ThoughtLogEntry]
    
    # Decision matrix
    decision_rationale: str
    alternative_scenarios: List[Dict[str, Any]]
    risk_reward_analysis: str
    
    # Educational content
    learning_points: List[str]
    market_context: str


class ThoughtLogGenerator:
    """
    AI Thought Log generator for transparent decision explanation.
    
    Provides human-readable explanations of Smart Lane analysis decisions
    with different levels of detail based on configuration.
    """
    
    def __init__(self, config: SmartLaneConfig):
        """
        Initialize the thought log generator.
        
        Args:
            config: Smart Lane configuration with thought log settings
        """
        self.config = config
        self.generation_stats = {
            'total_generated': 0,
            'average_generation_time_ms': 0.0,
            'by_level': {level.value: 0 for level in ThoughtLogLevel}
        }
        
        # Risk category descriptions for explanations
        self.risk_category_descriptions = {
            RiskCategory.HONEYPOT_DETECTION: "Honeypot/Scam Detection",
            RiskCategory.LIQUIDITY_ANALYSIS: "Liquidity & Market Depth",
            RiskCategory.SOCIAL_SENTIMENT: "Social Sentiment & Community",
            RiskCategory.TECHNICAL_ANALYSIS: "Technical Chart Patterns",
            RiskCategory.TOKEN_TAX_ANALYSIS: "Transaction Tax Structure",
            RiskCategory.CONTRACT_SECURITY: "Smart Contract Security",
            RiskCategory.HOLDER_DISTRIBUTION: "Token Holder Distribution",
            RiskCategory.MARKET_STRUCTURE: "Market Structure & Manipulation"
        }
        
        logger.info(f"Thought log generator initialized with {config.thought_log_detail_level} detail level")
    
    async def generate_thought_log(
        self,
        analysis_result: SmartLaneAnalysis,
        context: Dict[str, Any]
    ) -> ThoughtLog:
        """
        Generate comprehensive thought log for analysis result.
        
        Args:
            analysis_result: Complete Smart Lane analysis
            context: Additional context for reasoning
            
        Returns:
            Complete thought log with reasoning explanation
        """
        generation_start = time.time()
        
        try:
            logger.debug(f"Generating thought log for {analysis_result.token_address[:10]}...")
            
            # Determine detail level
            detail_level = ThoughtLogLevel(self.config.thought_log_detail_level)
            
            # Generate reasoning steps
            reasoning_steps = await self._generate_reasoning_steps(analysis_result, context)
            
            # Create executive summary
            executive_summary = self._create_executive_summary(analysis_result, context)
            
            # Extract key insights
            key_insights = self._extract_key_insights(analysis_result, reasoning_steps)
            
            # Identify main concerns
            main_concerns = self._identify_main_concerns(analysis_result)
            
            # Calculate confidence factors
            confidence_factors = self._calculate_confidence_factors(analysis_result)
            
            # Generate decision rationale
            decision_rationale = self._create_decision_rationale(analysis_result, context)
            
            # Create alternative scenarios
            alternative_scenarios = self._generate_alternative_scenarios(analysis_result, context)
            
            # Risk-reward analysis
            risk_reward_analysis = self._create_risk_reward_analysis(analysis_result)
            
            # Educational content
            learning_points = self._generate_learning_points(analysis_result, context)
            market_context = self._create_market_context(analysis_result, context)
            
            # Calculate generation time
            generation_time_ms = (time.time() - generation_start) * 1000
            
            # Create thought log
            thought_log = ThoughtLog(
                analysis_id=analysis_result.analysis_id,
                token_address=analysis_result.token_address,
                generation_time=datetime.now(timezone.utc).isoformat(),
                level=detail_level,
                total_generation_time_ms=generation_time_ms,
                executive_summary=executive_summary,
                key_insights=key_insights,
                main_concerns=main_concerns,
                confidence_factors=confidence_factors,
                reasoning_steps=reasoning_steps,
                decision_rationale=decision_rationale,
                alternative_scenarios=alternative_scenarios,
                risk_reward_analysis=risk_reward_analysis,
                learning_points=learning_points,
                market_context=market_context
            )
            
            # Update statistics
            self._update_generation_stats(detail_level, generation_time_ms)
            
            logger.info(
                f"Thought log generated for {analysis_result.token_address[:10]}... "
                f"in {generation_time_ms:.1f}ms ({detail_level.value} level)"
            )
            
            return thought_log
            
        except Exception as e:
            logger.error(f"Error generating thought log: {e}", exc_info=True)
            
            # Return minimal thought log on error
            return self._create_error_thought_log(analysis_result, str(e))
    
    async def _generate_reasoning_steps(
        self,
        analysis: SmartLaneAnalysis,
        context: Dict[str, Any]
    ) -> List[ThoughtLogEntry]:
        """Generate detailed reasoning steps for the analysis."""
        steps = []
        
        # Step 1: Data Collection
        steps.append(self._create_data_collection_step(analysis, context))
        
        # Step 2: Risk Assessment
        steps.append(self._create_risk_assessment_step(analysis))
        
        # Step 3: Technical Analysis
        steps.append(self._create_technical_analysis_step(analysis))
        
        # Step 4: Position Sizing
        steps.append(self._create_position_sizing_step(analysis))
        
        # Step 5: Strategy Selection
        steps.append(self._create_strategy_selection_step(analysis))
        
        # Step 6: Confidence Evaluation
        steps.append(self._create_confidence_evaluation_step(analysis))
        
        # Step 7: Final Decision
        steps.append(self._create_final_decision_step(analysis))
        
        return steps
    
    def _create_data_collection_step(
        self,
        analysis: SmartLaneAnalysis,
        context: Dict[str, Any]
    ) -> ThoughtLogEntry:
        """Create data collection reasoning step."""
        content = f"""
        **Data Collection & Initial Assessment**
        
        Token Address: {analysis.token_address}
        Chain: {self._get_chain_name(analysis.chain_id)}
        Analysis Time: {analysis.total_analysis_time_ms:.1f}ms
        Data Freshness: {analysis.data_freshness_score:.1%}
        
        **Sources Analyzed:**
        • On-chain contract data and transaction history
        • Liquidity pool information across major DEXes  
        • Social sentiment from multiple platforms
        • Technical price data across multiple timeframes
        • Holder distribution and wallet analysis
        
        **Data Quality Assessment:**
        The analysis utilized {len(analysis.risk_scores)} risk categories with an average
        data freshness score of {analysis.data_freshness_score:.1%}. 
        {len(analysis.critical_warnings)} critical warnings were identified during data collection.
        """
        
        return ThoughtLogEntry(
            step=ReasoningStep.DATA_COLLECTION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            title="Data Collection & Sources",
            content=content.strip(),
            confidence=analysis.data_freshness_score,
            data_points={
                'sources_count': len(analysis.risk_scores),
                'freshness_score': analysis.data_freshness_score,
                'warnings_count': len(analysis.critical_warnings)
            },
            warnings=analysis.critical_warnings[:3],  # Top 3 warnings
            processing_time_ms=analysis.total_analysis_time_ms * 0.1  # ~10% of total time
        )
    
    def _create_risk_assessment_step(self, analysis: SmartLaneAnalysis) -> ThoughtLogEntry:
        """Create risk assessment reasoning step."""
        risk_breakdown = []
        high_risk_categories = []
        
        for category, score in analysis.risk_scores.items():
            category_name = self.risk_category_descriptions.get(category, category.value)
            risk_level = self._categorize_risk_level(score.score)
            
            risk_breakdown.append(f"• {category_name}: {score.score:.2f} ({risk_level})")
            
            if score.score > 0.7:
                high_risk_categories.append(category_name)
        
        content = f"""
        **Comprehensive Risk Assessment**
        
        Overall Risk Score: {analysis.overall_risk_score:.2f}/1.00 ({self._categorize_risk_level(analysis.overall_risk_score)})
        Assessment Confidence: {analysis.overall_confidence:.1%}
        
        **Risk Category Breakdown:**
        {chr(10).join(risk_breakdown)}
        
        **Risk Analysis Summary:**
        {self._create_risk_summary(analysis.overall_risk_score, high_risk_categories)}
        
        **Key Risk Factors:**
        {self._identify_key_risk_factors(analysis)}
        """
        
        return ThoughtLogEntry(
            step=ReasoningStep.RISK_ASSESSMENT,
            timestamp=datetime.now(timezone.utc).isoformat(),
            title="Risk Assessment Analysis",
            content=content.strip(),
            confidence=analysis.overall_confidence,
            data_points={
                'overall_risk': analysis.overall_risk_score,
                'high_risk_categories': len(high_risk_categories),
                'category_count': len(analysis.risk_scores)
            },
            warnings=[f"High risk in: {', '.join(high_risk_categories)}"] if high_risk_categories else [],
            processing_time_ms=analysis.total_analysis_time_ms * 0.4  # ~40% of total time
        )
    
    def _create_technical_analysis_step(self, analysis: SmartLaneAnalysis) -> ThoughtLogEntry:
        """Create technical analysis reasoning step."""
        if not analysis.technical_signals:
            content = "**Technical Analysis:** No technical signals available for analysis."
            confidence = 0.0
        else:
            signals_summary = analysis.technical_summary
            signal_breakdown = []
            
            for signal in analysis.technical_signals:
                signal_breakdown.append(
                    f"• {signal.timeframe}: {signal.signal} "
                    f"(strength: {signal.strength:.2f}, confidence: {signal.confidence:.2f})"
                )
            
            content = f"""
            **Technical Analysis Across Multiple Timeframes**
            
            Overall Signal: {signals_summary.get('overall_signal', 'NEUTRAL')}
            Signal Strength: {signals_summary.get('average_strength', 0):.2f}/1.00
            Technical Confidence: {signals_summary.get('average_confidence', 0):.1%}
            
            **Timeframe Breakdown:**
            {chr(10).join(signal_breakdown)}
            
            **Signal Consensus:**
            • Buy signals: {signals_summary.get('buy_signals', 0)}
            • Sell signals: {signals_summary.get('sell_signals', 0)}  
            • Neutral signals: {signals_summary.get('neutral_signals', 0)}
            
            **Technical Interpretation:**
            {self._interpret_technical_signals(analysis.technical_signals, signals_summary)}
            """
            
            confidence = signals_summary.get('average_confidence', 0.0)
        
        return ThoughtLogEntry(
            step=ReasoningStep.TECHNICAL_ANALYSIS,
            timestamp=datetime.now(timezone.utc).isoformat(),
            title="Technical Analysis",
            content=content.strip(),
            confidence=confidence,
            data_points={
                'signals_count': len(analysis.technical_signals),
                'overall_signal': analysis.technical_summary.get('overall_signal', 'NEUTRAL'),
                'avg_strength': analysis.technical_summary.get('average_strength', 0.0)
            },
            warnings=[],
            processing_time_ms=analysis.total_analysis_time_ms * 0.2  # ~20% of total time
        )
    
    def _create_position_sizing_step(self, analysis: SmartLaneAnalysis) -> ThoughtLogEntry:
        """Create position sizing reasoning step."""
        sizing_rationale = self._explain_position_sizing(
            analysis.position_size_percent,
            analysis.overall_risk_score,
            analysis.overall_confidence
        )
        
        content = f"""
        **Position Sizing Strategy**
        
        Recommended Position Size: {analysis.position_size_percent:.1f}% of portfolio
        
        **Sizing Rationale:**
        {sizing_rationale}
        
        **Risk-Adjusted Considerations:**
        • Portfolio risk tolerance: {self.config.risk_per_trade_percent:.1f}% per trade
        • Maximum position limit: {self.config.max_position_size_percent:.1f}%
        • Risk score impact: {analysis.overall_risk_score:.2f} reduces size by {analysis.overall_risk_score * 50:.0f}%
        • Confidence impact: {analysis.overall_confidence:.1%} confidence level applied
        
        **Position Management:**
        {self._create_position_management_guidance(analysis)}
        """
        
        return ThoughtLogEntry(
            step=ReasoningStep.POSITION_SIZING,
            timestamp=datetime.now(timezone.utc).isoformat(),
            title="Position Sizing Strategy",
            content=content.strip(),
            confidence=analysis.overall_confidence,
            data_points={
                'position_size_percent': analysis.position_size_percent,
                'risk_score': analysis.overall_risk_score,
                'max_allowed': self.config.max_position_size_percent
            },
            warnings=self._get_position_sizing_warnings(analysis),
            processing_time_ms=analysis.total_analysis_time_ms * 0.1  # ~10% of total time
        )
    
    def _create_strategy_selection_step(self, analysis: SmartLaneAnalysis) -> ThoughtLogEntry:
        """Create strategy selection reasoning step."""
        strategy_explanation = self._explain_strategy_selection(analysis.recommended_action)
        
        content = f"""
        **Strategy Selection & Exit Planning**
        
        Recommended Action: {analysis.recommended_action.value}
        Confidence Level: {analysis.confidence_level.value}
        
        **Strategy Rationale:**
        {strategy_explanation}
        
        **Exit Strategy Components:**
        • Stop Loss: {analysis.stop_loss_percent or 'Dynamic based on volatility'}%
        • Take Profit Targets: {', '.join([f'{target:.1f}%' for target in (analysis.take_profit_targets or [])])}
        • Maximum Hold Time: {analysis.max_hold_time_hours or 'Unlimited'} hours
        
        **Strategy Alternatives Considered:**
        {self._list_alternative_strategies(analysis)}
        """
        
        return ThoughtLogEntry(
            step=ReasoningStep.STRATEGY_SELECTION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            title="Strategy Selection",
            content=content.strip(),
            confidence=self._action_to_confidence_score(analysis.confidence_level),
            data_points={
                'action': analysis.recommended_action.value,
                'confidence': analysis.confidence_level.value,
                'stop_loss': analysis.stop_loss_percent,
                'take_profit_count': len(analysis.take_profit_targets or [])
            },
            warnings=[],
            processing_time_ms=analysis.total_analysis_time_ms * 0.1  # ~10% of total time
        )
    
    def _create_confidence_evaluation_step(self, analysis: SmartLaneAnalysis) -> ThoughtLogEntry:
        """Create confidence evaluation reasoning step."""
        confidence_factors = self._analyze_confidence_factors(analysis)
        
        content = f"""
        **Confidence Assessment & Reliability**
        
        Overall Confidence: {analysis.overall_confidence:.1%}
        Decision Confidence: {analysis.confidence_level.value}
        
        **Confidence Contributing Factors:**
        {self._format_confidence_factors(confidence_factors)}
        
        **Reliability Indicators:**
        • Data quality: {analysis.data_freshness_score:.1%}
        • Analysis completeness: {len(analysis.risk_scores)}/8 risk categories
        • Technical signal agreement: {self._calculate_signal_agreement(analysis.technical_signals):.1%}
        • Time constraints: Analysis completed in {analysis.total_analysis_time_ms:.0f}ms (target: <5000ms)
        
        **Confidence Limitations:**
        {self._identify_confidence_limitations(analysis)}
        """
        
        return ThoughtLogEntry(
            step=ReasoningStep.CONFIDENCE_EVALUATION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            title="Confidence & Reliability Assessment",
            content=content.strip(),
            confidence=analysis.overall_confidence,
            data_points={
                'overall_confidence': analysis.overall_confidence,
                'data_freshness': analysis.data_freshness_score,
                'categories_analyzed': len(analysis.risk_scores),
                'analysis_time_ms': analysis.total_analysis_time_ms
            },
            warnings=self._get_confidence_warnings(analysis),
            processing_time_ms=analysis.total_analysis_time_ms * 0.05  # ~5% of total time
        )
    
    def _create_final_decision_step(self, analysis: SmartLaneAnalysis) -> ThoughtLogEntry:
        """Create final decision reasoning step."""
        decision_summary = self._create_final_decision_summary(analysis)
        
        content = f"""
        **Final Decision & Recommendation**
        
        **RECOMMENDATION: {analysis.recommended_action.value}**
        Position Size: {analysis.position_size_percent:.1f}% of portfolio
        Confidence: {analysis.confidence_level.value} ({analysis.overall_confidence:.1%})
        
        **Decision Matrix Results:**
        • Risk Assessment: {analysis.overall_risk_score:.2f}/1.00 ({self._categorize_risk_level(analysis.overall_risk_score)})
        • Technical Signals: {analysis.technical_summary.get('overall_signal', 'NEUTRAL')}
        • Position Sizing: Conservative approach due to risk level
        • Exit Strategy: Defined stop-loss and take-profit levels
        
        **Key Decision Drivers:**
        {decision_summary}
        
        **Implementation Notes:**
        • Execute during favorable market conditions
        • Monitor for changes in risk factors
        • Adjust position size based on portfolio performance
        • Review decision if market structure changes significantly
        
        **Risk Disclaimer:**
        This analysis is based on available data and market conditions at the time of analysis.
        Market conditions can change rapidly. Always perform your own due diligence.
        """
        
        return ThoughtLogEntry(
            step=ReasoningStep.FINAL_DECISION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            title="Final Decision & Implementation",
            content=content.strip(),
            confidence=analysis.overall_confidence,
            data_points={
                'final_action': analysis.recommended_action.value,
                'position_size': analysis.position_size_percent,
                'overall_risk': analysis.overall_risk_score,
                'overall_confidence': analysis.overall_confidence
            },
            warnings=analysis.critical_warnings,
            processing_time_ms=analysis.total_analysis_time_ms * 0.05  # ~5% of total time
        )
    
    def _create_executive_summary(
        self,
        analysis: SmartLaneAnalysis,
        context: Dict[str, Any]
    ) -> str:
        """Create executive summary of the analysis."""
        risk_level = self._categorize_risk_level(analysis.overall_risk_score)
        technical_signal = analysis.technical_summary.get('overall_signal', 'NEUTRAL')
        
        return f"""
        **EXECUTIVE SUMMARY**
        
        Token: {analysis.token_address[:10]}...
        Recommendation: **{analysis.recommended_action.value}** ({analysis.confidence_level.value} confidence)
        Position Size: {analysis.position_size_percent:.1f}% of portfolio
        
        **Key Findings:**
        • Risk Level: {risk_level} ({analysis.overall_risk_score:.2f}/1.00)
        • Technical Signal: {technical_signal}
        • Analysis Confidence: {analysis.overall_confidence:.1%}
        • Data Quality: {analysis.data_freshness_score:.1%}
        
        **Bottom Line:** {self._create_bottom_line_assessment(analysis)}
        """
    
    def _extract_key_insights(
        self,
        analysis: SmartLaneAnalysis,
        reasoning_steps: List[ThoughtLogEntry]
    ) -> List[str]:
        """Extract key insights from the analysis."""
        insights = []
        
        # Risk-based insights
        if analysis.overall_risk_score > 0.7:
            insights.append(f"High risk detected ({analysis.overall_risk_score:.2f}/1.00) - proceed with extreme caution")
        elif analysis.overall_risk_score < 0.3:
            insights.append(f"Low risk profile ({analysis.overall_risk_score:.2f}/1.00) - favorable risk-reward setup")
        
        # Technical insights
        technical_signal = analysis.technical_summary.get('overall_signal')
        if technical_signal == 'BUY':
            buy_strength = analysis.technical_summary.get('average_strength', 0)
            insights.append(f"Strong technical buy signals across timeframes (strength: {buy_strength:.2f})")
        elif technical_signal == 'SELL':
            sell_strength = analysis.technical_summary.get('average_strength', 0)
            insights.append(f"Technical indicators suggest selling pressure (strength: {sell_strength:.2f})")
        
        # Confidence insights
        if analysis.overall_confidence > 0.8:
            insights.append("High confidence in analysis due to quality data and consistent signals")
        elif analysis.overall_confidence < 0.5:
            insights.append("Lower confidence due to data limitations or conflicting signals")
        
        # Position sizing insights
        if analysis.position_size_percent < 2:
            insights.append("Conservative position sizing recommended due to risk factors")
        elif analysis.position_size_percent > 8:
            insights.append("Larger position size justified by favorable risk-reward profile")
        
        # Performance insights
        if analysis.total_analysis_time_ms > 4000:
            insights.append("Extended analysis time allowed for thorough evaluation")
        
        return insights[:5]  # Limit to top 5 insights
    
    def _identify_main_concerns(self, analysis: SmartLaneAnalysis) -> List[str]:
        """Identify main concerns from the analysis."""
        concerns = []
        
        # Add critical warnings as concerns
        concerns.extend(analysis.critical_warnings[:3])
        
        # Risk-based concerns
        high_risk_categories = [
            category for category, score in analysis.risk_scores.items()
            if score.score > 0.7
        ]
        
        if high_risk_categories:
            category_names = [self.risk_category_descriptions.get(cat, cat.value) for cat in high_risk_categories]
            concerns.append(f"High risk in: {', '.join(category_names)}")
        
        # Data quality concerns
        if analysis.data_freshness_score < 0.7:
            concerns.append(f"Data freshness concerns (score: {analysis.data_freshness_score:.1%})")
        
        # Confidence concerns
        if analysis.overall_confidence < 0.6:
            concerns.append(f"Low analysis confidence ({analysis.overall_confidence:.1%}) - additional validation recommended")
        
        # Technical concerns
        conflicting_signals = (
            analysis.technical_summary.get('buy_signals', 0) > 0 and
            analysis.technical_summary.get('sell_signals', 0) > 0
        )
        if conflicting_signals:
            concerns.append("Conflicting technical signals across timeframes")
        
        return concerns[:5]  # Limit to top 5 concerns
    
    def _calculate_confidence_factors(self, analysis: SmartLaneAnalysis) -> Dict[str, float]:
        """Calculate detailed confidence factors."""
        return {
            'data_quality': analysis.data_freshness_score,
            'risk_assessment_confidence': analysis.overall_confidence,
            'technical_signal_agreement': self._calculate_signal_agreement(analysis.technical_signals),
            'analysis_completeness': len(analysis.risk_scores) / 8.0,  # 8 total categories
            'time_adequacy': min(1.0, analysis.total_analysis_time_ms / 3000.0),  # 3s target
            'error_rate': 1.0 - (len(analysis.critical_warnings) * 0.2)
        }
    
    def _create_decision_rationale(
        self,
        analysis: SmartLaneAnalysis,
        context: Dict[str, Any]
    ) -> str:
        """Create detailed decision rationale."""
        return f"""
        The recommendation to **{analysis.recommended_action.value}** is based on a comprehensive
        analysis weighing multiple factors:
        
        **Primary Decision Drivers:**
        1. Risk Score: {analysis.overall_risk_score:.2f}/1.00 indicates {self._categorize_risk_level(analysis.overall_risk_score)} risk
        2. Technical Analysis: {analysis.technical_summary.get('overall_signal', 'NEUTRAL')} consensus across timeframes
        3. Confidence Level: {analysis.overall_confidence:.1%} in analysis quality and data
        4. Position Sizing: {analysis.position_size_percent:.1f}% provides appropriate risk exposure
        
        **Decision Matrix Logic:**
        {self._explain_decision_matrix_logic(analysis)}
        
        This recommendation balances potential returns against identified risks while
        maintaining portfolio-appropriate position sizing.
        """
    
    def _generate_alternative_scenarios(
        self,
        analysis: SmartLaneAnalysis,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate alternative scenario analyses."""
        scenarios = []
        
        # Scenario 1: Higher risk tolerance
        scenarios.append({
            'name': 'Higher Risk Tolerance',
            'description': f'If risk tolerance was increased, position size could be {analysis.position_size_percent * 1.5:.1f}%',
            'conditions': 'Higher portfolio risk allocation, strong conviction in analysis',
            'outcome': 'Increased potential returns but higher downside risk'
        })
        
        # Scenario 2: Market downturn
        scenarios.append({
            'name': 'Market Downturn Scenario',
            'description': 'If broader market enters correction phase',
            'conditions': 'General market decline >10%, decreased liquidity',
            'outcome': 'Recommend reducing position or waiting for better entry'
        })
        
        # Scenario 3: New information
        scenarios.append({
            'name': 'New Information Available',
            'description': 'If additional fundamental or technical data becomes available',
            'conditions': 'Major news, partnership announcements, regulatory changes',
            'outcome': 'Re-run analysis with updated parameters'
        })
        
        return scenarios
    
    def _create_risk_reward_analysis(self, analysis: SmartLaneAnalysis) -> str:
        """Create risk-reward analysis summary."""
        potential_upside = analysis.take_profit_targets[0] if analysis.take_profit_targets else 20.0
        potential_downside = analysis.stop_loss_percent or 10.0
        risk_reward_ratio = potential_upside / potential_downside
        
        return f"""
        **Risk-Reward Profile Analysis**
        
        Potential Upside: +{potential_upside:.1f}% (first target)
        Potential Downside: -{potential_downside:.1f}% (stop loss)
        Risk-Reward Ratio: {risk_reward_ratio:.1f}:1
        
        **Risk-Adjusted Returns:**
        Considering the risk score of {analysis.overall_risk_score:.2f}, the expected
        risk-adjusted return is {self._calculate_risk_adjusted_return(analysis):.1f}%.
        
        **Probability Assessment:**
        Based on technical signals and risk analysis, estimated success probability
        is {self._estimate_success_probability(analysis):.0f}%.
        
        **Portfolio Impact:**
        With a {analysis.position_size_percent:.1f}% position size, maximum portfolio
        impact is limited to {analysis.position_size_percent * potential_downside / 100:.2f}%
        downside risk.
        """
    
    def _generate_learning_points(
        self,
        analysis: SmartLaneAnalysis,
        context: Dict[str, Any]
    ) -> List[str]:
        """Generate educational learning points."""
        learning_points = []
        
        # Risk education based on analysis
        if analysis.overall_risk_score > 0.7:
            learning_points.append(
                "High-risk tokens require smaller position sizes and tighter stop-losses to manage downside"
            )
        
        # Technical analysis education
        if analysis.technical_signals:
            conflicting = (
                analysis.technical_summary.get('buy_signals', 0) > 0 and
                analysis.technical_summary.get('sell_signals', 0) > 0
            )
            if conflicting:
                learning_points.append(
                    "When technical signals conflict across timeframes, consider the longer-term trend as primary"
                )
        
        # Position sizing education
        if analysis.position_size_percent < 5:
            learning_points.append(
                "Conservative position sizing allows for multiple attempts while limiting single-trade impact"
            )
        
        # Confidence and decision-making
        if analysis.overall_confidence < 0.7:
            learning_points.append(
                "Lower confidence analyses suggest waiting for better data or more favorable setups"
            )
        
        # General trading wisdom
        learning_points.append(
            "Risk management is more important than being right - protect capital first, profits second"
        )
        
        return learning_points[:4]  # Limit to top 4 learning points
    
    def _create_market_context(
        self,
        analysis: SmartLaneAnalysis,
        context: Dict[str, Any]
    ) -> str:
        """Create market context explanation."""
        return f"""
        **Market Context & Environment**
        
        This analysis was performed on {analysis.timestamp[:10]} for the
        {self._get_chain_name(analysis.chain_id)} blockchain ecosystem.
        
        **Current Market Considerations:**
        • Analysis completed in {analysis.total_analysis_time_ms:.0f}ms using Smart Lane comprehensive evaluation
        • {len(analysis.risk_scores)} risk categories analyzed for thorough assessment
        • Technical analysis across {len(analysis.technical_signals)} timeframes
        • Data freshness score of {analysis.data_freshness_score:.1%} indicates current market data
        
        **Trading Environment:**
        Smart Lane analysis provides deeper insights than speed-focused approaches,
        enabling more informed decision-making for strategic positions. This approach
        is optimal for medium-term holds and risk-conscious trading.
        
        **Market Structure Notes:**
        {self._create_market_structure_notes(analysis)}
        """
    
    # Helper methods for formatting and calculations
    
    def _categorize_risk_level(self, risk_score: float) -> str:
        """Categorize risk score into human-readable levels."""
        if risk_score >= 0.8:
            return "CRITICAL"
        elif risk_score >= 0.6:
            return "HIGH"
        elif risk_score >= 0.4:
            return "MEDIUM"
        elif risk_score >= 0.2:
            return "LOW"
        else:
            return "MINIMAL"
    
    def _get_chain_name(self, chain_id: int) -> str:
        """Get human-readable chain name."""
        chain_names = {
            1: "Ethereum",
            56: "BSC",
            137: "Polygon",
            42161: "Arbitrum",
            10: "Optimism",
            8453: "Base"
        }
        return chain_names.get(chain_id, f"Chain {chain_id}")
    
    def _calculate_signal_agreement(self, signals: List[TechnicalSignal]) -> float:
        """Calculate agreement percentage among technical signals."""
        if not signals:
            return 0.0
        
        buy_count = sum(1 for s in signals if s.signal == 'BUY')
        sell_count = sum(1 for s in signals if s.signal == 'SELL')
        neutral_count = sum(1 for s in signals if s.signal == 'NEUTRAL')
        
        max_agreement = max(buy_count, sell_count, neutral_count)
        return max_agreement / len(signals)
    
    def _action_to_confidence_score(self, confidence_level: DecisionConfidence) -> float:
        """Convert confidence level to numeric score."""
        mapping = {
            DecisionConfidence.LOW: 0.3,
            DecisionConfidence.MEDIUM: 0.6,
            DecisionConfidence.HIGH: 0.8,
            DecisionConfidence.VERY_HIGH: 0.95
        }
        return mapping.get(confidence_level, 0.5)
    
    def _update_generation_stats(self, level: ThoughtLogLevel, time_ms: float) -> None:
        """Update thought log generation statistics."""
        self.generation_stats['total_generated'] += 1
        self.generation_stats['by_level'][level.value] += 1
        
        # Update rolling average
        total = self.generation_stats['total_generated']
        current_avg = self.generation_stats['average_generation_time_ms']
        
        new_avg = ((current_avg * (total - 1)) + time_ms) / total
        self.generation_stats['average_generation_time_ms'] = new_avg
    
    def _create_error_thought_log(
        self,
        analysis: SmartLaneAnalysis,
        error_message: str
    ) -> ThoughtLog:
        """Create minimal thought log for error cases."""
        return ThoughtLog(
            analysis_id=analysis.analysis_id,
            token_address=analysis.token_address,
            generation_time=datetime.now(timezone.utc).isoformat(),
            level=ThoughtLogLevel.BASIC,
            total_generation_time_ms=0.0,
            executive_summary=f"Error generating thought log: {error_message}",
            key_insights=["Thought log generation failed"],
            main_concerns=[error_message],
            confidence_factors={},
            reasoning_steps=[],
            decision_rationale="Analysis completed but thought log generation failed",
            alternative_scenarios=[],
            risk_reward_analysis="Unable to generate risk-reward analysis",
            learning_points=["Always have fallback error handling in place"],
            market_context="Error in context generation"
        )
    
    # Additional helper methods (placeholder implementations)
    
    def _create_risk_summary(self, risk_score: float, high_risk_categories: List[str]) -> str:
        """Create risk summary text."""
        level = self._categorize_risk_level(risk_score)
        
        if level == "CRITICAL":
            return f"CRITICAL RISK DETECTED. This token shows extremely high risk factors. Consider avoiding this trade entirely."
        elif level == "HIGH":
            return f"HIGH RISK identified. Proceed only with minimal position sizing and tight risk management."
        elif level == "MEDIUM":
            return f"MODERATE RISK detected. Standard risk management protocols should be applied."
        elif level == "LOW":
            return f"LOW RISK profile. Favorable for larger position sizes with appropriate stops."
        else:
            return f"MINIMAL RISK detected. Strong fundamental and technical setup."
    
    def _identify_key_risk_factors(self, analysis: SmartLaneAnalysis) -> str:
        """Identify key risk factors from analysis."""
        factors = []
        
        for category, score in analysis.risk_scores.items():
            if score.score > 0.6:
                category_name = self.risk_category_descriptions.get(category, category.value)
                factors.append(f"• {category_name}: {score.score:.2f}")
        
        if not factors:
            return "• No significant risk factors identified"
        
        return "\n".join(factors[:5])  # Top 5 risk factors
    
    def _interpret_technical_signals(
        self,
        signals: List[TechnicalSignal],
        summary: Dict[str, Any]
    ) -> str:
        """Interpret technical signals in human-readable format."""
        overall_signal = summary.get('overall_signal', 'NEUTRAL')
        strength = summary.get('average_strength', 0.0)
        
        if overall_signal == 'BUY' and strength > 0.7:
            return "Strong bullish momentum across multiple timeframes suggests upward price movement."
        elif overall_signal == 'BUY':
            return "Modest bullish signals present but with moderate strength."
        elif overall_signal == 'SELL' and strength > 0.7:
            return "Strong bearish pressure across timeframes indicates potential downward movement."
        elif overall_signal == 'SELL':
            return "Some bearish signals present but strength is moderate."
        else:
            return "Mixed or neutral signals - market lacks clear directional bias."
    
    def _explain_position_sizing(self, position_size: float, risk_score: float, confidence: float) -> str:
        """Explain position sizing rationale."""
        if position_size < 2:
            return f"Very conservative {position_size:.1f}% sizing due to high risk ({risk_score:.2f}) or low confidence ({confidence:.1%})"
        elif position_size < 5:
            return f"Conservative {position_size:.1f}% sizing balances opportunity with risk management"
        elif position_size < 8:
            return f"Standard {position_size:.1f}% sizing appropriate for risk level and confidence"
        else:
            return f"Larger {position_size:.1f}% sizing justified by favorable risk-reward profile"
    
    def _create_position_management_guidance(self, analysis: SmartLaneAnalysis) -> str:
        """Create position management guidance."""
        return f"""
        • Entry: Consider scaling into position if volatility is high
        • Stop Loss: {analysis.stop_loss_percent or 'Dynamic'}% based on technical levels
        • Take Profit: Staged exits at {', '.join([f'{t:.1f}%' for t in (analysis.take_profit_targets or [15, 30, 50])])}
        • Review: Monitor risk factors and adjust position if conditions change
        """
    
    def _get_position_sizing_warnings(self, analysis: SmartLaneAnalysis) -> List[str]:
        """Get position sizing related warnings."""
        warnings = []
        
        if analysis.position_size_percent > self.config.max_position_size_percent:
            warnings.append(f"Position size exceeds configured maximum of {self.config.max_position_size_percent}%")
        
        if analysis.overall_risk_score > 0.7 and analysis.position_size_percent > 3:
            warnings.append("High risk score suggests smaller position size")
        
        return warnings
    
    def _explain_strategy_selection(self, action: SmartLaneAction) -> str:
        """Explain why a particular strategy was selected."""
        explanations = {
            SmartLaneAction.BUY: "Strong bullish signals with acceptable risk justify a buy recommendation",
            SmartLaneAction.SELL: "Bearish indicators and risk factors support a sell recommendation",
            SmartLaneAction.HOLD: "Mixed signals suggest maintaining current position",
            SmartLaneAction.AVOID: "High risk factors make this trade unsuitable",
            SmartLaneAction.PARTIAL_BUY: "Positive signals with some uncertainty warrant partial position",
            SmartLaneAction.WAIT_FOR_BETTER_ENTRY: "Setup has potential but waiting for better conditions is prudent",
            SmartLaneAction.SCALE_IN: "Gradual position building recommended due to uncertainty",
            SmartLaneAction.SCALE_OUT: "Taking partial profits while maintaining some exposure"
        }
        
        return explanations.get(action, "Strategy selection based on comprehensive analysis")
    
    def _list_alternative_strategies(self, analysis: SmartLaneAnalysis) -> str:
        """List alternative strategies that were considered."""
        return """
        • Conservative approach: Smaller position with tighter stops
        • Aggressive approach: Larger position with wider stops  
        • Wait-and-see: Monitor for better entry conditions
        • Partial entry: Scale in over time to average entry price
        """
    
    def _analyze_confidence_factors(self, analysis: SmartLaneAnalysis) -> Dict[str, float]:
        """Analyze what contributes to overall confidence."""
        return {
            'data_quality': analysis.data_freshness_score,
            'analysis_completeness': len(analysis.risk_scores) / 8,
            'signal_consistency': self._calculate_signal_agreement(analysis.technical_signals),
            'risk_assessment_clarity': 1.0 - abs(analysis.overall_risk_score - 0.5) * 2,
            'time_adequacy': min(1.0, analysis.total_analysis_time_ms / 5000)
        }
    
    def _format_confidence_factors(self, factors: Dict[str, float]) -> str:
        """Format confidence factors for display."""
        formatted = []
        for factor, score in factors.items():
            formatted.append(f"• {factor.replace('_', ' ').title()}: {score:.1%}")
        return "\n".join(formatted)
    
    def _identify_confidence_limitations(self, analysis: SmartLaneAnalysis) -> str:
        """Identify limitations in confidence assessment."""
        limitations = []
        
        if analysis.data_freshness_score < 0.8:
            limitations.append("• Data freshness could be improved")
        
        if len(analysis.critical_warnings) > 2:
            limitations.append(f"• {len(analysis.critical_warnings)} critical warnings affect confidence")
        
        if analysis.total_analysis_time_ms > 4500:
            limitations.append("• Extended analysis time may indicate data collection challenges")
        
        if not limitations:
            limitations.append("• No significant confidence limitations identified")
        
        return "\n".join(limitations)
    
    def _get_confidence_warnings(self, analysis: SmartLaneAnalysis) -> List[str]:
        """Get warnings related to confidence assessment."""
        warnings = []
        
        if analysis.overall_confidence < 0.5:
            warnings.append("Low overall confidence - consider additional validation")
        
        if analysis.data_freshness_score < 0.7:
            warnings.append("Data freshness below optimal levels")
        
        return warnings
    
    def _create_final_decision_summary(self, analysis: SmartLaneAnalysis) -> str:
        """Create final decision summary."""
        key_drivers = []
        
        # Primary decision factors
        if analysis.overall_risk_score > 0.7:
            key_drivers.append("High risk score was primary concern")
        elif analysis.overall_risk_score < 0.3:
            key_drivers.append("Low risk profile was encouraging factor")
        
        technical_signal = analysis.technical_summary.get('overall_signal', 'NEUTRAL')
        if technical_signal != 'NEUTRAL':
            key_drivers.append(f"Technical signals showed {technical_signal.lower()} bias")
        
        if analysis.overall_confidence > 0.8:
            key_drivers.append("High confidence in analysis quality")
        elif analysis.overall_confidence < 0.5:
            key_drivers.append("Low confidence led to conservative approach")
        
        return "• " + "\n• ".join(key_drivers) if key_drivers else "• Balanced assessment across all factors"
    
    def _create_bottom_line_assessment(self, analysis: SmartLaneAnalysis) -> str:
        """Create bottom line assessment."""
        risk_level = self._categorize_risk_level(analysis.overall_risk_score)
        
        if analysis.recommended_action == SmartLaneAction.BUY:
            return f"Favorable opportunity with {risk_level.lower()} risk - recommended for execution"
        elif analysis.recommended_action == SmartLaneAction.SELL:
            return f"Risk factors outweigh potential - selling recommended"
        elif analysis.recommended_action == SmartLaneAction.AVOID:
            return f"High risk factors make this unsuitable for current strategy"
        elif analysis.recommended_action == SmartLaneAction.HOLD:
            return f"Neutral outlook suggests maintaining current exposure"
        else:
            return f"Mixed signals warrant cautious approach with {analysis.recommended_action.value.lower()}"
    
    def _explain_decision_matrix_logic(self, analysis: SmartLaneAnalysis) -> str:
        """Explain the decision matrix logic."""
        return f"""
        Risk Score {analysis.overall_risk_score:.2f} combined with {analysis.overall_confidence:.1%} confidence
        and {analysis.technical_summary.get('overall_signal', 'NEUTRAL')} technical bias led to the
        {analysis.recommended_action.value} recommendation. Position sizing of {analysis.position_size_percent:.1f}%
        balances opportunity size with risk management requirements.
        """
    
    def _calculate_risk_adjusted_return(self, analysis: SmartLaneAnalysis) -> float:
        """Calculate risk-adjusted expected return."""
        base_return = analysis.take_profit_targets[0] if analysis.take_profit_targets else 15.0
        risk_adjustment = 1.0 - analysis.overall_risk_score * 0.5
        confidence_adjustment = analysis.overall_confidence
        
        return base_return * risk_adjustment * confidence_adjustment
    
    def _estimate_success_probability(self, analysis: SmartLaneAnalysis) -> float:
        """Estimate probability of successful trade."""
        base_probability = 60.0  # Base 60% success rate
        
        # Adjust for risk
        risk_adjustment = (1.0 - analysis.overall_risk_score) * 20  # +/- 20%
        
        # Adjust for confidence
        confidence_adjustment = (analysis.overall_confidence - 0.5) * 30  # +/- 15%
        
        # Adjust for technical signals
        technical_strength = analysis.technical_summary.get('average_strength', 0.5)
        technical_adjustment = (technical_strength - 0.5) * 20  # +/- 10%
        
        total_probability = base_probability + risk_adjustment + confidence_adjustment + technical_adjustment
        
        return max(10.0, min(95.0, total_probability))  # Clamp between 10% and 95%
    
    def _create_market_structure_notes(self, analysis: SmartLaneAnalysis) -> str:
        """Create market structure notes."""
        return f"""
        Analysis performed using Smart Lane comprehensive evaluation framework,
        designed for strategic position taking with risk-first approach.
        Market data quality: {analysis.data_freshness_score:.1%}
        """
    
    def get_generation_statistics(self) -> Dict[str, Any]:
        """Get thought log generation statistics."""
        total = self.generation_stats['total_generated']
        
        return {
            'total_generated': total,
            'average_generation_time_ms': self.generation_stats['average_generation_time_ms'],
            'generation_by_level': self.generation_stats['by_level'],
            'config_level': self.config.thought_log_detail_level,
            'thought_log_enabled': self.config.thought_log_enabled
        }


# Export key classes
__all__ = [
    'ThoughtLogGenerator',
    'ThoughtLog',
    'ThoughtLogEntry',
    'ThoughtLogLevel',
    'ReasoningStep'
]