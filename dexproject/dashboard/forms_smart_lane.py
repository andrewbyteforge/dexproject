"""
Smart Lane Dashboard Forms

Forms for Smart Lane configuration and control in the dashboard interface.
Enables users to configure Smart Lane analysis parameters and view results.

Path: dashboard/forms_smart_lane.py
"""

from django import forms
from django.core.exceptions import ValidationError
from typing import Dict, Any, List
import json


class SmartLaneConfigForm(forms.Form):
    """Form for Smart Lane configuration settings."""
    
    # Analysis Depth
    DEPTH_CHOICES = [
        ('BASIC', 'Basic (Fast ~1s) - Core risk checks only'),
        ('COMPREHENSIVE', 'Comprehensive (Standard ~3-5s) - All risk categories'),
        ('DEEP_DIVE', 'Deep Dive (Thorough ~8-12s) - Extended analysis')
    ]
    
    analysis_depth = forms.ChoiceField(
        choices=DEPTH_CHOICES,
        initial='COMPREHENSIVE',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        help_text='Select the depth of analysis to perform'
    )
    
    # Risk Categories to Enable
    enable_honeypot_detection = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Honeypot Detection',
        help_text='Detect scam tokens and honeypots'
    )
    
    enable_liquidity_analysis = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Liquidity Analysis',
        help_text='Analyze liquidity depth and stability'
    )
    
    enable_social_sentiment = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Social Sentiment',
        help_text='Analyze social media sentiment and community'
    )
    
    enable_technical_analysis = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Technical Analysis',
        help_text='Perform chart pattern and indicator analysis'
    )
    
    enable_contract_security = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Contract Security',
        help_text='Analyze smart contract for vulnerabilities'
    )
    
    enable_holder_distribution = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Holder Distribution',
        help_text='Analyze token holder concentration'
    )
    
    enable_market_structure = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Market Structure',
        help_text='Analyze market manipulation risks'
    )
    
    # AI Thought Log Settings
    THOUGHT_LOG_LEVELS = [
        ('BASIC', 'Basic - Key decisions only'),
        ('DETAILED', 'Detailed - Include reasoning steps'),
        ('COMPREHENSIVE', 'Comprehensive - Full analysis breakdown'),
        ('DEBUG', 'Debug - Include all internal data')
    ]
    
    thought_log_level = forms.ChoiceField(
        choices=THOUGHT_LOG_LEVELS,
        initial='DETAILED',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='AI Thought Log Detail Level',
        help_text='Control the verbosity of AI reasoning explanations'
    )
    
    include_education = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Include Educational Content',
        help_text='Add learning points and market education to thought logs'
    )
    
    # Risk Management Settings
    max_acceptable_risk = forms.FloatField(
        min_value=0.0,
        max_value=1.0,
        initial=0.7,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.05',
            'min': '0',
            'max': '1'
        }),
        label='Maximum Acceptable Risk Score',
        help_text='Trades above this risk score will be rejected (0-1 scale)'
    )
    
    min_confidence_threshold = forms.FloatField(
        min_value=0.0,
        max_value=1.0,
        initial=0.5,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.05',
            'min': '0',
            'max': '1'
        }),
        label='Minimum Confidence Threshold',
        help_text='Minimum confidence required to recommend a trade (0-1 scale)'
    )
    
    # Position Sizing Settings
    enable_dynamic_sizing = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Enable Dynamic Position Sizing',
        help_text='Automatically adjust position sizes based on risk and confidence'
    )
    
    max_position_size_percent = forms.FloatField(
        min_value=0.5,
        max_value=25.0,
        initial=10.0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.5',
            'min': '0.5',
            'max': '25'
        }),
        label='Maximum Position Size (%)',
        help_text='Maximum percentage of portfolio for a single position'
    )
    
    risk_per_trade_percent = forms.FloatField(
        min_value=0.5,
        max_value=5.0,
        initial=2.0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.25',
            'min': '0.5',
            'max': '5'
        }),
        label='Risk Per Trade (%)',
        help_text='Maximum portfolio percentage to risk per trade'
    )
    
    # Technical Analysis Settings
    technical_timeframes = forms.MultipleChoiceField(
        choices=[
            ('1m', '1 Minute'),
            ('5m', '5 Minutes'),
            ('15m', '15 Minutes'),
            ('1h', '1 Hour'),
            ('4h', '4 Hours'),
            ('1d', '1 Day')
        ],
        initial=['5m', '15m', '1h', '4h'],
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label='Technical Analysis Timeframes',
        help_text='Select timeframes for technical analysis'
    )
    
    def clean(self) -> Dict[str, Any]:
        """Validate and clean form data."""
        cleaned_data = super().clean()
        
        # Ensure at least one risk category is enabled
        risk_categories = [
            cleaned_data.get('enable_honeypot_detection'),
            cleaned_data.get('enable_liquidity_analysis'),
            cleaned_data.get('enable_social_sentiment'),
            cleaned_data.get('enable_technical_analysis'),
            cleaned_data.get('enable_contract_security'),
            cleaned_data.get('enable_holder_distribution'),
            cleaned_data.get('enable_market_structure')
        ]
        
        if not any(risk_categories):
            raise ValidationError(
                'At least one risk analysis category must be enabled'
            )
        
        # Validate risk thresholds
        max_risk = cleaned_data.get('max_acceptable_risk')
        min_confidence = cleaned_data.get('min_confidence_threshold')
        
        if max_risk and min_confidence:
            if max_risk < 0.3 and min_confidence > 0.7:
                self.add_error(None,
                    'Very conservative settings detected. This may result in few trading opportunities.'
                )
        
        return cleaned_data
    
    def get_config_dict(self) -> Dict[str, Any]:
        """Convert form data to configuration dictionary."""
        if not self.is_valid():
            raise ValueError("Form must be valid to get configuration")
        
        data = self.cleaned_data
        
        # Build enabled categories list
        enabled_categories = []
        category_mapping = {
            'enable_honeypot_detection': 'HONEYPOT_DETECTION',
            'enable_liquidity_analysis': 'LIQUIDITY_ANALYSIS',
            'enable_social_sentiment': 'SOCIAL_SENTIMENT',
            'enable_technical_analysis': 'TECHNICAL_ANALYSIS',
            'enable_contract_security': 'CONTRACT_SECURITY',
            'enable_holder_distribution': 'HOLDER_DISTRIBUTION',
            'enable_market_structure': 'MARKET_STRUCTURE'
        }
        
        for field, category in category_mapping.items():
            if data.get(field):
                enabled_categories.append(category)
        
        return {
            'analysis_depth': data['analysis_depth'],
            'enabled_categories': enabled_categories,
            'thought_log_detail_level': data['thought_log_level'],
            'include_education': data['include_education'],
            'max_acceptable_risk_score': data['max_acceptable_risk'],
            'min_confidence_threshold': data['min_confidence_threshold'],
            'enable_dynamic_sizing': data['enable_dynamic_sizing'],
            'max_position_size_percent': data['max_position_size_percent'],
            'risk_per_trade_percent': data['risk_per_trade_percent'],
            'technical_timeframes': data.get('technical_timeframes', [])
        }


class SmartLaneAnalysisRequestForm(forms.Form):
    """Form for requesting Smart Lane analysis of a specific token."""
    
    token_address = forms.CharField(
        max_length=42,
        min_length=42,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '0x...',
            'pattern': '^0x[a-fA-F0-9]{40}$'
        }),
        label='Token Address',
        help_text='Enter the token contract address to analyze'
    )
    
    pair_address = forms.CharField(
        max_length=42,
        min_length=42,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '0x... (optional)',
            'pattern': '^0x[a-fA-F0-9]{40}$'
        }),
        label='Pair Address (Optional)',
        help_text='Specific liquidity pair to analyze'
    )
    
    analysis_urgency = forms.ChoiceField(
        choices=[
            ('NORMAL', 'Normal - Use full analysis'),
            ('QUICK', 'Quick - Skip some checks for speed'),
            ('URGENT', 'Urgent - Minimal checks only')
        ],
        initial='NORMAL',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Analysis Urgency',
        help_text='Trade-off between speed and thoroughness'
    )
    
    include_thought_log = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Generate AI Thought Log',
        help_text='Include detailed reasoning explanation'
    )
    
    def clean_token_address(self) -> str:
        """Validate token address format."""
        address = self.cleaned_data['token_address']
        
        if not address.startswith('0x'):
            raise ValidationError('Token address must start with 0x')
        
        if len(address) != 42:
            raise ValidationError('Token address must be 42 characters')
        
        # Check if it's a valid hex string
        try:
            int(address, 16)
        except ValueError:
            raise ValidationError('Token address must be a valid hexadecimal')
        
        return address.lower()
    
    def clean_pair_address(self) -> str:
        """Validate pair address format if provided."""
        address = self.cleaned_data.get('pair_address', '')
        
        if not address:
            return ''
        
        if not address.startswith('0x'):
            raise ValidationError('Pair address must start with 0x')
        
        if len(address) != 42:
            raise ValidationError('Pair address must be 42 characters')
        
        try:
            int(address, 16)
        except ValueError:
            raise ValidationError('Pair address must be a valid hexadecimal')
        
        return address.lower()


class SmartLaneFilterForm(forms.Form):
    """Form for filtering Smart Lane analysis results."""
    
    min_confidence = forms.FloatField(
        min_value=0.0,
        max_value=1.0,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Min',
            'step': '0.1'
        }),
        label='Min Confidence'
    )
    
    max_risk = forms.FloatField(
        min_value=0.0,
        max_value=1.0,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Max',
            'step': '0.1'
        }),
        label='Max Risk'
    )
    
    action_filter = forms.MultipleChoiceField(
        choices=[
            ('BUY', 'Buy'),
            ('SELL', 'Sell'),
            ('HOLD', 'Hold'),
            ('AVOID', 'Avoid')
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Recommended Actions'
    )
    
    date_range = forms.ChoiceField(
        choices=[
            ('1h', 'Last Hour'),
            ('24h', 'Last 24 Hours'),
            ('7d', 'Last 7 Days'),
            ('30d', 'Last 30 Days'),
            ('all', 'All Time')
        ],
        initial='24h',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label='Time Range'
    )