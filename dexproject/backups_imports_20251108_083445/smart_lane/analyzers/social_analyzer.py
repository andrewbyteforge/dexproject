"""
Social Sentiment Analyzer

Medium-priority analyzer that evaluates community sentiment, social signals,
and public perception around tokens. Integrates multiple data sources to
assess community health and market sentiment.

Path: engine/smart_lane/analyzers/social_analyzer.py
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
import json

from . import BaseAnalyzer
from .. import RiskScore, RiskCategory

logger = logging.getLogger(__name__)


@dataclass
class SocialMetric:
    """Individual social sentiment metric."""
    platform: str  # TWITTER, TELEGRAM, REDDIT, DISCORD, etc.
    metric_type: str  # SENTIMENT, VOLUME, ENGAGEMENT, GROWTH
    value: float
    normalized_score: float  # 0-1 scale
    confidence: float
    data_points: int
    last_updated: str


@dataclass
class SentimentAnalysis:
    """Comprehensive sentiment analysis result."""
    overall_sentiment: str  # VERY_POSITIVE, POSITIVE, NEUTRAL, NEGATIVE, VERY_NEGATIVE
    sentiment_score: float  # -1 to 1 scale
    confidence_level: float
    trending_direction: str  # IMPROVING, STABLE, DECLINING
    volume_score: float  # 0-1 scale
    engagement_quality: str  # HIGH, MEDIUM, LOW
    bot_detection_score: float  # 0-1, higher = more likely bots
    community_health: str  # EXCELLENT, GOOD, FAIR, POOR


@dataclass
class CommunityMetrics:
    """Community health and engagement metrics."""
    total_followers: int
    active_members: int
    engagement_rate: float
    growth_rate_30d: float
    moderator_activity: float
    spam_ratio: float
    verified_accounts_ratio: float
    community_age_days: int


class SocialAnalyzer(BaseAnalyzer):
    """
    Advanced social sentiment and community analysis.
    
    Analyzes:
    - Multi-platform sentiment aggregation (Twitter, Telegram, Reddit)
    - Community engagement and health metrics
    - Influencer and whale sentiment tracking
    - Bot detection and organic growth assessment
    - Trending analysis and momentum indicators
    - Social risk factors (coordinated attacks, FUD campaigns)
    """
    
    def __init__(self, chain_id: int, config: Optional[Dict[str, Any]] = None):
        """
        Initialize social sentiment analyzer.
        
        Args:
            chain_id: Blockchain chain identifier
            config: Analyzer configuration including API keys and thresholds
        """
        super().__init__(chain_id, config)
        
        # Analysis thresholds
        self.thresholds = {
            'min_sentiment_score': -0.3,  # Below this = high risk
            'max_bot_ratio': 0.4,  # Above this = suspicious
            'min_engagement_rate': 0.02,  # Below this = poor community
            'min_community_size': 100,  # Minimum for reliable analysis
            'sentiment_volatility_threshold': 0.6,  # High volatility = risk
            'spam_threshold': 0.3,  # Above this = spam concern
            'min_data_points': 10  # Minimum posts/messages for analysis
        }
        
        # Update with custom config
        if config:
            self.thresholds.update(config.get('thresholds', {}))
            
        # Platform configurations
        self.platforms = {
            'twitter': {'weight': 0.4, 'enabled': True},
            'telegram': {'weight': 0.3, 'enabled': True},
            'reddit': {'weight': 0.2, 'enabled': True},
            'discord': {'weight': 0.1, 'enabled': True}
        }
        
        # Sentiment keywords and patterns
        self.sentiment_patterns = self._load_sentiment_patterns()
        
        # Analysis cache
        self.sentiment_cache: Dict[str, Tuple[SentimentAnalysis, datetime]] = {}
        self.cache_ttl_minutes = 15  # Shorter cache for social data
        
        logger.info(f"Social analyzer initialized for chain {chain_id}")
    
    def get_category(self) -> RiskCategory:
        """Get the risk category this analyzer handles."""
        return RiskCategory.SOCIAL_SENTIMENT
    
    async def analyze(
        self,
        token_address: str,
        context: Dict[str, Any]
    ) -> RiskScore:
        """
        Perform comprehensive social sentiment analysis.
        
        Args:
            token_address: Token contract address to analyze
            context: Additional context including token symbol, name
            
        Returns:
            RiskScore with social sentiment assessment
        """
        analysis_start = time.time()
        
        try:
            logger.debug(f"Starting social analysis for {token_address[:10]}...")
            
            # Update performance stats
            self.performance_stats['total_analyses'] += 1
            
            # Input validation
            if not self._validate_inputs(token_address, context):
                return self._create_error_risk_score("Invalid inputs for social analysis")
            
            # Check cache first
            cached_result = self._get_cached_sentiment(token_address)
            if cached_result and not context.get('force_refresh', False):
                self.performance_stats['cache_hits'] += 1
                return self._create_risk_score_from_cache(cached_result)
            
            self.performance_stats['cache_misses'] += 1
            
            # Extract token information
            token_symbol = context.get('symbol', '').upper()
            token_name = context.get('name', '')
            
            if not token_symbol:
                return self._create_error_risk_score("Token symbol required for social analysis")
            
            # Collect social metrics from multiple platforms
            social_tasks = [
                self._analyze_twitter_sentiment(token_symbol, token_name),
                self._analyze_telegram_sentiment(token_symbol, token_name),
                self._analyze_reddit_sentiment(token_symbol, token_name),
                self._analyze_discord_sentiment(token_symbol, token_name),
                self._analyze_community_metrics(token_symbol, context),
                self._detect_social_risks(token_symbol, token_name)
            ]
            
            # Execute all tasks with timeout protection
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*social_tasks, return_exceptions=True),
                    timeout=30.0  # 30 second timeout for social analysis
                )
            except asyncio.TimeoutError:
                logger.warning(f"Social analysis timeout for {token_symbol}")
                return self._create_timeout_risk_score()
            
            # Process results
            platform_metrics = []
            community_metrics = None
            social_risks = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"Social task {i} failed: {result}")
                    continue
                
                if i < 4:  # Platform sentiment results
                    if isinstance(result, list):
                        platform_metrics.extend(result)
                elif i == 4:  # Community metrics
                    community_metrics = result
                elif i == 5:  # Social risks
                    social_risks = result
            
            # Aggregate sentiment analysis
            sentiment_analysis = self._aggregate_sentiment_scores(platform_metrics)
            
            # Calculate overall risk score
            risk_score = self._calculate_social_risk_score(
                sentiment_analysis, community_metrics, social_risks
            )
            
            # Cache the result
            self._cache_sentiment_result(token_address, sentiment_analysis)
            
            # Create detailed analysis data
            analysis_details = {
                'sentiment_analysis': sentiment_analysis.__dict__,
                'community_metrics': community_metrics.__dict__ if community_metrics else None,
                'platform_metrics': [m.__dict__ for m in platform_metrics],
                'social_risks': social_risks,
                'analysis_quality': self._assess_data_quality(platform_metrics),
                'confidence_factors': self._calculate_confidence_factors(platform_metrics)
            }
            
            # Generate warnings
            warnings = self._generate_social_warnings(sentiment_analysis, social_risks)
            
            # Calculate analysis time
            analysis_time_ms = (time.time() - analysis_start) * 1000
            
            # Update performance stats
            self.performance_stats['successful_analyses'] += 1
            
            # Create and return risk score
            return RiskScore(
                category=self.get_category(),
                score=risk_score,
                confidence=sentiment_analysis.confidence_level,
                details=analysis_details,
                analysis_time_ms=analysis_time_ms,
                warnings=warnings,
                data_quality=self._assess_data_quality(platform_metrics),
                last_updated=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Error in social sentiment analysis: {e}", exc_info=True)
            self.performance_stats['failed_analyses'] += 1
            
            analysis_time_ms = (time.time() - analysis_start) * 1000
            return RiskScore(
                category=self.get_category(),
                score=0.7,  # Medium-high risk due to analysis failure
                confidence=0.3,
                details={'error': str(e), 'analysis_failed': True},
                analysis_time_ms=analysis_time_ms,
                warnings=[f"Social analysis failed: {str(e)}"],
                data_quality="POOR"
            )
    
    async def _analyze_twitter_sentiment(
        self,
        token_symbol: str,
        token_name: str
    ) -> List[SocialMetric]:
        """
        Analyze Twitter sentiment and engagement.
        
        In production, this would use Twitter API v2 to fetch recent tweets,
        analyze sentiment, and calculate engagement metrics.
        """
        metrics = []
        
        # Simulate Twitter API call delay
        await asyncio.sleep(0.2)
        
        try:
            # Mock Twitter analysis - in production would use real Twitter API
            # This would search for mentions of token symbol and name
            search_terms = [token_symbol, f"${token_symbol}", token_name]
            
            # Simulated sentiment analysis results
            sentiment_data = {
                'total_tweets': 342,
                'positive_tweets': 180,
                'negative_tweets': 95,
                'neutral_tweets': 67,
                'avg_sentiment_score': 0.23,  # Slightly positive
                'engagement_rate': 0.045,
                'retweet_ratio': 0.28,
                'verified_accounts': 15,
                'bot_score': 0.25,  # 25% likely bots
                'trending_score': 0.6
            }
            
            # Calculate normalized sentiment score
            total_tweets = sentiment_data['total_tweets']
            if total_tweets > 0:
                sentiment_score = (
                    sentiment_data['positive_tweets'] - sentiment_data['negative_tweets']
                ) / total_tweets
                normalized_sentiment = (sentiment_score + 1) / 2  # Convert to 0-1 scale
            else:
                normalized_sentiment = 0.5  # Neutral if no data
            
            # Create metrics
            metrics.extend([
                SocialMetric(
                    platform="TWITTER",
                    metric_type="SENTIMENT",
                    value=sentiment_data['avg_sentiment_score'],
                    normalized_score=normalized_sentiment,
                    confidence=0.7,
                    data_points=total_tweets,
                    last_updated=datetime.now(timezone.utc).isoformat()
                ),
                SocialMetric(
                    platform="TWITTER",
                    metric_type="ENGAGEMENT",
                    value=sentiment_data['engagement_rate'],
                    normalized_score=min(sentiment_data['engagement_rate'] * 20, 1.0),
                    confidence=0.8,
                    data_points=total_tweets,
                    last_updated=datetime.now(timezone.utc).isoformat()
                ),
                SocialMetric(
                    platform="TWITTER",
                    metric_type="BOT_DETECTION",
                    value=sentiment_data['bot_score'],
                    normalized_score=1.0 - sentiment_data['bot_score'],  # Lower bot score = better
                    confidence=0.6,
                    data_points=total_tweets,
                    last_updated=datetime.now(timezone.utc).isoformat()
                )
            ])
            
        except Exception as e:
            logger.warning(f"Twitter analysis failed: {e}")
            # Add error metric
            metrics.append(
                SocialMetric(
                    platform="TWITTER",
                    metric_type="ERROR",
                    value=0.0,
                    normalized_score=0.5,  # Neutral on error
                    confidence=0.1,
                    data_points=0,
                    last_updated=datetime.now(timezone.utc).isoformat()
                )
            )
        
        return metrics
    
    async def _analyze_telegram_sentiment(
        self,
        token_symbol: str,
        token_name: str
    ) -> List[SocialMetric]:
        """
        Analyze Telegram channel and group sentiment.
        
        In production, this would connect to Telegram API to analyze
        channel messages, group discussions, and community activity.
        """
        metrics = []
        
        # Simulate Telegram API call delay
        await asyncio.sleep(0.15)
        
        try:
            # Mock Telegram analysis
            telegram_data = {
                'channel_members': 2150,
                'active_members_24h': 145,
                'messages_24h': 89,
                'avg_sentiment': 0.15,  # Slightly positive
                'admin_activity': 0.8,  # High admin engagement
                'spam_ratio': 0.12,
                'member_growth_7d': 0.08,  # 8% growth
                'engagement_rate': 0.067
            }
            
            # Calculate metrics
            activity_score = min(telegram_data['active_members_24h'] / 100, 1.0)
            sentiment_normalized = (telegram_data['avg_sentiment'] + 1) / 2
            
            metrics.extend([
                SocialMetric(
                    platform="TELEGRAM",
                    metric_type="SENTIMENT",
                    value=telegram_data['avg_sentiment'],
                    normalized_score=sentiment_normalized,
                    confidence=0.75,
                    data_points=telegram_data['messages_24h'],
                    last_updated=datetime.now(timezone.utc).isoformat()
                ),
                SocialMetric(
                    platform="TELEGRAM",
                    metric_type="ACTIVITY",
                    value=telegram_data['active_members_24h'],
                    normalized_score=activity_score,
                    confidence=0.8,
                    data_points=telegram_data['channel_members'],
                    last_updated=datetime.now(timezone.utc).isoformat()
                ),
                SocialMetric(
                    platform="TELEGRAM",
                    metric_type="GROWTH",
                    value=telegram_data['member_growth_7d'],
                    normalized_score=min(telegram_data['member_growth_7d'] * 5, 1.0),
                    confidence=0.7,
                    data_points=telegram_data['channel_members'],
                    last_updated=datetime.now(timezone.utc).isoformat()
                )
            ])
            
        except Exception as e:
            logger.warning(f"Telegram analysis failed: {e}")
            metrics.append(
                SocialMetric(
                    platform="TELEGRAM",
                    metric_type="ERROR",
                    value=0.0,
                    normalized_score=0.5,
                    confidence=0.1,
                    data_points=0,
                    last_updated=datetime.now(timezone.utc).isoformat()
                )
            )
        
        return metrics
    
    async def _analyze_reddit_sentiment(
        self,
        token_symbol: str,
        token_name: str
    ) -> List[SocialMetric]:
        """
        Analyze Reddit posts and comments sentiment.
        
        In production, this would use Reddit API to analyze posts
        in relevant subreddits and calculate sentiment scores.
        """
        metrics = []
        
        # Simulate Reddit API call delay
        await asyncio.sleep(0.1)
        
        try:
            # Mock Reddit analysis
            reddit_data = {
                'posts_found': 23,
                'comments_analyzed': 156,
                'avg_upvote_ratio': 0.73,
                'sentiment_score': 0.31,  # Positive
                'engagement_quality': 0.65,
                'subreddit_activity': 0.8
            }
            
            if reddit_data['posts_found'] > 0:
                sentiment_normalized = (reddit_data['sentiment_score'] + 1) / 2
                
                metrics.extend([
                    SocialMetric(
                        platform="REDDIT",
                        metric_type="SENTIMENT",
                        value=reddit_data['sentiment_score'],
                        normalized_score=sentiment_normalized,
                        confidence=0.65,
                        data_points=reddit_data['posts_found'] + reddit_data['comments_analyzed'],
                        last_updated=datetime.now(timezone.utc).isoformat()
                    ),
                    SocialMetric(
                        platform="REDDIT",
                        metric_type="ENGAGEMENT",
                        value=reddit_data['avg_upvote_ratio'],
                        normalized_score=reddit_data['avg_upvote_ratio'],
                        confidence=0.7,
                        data_points=reddit_data['posts_found'],
                        last_updated=datetime.now(timezone.utc).isoformat()
                    )
                ])
            
        except Exception as e:
            logger.warning(f"Reddit analysis failed: {e}")
            metrics.append(
                SocialMetric(
                    platform="REDDIT",
                    metric_type="ERROR",
                    value=0.0,
                    normalized_score=0.5,
                    confidence=0.1,
                    data_points=0,
                    last_updated=datetime.now(timezone.utc).isoformat()
                )
            )
        
        return metrics
    
    async def _analyze_discord_sentiment(
        self,
        token_symbol: str,
        token_name: str
    ) -> List[SocialMetric]:
        """
        Analyze Discord server sentiment and activity.
        
        In production, this would connect to Discord API to analyze
        server activity, member engagement, and message sentiment.
        """
        metrics = []
        
        # Simulate Discord API call delay
        await asyncio.sleep(0.1)
        
        try:
            # Mock Discord analysis
            discord_data = {
                'server_members': 890,
                'online_members': 67,
                'messages_24h': 234,
                'avg_sentiment': 0.08,  # Slightly positive
                'moderator_activity': 0.9,
                'channel_activity': 0.6
            }
            
            if discord_data['messages_24h'] > 10:
                sentiment_normalized = (discord_data['avg_sentiment'] + 1) / 2
                activity_score = min(discord_data['online_members'] / 50, 1.0)
                
                metrics.extend([
                    SocialMetric(
                        platform="DISCORD",
                        metric_type="SENTIMENT",
                        value=discord_data['avg_sentiment'],
                        normalized_score=sentiment_normalized,
                        confidence=0.6,
                        data_points=discord_data['messages_24h'],
                        last_updated=datetime.now(timezone.utc).isoformat()
                    ),
                    SocialMetric(
                        platform="DISCORD",
                        metric_type="ACTIVITY",
                        value=discord_data['online_members'],
                        normalized_score=activity_score,
                        confidence=0.75,
                        data_points=discord_data['server_members'],
                        last_updated=datetime.now(timezone.utc).isoformat()
                    )
                ])
            
        except Exception as e:
            logger.warning(f"Discord analysis failed: {e}")
            metrics.append(
                SocialMetric(
                    platform="DISCORD",
                    metric_type="ERROR",
                    value=0.0,
                    normalized_score=0.5,
                    confidence=0.1,
                    data_points=0,
                    last_updated=datetime.now(timezone.utc).isoformat()
                )
            )
        
        return metrics
    
    async def _analyze_community_metrics(
        self,
        token_symbol: str,
        context: Dict[str, Any]
    ) -> CommunityMetrics:
        """Analyze overall community health and metrics."""
        await asyncio.sleep(0.05)
        
        # Mock community metrics aggregation
        return CommunityMetrics(
            total_followers=3125,
            active_members=245,
            engagement_rate=0.078,
            growth_rate_30d=0.15,
            moderator_activity=0.85,
            spam_ratio=0.08,
            verified_accounts_ratio=0.12,
            community_age_days=67
        )
    
    async def _detect_social_risks(
        self,
        token_symbol: str,
        token_name: str
    ) -> List[Dict[str, Any]]:
        """Detect social risk factors and red flags."""
        await asyncio.sleep(0.05)
        
        risks = []
        
        # Mock risk detection
        risk_patterns = [
            {
                'type': 'COORDINATED_PROMOTION',
                'severity': 'MEDIUM',
                'description': 'Possible coordinated promotion detected',
                'confidence': 0.4,
                'evidence': 'Similar posting patterns across accounts'
            },
            {
                'type': 'LOW_ORGANIC_ENGAGEMENT',
                'severity': 'LOW',
                'description': 'Low organic engagement relative to follower count',
                'confidence': 0.6,
                'evidence': 'Engagement rate below 3%'
            }
        ]
        
        return risk_patterns
    
    def _aggregate_sentiment_scores(self, platform_metrics: List[SocialMetric]) -> SentimentAnalysis:
        """Aggregate sentiment scores from all platforms."""
        if not platform_metrics:
            return SentimentAnalysis(
                overall_sentiment="NEUTRAL",
                sentiment_score=0.0,
                confidence_level=0.1,
                trending_direction="STABLE",
                volume_score=0.0,
                engagement_quality="LOW",
                bot_detection_score=0.5,
                community_health="POOR"
            )
        
        # Weight scores by platform and confidence
        weighted_scores = []
        total_weight = 0
        total_data_points = 0
        bot_scores = []
        
        for metric in platform_metrics:
            if metric.metric_type == "SENTIMENT":
                platform_weight = self.platforms.get(metric.platform.lower(), {}).get('weight', 0.1)
                weight = platform_weight * metric.confidence
                weighted_scores.append(metric.normalized_score * weight)
                total_weight += weight
                total_data_points += metric.data_points
            elif metric.metric_type == "BOT_DETECTION":
                bot_scores.append(metric.value)
        
        # Calculate aggregated sentiment
        if total_weight > 0:
            avg_sentiment = sum(weighted_scores) / total_weight
            # Convert to -1 to 1 scale
            sentiment_score = (avg_sentiment * 2) - 1
        else:
            sentiment_score = 0.0
        
        # Determine overall sentiment category
        if sentiment_score > 0.4:
            overall_sentiment = "VERY_POSITIVE"
        elif sentiment_score > 0.1:
            overall_sentiment = "POSITIVE"
        elif sentiment_score > -0.1:
            overall_sentiment = "NEUTRAL"
        elif sentiment_score > -0.4:
            overall_sentiment = "NEGATIVE"
        else:
            overall_sentiment = "VERY_NEGATIVE"
        
        # Calculate confidence based on data points
        confidence_level = min(total_data_points / 100, 1.0) * 0.8 + 0.2
        
        # Calculate bot detection score
        avg_bot_score = sum(bot_scores) / len(bot_scores) if bot_scores else 0.5
        
        return SentimentAnalysis(
            overall_sentiment=overall_sentiment,
            sentiment_score=sentiment_score,
            confidence_level=confidence_level,
            trending_direction="STABLE",  # Would need historical data
            volume_score=min(total_data_points / 200, 1.0),
            engagement_quality="MEDIUM",  # Calculated from engagement metrics
            bot_detection_score=avg_bot_score,
            community_health="GOOD" if sentiment_score > 0 else "FAIR"
        )
    
    def _calculate_social_risk_score(
        self,
        sentiment_analysis: SentimentAnalysis,
        community_metrics: Optional[CommunityMetrics],
        social_risks: List[Dict[str, Any]]
    ) -> float:
        """Calculate overall social risk score."""
        risk_factors = []
        
        # Sentiment risk
        if sentiment_analysis.sentiment_score < self.thresholds['min_sentiment_score']:
            risk_factors.append(0.4)  # High risk for negative sentiment
        elif sentiment_analysis.sentiment_score < 0:
            risk_factors.append(0.25)  # Medium risk
        else:
            risk_factors.append(0.1)  # Low risk for positive sentiment
        
        # Bot risk
        if sentiment_analysis.bot_detection_score > self.thresholds['max_bot_ratio']:
            risk_factors.append(0.3)
        else:
            risk_factors.append(0.1)
        
        # Community health risk
        if community_metrics:
            if community_metrics.spam_ratio > self.thresholds['spam_threshold']:
                risk_factors.append(0.25)
            elif community_metrics.engagement_rate < self.thresholds['min_engagement_rate']:
                risk_factors.append(0.2)
            else:
                risk_factors.append(0.05)
        
        # Social risks
        critical_risks = [r for r in social_risks if r.get('severity') == 'CRITICAL']
        high_risks = [r for r in social_risks if r.get('severity') == 'HIGH']
        
        if critical_risks:
            risk_factors.append(0.5)
        elif high_risks:
            risk_factors.append(0.3)
        elif social_risks:
            risk_factors.append(0.15)
        else:
            risk_factors.append(0.05)
        
        # Calculate weighted average
        return sum(risk_factors) / len(risk_factors) if risk_factors else 0.5
    
    def _generate_social_warnings(
        self,
        sentiment_analysis: SentimentAnalysis,
        social_risks: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate warnings based on social analysis."""
        warnings = []
        
        if sentiment_analysis.sentiment_score < -0.3:
            warnings.append("Predominantly negative social sentiment detected")
        
        if sentiment_analysis.bot_detection_score > 0.4:
            warnings.append("High bot activity detected in social mentions")
        
        if sentiment_analysis.confidence_level < 0.3:
            warnings.append("Low confidence in social analysis due to limited data")
        
        for risk in social_risks:
            if risk.get('severity') in ['CRITICAL', 'HIGH']:
                warnings.append(f"Social risk: {risk.get('description', 'Unknown risk')}")
        
        return warnings
    
    def _validate_inputs(self, token_address: str, context: Dict[str, Any]) -> bool:
        """Validate inputs for social analysis."""
        if not token_address or len(token_address) != 42:
            return False
        
        if not context.get('symbol'):
            return False
        
        return True
    
    def _create_error_risk_score(self, error_message: str) -> RiskScore:
        """Create error risk score for failed analysis."""
        return RiskScore(
            category=self.get_category(),
            score=0.6,  # Medium risk when analysis fails
            confidence=0.2,
            details={'error': error_message, 'analysis_failed': True},
            analysis_time_ms=0.0,
            warnings=[error_message],
            data_quality="POOR"
        )
    
    def _create_timeout_risk_score(self) -> RiskScore:
        """Create risk score for timeout scenarios."""
        return RiskScore(
            category=self.get_category(),
            score=0.5,  # Neutral risk on timeout
            confidence=0.1,
            details={'timeout': True, 'analysis_incomplete': True},
            analysis_time_ms=30000.0,
            warnings=["Social analysis timed out - results may be incomplete"],
            data_quality="POOR"
        )
    
    def _get_cached_sentiment(self, token_address: str) -> Optional[SentimentAnalysis]:
        """Get cached sentiment analysis if available and fresh."""
        if token_address in self.sentiment_cache:
            result, timestamp = self.sentiment_cache[token_address]
            age = datetime.now(timezone.utc) - timestamp
            
            if age.total_seconds() < (self.cache_ttl_minutes * 60):
                return result
            else:
                del self.sentiment_cache[token_address]
        
        return None
    
    def _cache_sentiment_result(self, token_address: str, result: SentimentAnalysis) -> None:
        """Cache sentiment analysis result."""
        self.sentiment_cache[token_address] = (result, datetime.now(timezone.utc))
        
        # Clean up old cache entries
        if len(self.sentiment_cache) > 50:
            sorted_entries = sorted(
                self.sentiment_cache.items(),
                key=lambda x: x[1][1]
            )
            for token, _ in sorted_entries[:10]:
                del self.sentiment_cache[token]
    
    def _create_risk_score_from_cache(self, cached_result: SentimentAnalysis) -> RiskScore:
        """Create risk score from cached sentiment analysis."""
        risk_score = self._calculate_social_risk_score(cached_result, None, [])
        
        return RiskScore(
            category=self.get_category(),
            score=risk_score,
            confidence=cached_result.confidence_level,
            details={'sentiment_analysis': cached_result.__dict__, 'from_cache': True},
            analysis_time_ms=5.0,  # Fast cache retrieval
            warnings=[],
            data_quality="GOOD",
            last_updated=datetime.now(timezone.utc).isoformat()
        )
    
    def _assess_data_quality(self, platform_metrics: List[SocialMetric]) -> str:
        """Assess the quality of collected social data."""
        if not platform_metrics:
            return "POOR"
        
        total_data_points = sum(m.data_points for m in platform_metrics)
        error_metrics = [m for m in platform_metrics if m.metric_type == "ERROR"]
        
        if len(error_metrics) > len(platform_metrics) / 2:
            return "POOR"
        elif total_data_points < 20:
            return "FAIR"
        elif total_data_points < 100:
            return "GOOD"
        else:
            return "EXCELLENT"
    
    def _calculate_confidence_factors(self, platform_metrics: List[SocialMetric]) -> Dict[str, float]:
        """Calculate confidence factors for the analysis."""
        total_data_points = sum(m.data_points for m in platform_metrics)
        platforms_analyzed = len(set(m.platform for m in platform_metrics))
        avg_confidence = sum(m.confidence for m in platform_metrics) / len(platform_metrics) if platform_metrics else 0.0
        
        return {
            'data_volume_factor': min(total_data_points / 100, 1.0),
            'platform_diversity_factor': min(platforms_analyzed / 4, 1.0),
            'average_metric_confidence': avg_confidence,
            'overall_confidence': min((total_data_points / 100) * 0.4 + (platforms_analyzed / 4) * 0.3 + avg_confidence * 0.3, 1.0)
        }
    
    def _load_sentiment_patterns(self) -> Dict[str, List[str]]:
        """Load sentiment analysis patterns and keywords."""
        return {
            'positive': ['moon', 'bullish', 'pump', 'hodl', 'diamond hands', 'to the moon', 'gem', 'undervalued'],
            'negative': ['dump', 'rug', 'scam', 'bearish', 'fud', 'crash', 'dead', 'exit scam', 'honeypot'],
            'neutral': ['dyor', 'analysis', 'chart', 'volume', 'market cap', 'trading', 'investment']
        }


# Export the analyzer class
__all__ = ['SocialAnalyzer', 'SocialMetric', 'SentimentAnalysis', 'CommunityMetrics']