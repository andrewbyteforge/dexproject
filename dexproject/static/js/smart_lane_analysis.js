/**
 * Smart Lane Analysis JavaScript
 * 
 * Provides interactive functionality for AI-powered token analysis
 * with proper thought log fetching and comprehensive error handling
 * 
 * File: dexproject/static/js/smart_lane_analysis.js
 */

'use strict';

// ============================================================================
// SMART LANE ANALYSIS MODULE
// ============================================================================

const SmartLaneAnalysis = {
    // Polling interval reference
    thoughtLogInterval: null,
    thoughtLogPollCount: 0,
    maxPollAttempts: 15, // Poll for max 30 seconds (15 * 2 seconds)

    /**
     * Initialize the Smart Lane Analysis page
     */
    init: function () {
        console.log('Initializing Smart Lane Analysis...');

        // Mark page for trading functionality
        document.body.dataset.page = 'smart-lane';

        // Initialize analysis functionality
        this.initializeSmartLaneAnalysis();

        console.log('Smart Lane Analysis initialized');
    },

    /**
     * Main initialization function
     */
    initializeSmartLaneAnalysis: function () {
        const form = document.getElementById('analysis-form');

        if (form) {
            form.addEventListener('submit', this.handleFormSubmit.bind(this));
        }

        // Auto-fill token address from URL if provided
        this.autoFillTokenFromURL();

        // Setup execution button handlers
        this.setupExecutionButtons();
    },

    /**
     * Handle form submission
     */
    handleFormSubmit: function (e) {
        e.preventDefault();
        this.startAnalysis();
    },

    /**
     * Auto-fill token address from URL parameters
     */
    autoFillTokenFromURL: function () {
        const urlParams = new URLSearchParams(window.location.search);
        const tokenAddress = urlParams.get('token');

        if (tokenAddress) {
            const tokenInput = document.getElementById('token_address');
            if (tokenInput) {
                tokenInput.value = tokenAddress;
            }
        }
    },

    /**
     * Setup execution button event handlers
     */
    setupExecutionButtons: function () {
        const buyBtn = document.getElementById('execute-buy-btn');
        const sellBtn = document.getElementById('execute-sell-btn');
        const manualBtn = document.getElementById('manual-trade-btn');

        if (buyBtn) {
            buyBtn.addEventListener('click', this.handleExecuteTradeClick.bind(this));
        }

        if (sellBtn) {
            sellBtn.addEventListener('click', this.handleExecuteTradeClick.bind(this));
        }

        if (manualBtn) {
            manualBtn.addEventListener('click', this.showManualTradeModal.bind(this));
        }
    },

    /**
     * Handle execute trade button clicks
     */
    handleExecuteTradeClick: function (e) {
        const button = e.currentTarget;
        const action = button.dataset.action;
        const tokenAddress = button.dataset.tokenAddress;
        const amount = button.dataset.amount;

        if (!tokenAddress) {
            this.showNotification('Token address not available', 'warning');
            return;
        }

        this.executeTradeFromAnalysis(action, tokenAddress, amount);
    }
};

// ============================================================================
// ANALYSIS FUNCTIONS
// ============================================================================

/**
 * Start Smart Lane analysis process
 * FIXED: Using correct endpoint and properly handling the response
 */
SmartLaneAnalysis.startAnalysis = async function () {
    const form = document.getElementById('analysis-form');
    const formData = new FormData(form);

    // Validate form
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }

    const analysisData = {
        token_address: formData.get('token_address'),
        config: {
            analysis_depth: formData.get('analysis_depth') || 'COMPREHENSIVE',
            position_size: parseFloat(formData.get('position_size')) || 0.1,
            analyzers: {
                honeypot_detection: document.getElementById('honeypot_check')?.checked !== false,
                liquidity_analysis: document.getElementById('liquidity_check')?.checked !== false,
                social_sentiment: document.getElementById('social_check')?.checked !== false,
                technical_analysis: document.getElementById('technical_check')?.checked !== false,
                contract_security: document.getElementById('contract_check')?.checked !== false,
                market_structure: document.getElementById('market_check')?.checked !== false
            }
        }
    };

    console.log('Starting analysis with data:', analysisData);

    try {
        // Show loading state
        this.showLoadingState();

        // FIXED: Use correct API endpoint
        const response = await fetch('/dashboard/api/smart-lane/analyze/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
            },
            body: JSON.stringify(analysisData)
        });

        console.log('Analysis response status:', response.status);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const result = await response.json();
        console.log('Analysis result:', result);

        if (result.success) {
            const analysis = result.analysis;

            // Display initial results
            this.displayAnalysisResults(analysis);

            // CRITICAL FIX: Start polling for thought log updates
            if (analysis.analysis_id || analysis.thought_log_id) {
                const thoughtLogId = analysis.thought_log_id || analysis.analysis_id;
                console.log('Starting thought log polling for analysis:', thoughtLogId);

                // Start polling for thought log updates
                this.startThoughtLogPolling(thoughtLogId);
            } else {
                console.warn('No analysis_id or thought_log_id in response');
            }

            // Monitor analysis progress if still in progress
            if (analysis.status === 'IN_PROGRESS') {
                this.monitorAnalysisProgress(analysis.analysis_id);
            }
        } else {
            throw new Error(result.error || 'Analysis failed');
        }

    } catch (error) {
        console.error('Analysis error:', error);
        this.hideLoadingState();
        this.showNotification(`Analysis failed: ${error.message}`, 'error');
    }
};

/**
 * Start polling for thought log updates
 * NEW FUNCTION: Polls for thought log updates every 2 seconds
 */
SmartLaneAnalysis.startThoughtLogPolling = function (analysisId) {
    if (!analysisId) {
        console.warn('No analysis ID provided for thought log polling');
        return;
    }

    // Reset poll count
    this.thoughtLogPollCount = 0;

    // Clear any existing interval
    this.stopThoughtLogPolling();

    console.log('Starting thought log polling for analysis:', analysisId);

    // Initial fetch
    this.fetchThoughtLog(analysisId);

    // Set up polling interval (every 2 seconds)
    this.thoughtLogInterval = setInterval(() => {
        this.thoughtLogPollCount++;

        // Check if we've reached max poll attempts
        if (this.thoughtLogPollCount >= this.maxPollAttempts) {
            console.log('Max poll attempts reached, stopping thought log polling');
            this.stopThoughtLogPolling();
            return;
        }

        console.log(`Polling thought log (attempt ${this.thoughtLogPollCount}/${this.maxPollAttempts})`);
        this.fetchThoughtLog(analysisId);
    }, 2000);

    // Also stop polling after 30 seconds as a safety measure
    setTimeout(() => {
        if (this.thoughtLogInterval) {
            console.log('Timeout reached, stopping thought log polling');
            this.stopThoughtLogPolling();
        }
    }, 30000);
};

/**
 * Stop polling for thought log updates
 * NEW FUNCTION: Cleans up the polling interval
 */
SmartLaneAnalysis.stopThoughtLogPolling = function () {
    if (this.thoughtLogInterval) {
        console.log('Stopping thought log polling');
        clearInterval(this.thoughtLogInterval);
        this.thoughtLogInterval = null;
        this.thoughtLogPollCount = 0;
    }
};

/**
 * Fetch thought log for a specific analysis
 * ENHANCED: Now supports being called multiple times for polling
 */
SmartLaneAnalysis.fetchThoughtLog = async function (analysisId) {
    if (!analysisId) {
        console.warn('No analysis ID provided for thought log fetch');
        return;
    }

    console.log('Fetching thought log for analysis:', analysisId);

    const url = `/dashboard/api/smart-lane/thought-log/${analysisId}/`;

    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            }
        });

        console.log('Thought log response status:', response.status);

        if (!response.ok) {
            throw new Error(`Failed to fetch thought log: ${response.status}`);
        }

        const data = await response.json();
        console.log('Thought log response data:', data);

        if (data.success && data.thought_log) {
            // Update the thought log display with actual data
            this.updateThoughtLog(data.thought_log);
            console.log('Thought log updated successfully');

            // Check if thought log looks complete and stop polling if so
            if (this.isThoughtLogComplete(data.thought_log)) {
                console.log('Thought log appears complete, stopping polling');
                this.stopThoughtLogPolling();
            }
        } else {
            console.warn('No thought log data received:', data);
            // Show placeholder if no data
            this.updateThoughtLog([]);
        }

    } catch (error) {
        console.error('Error fetching thought log:', error);
        // Show error state in UI
        const container = document.getElementById('thought-log');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-4 text-danger">
                    <i class="bi bi-exclamation-triangle display-4 d-block mb-3"></i>
                    <p>Failed to load AI reasoning</p>
                    <small>${error.message}</small>
                </div>
            `;
        }
    }
};

/**
 * Check if thought log appears to be complete
 * NEW FUNCTION: Determines if we should stop polling
 */
SmartLaneAnalysis.isThoughtLogComplete = function (thoughtLog) {
    if (!thoughtLog || !Array.isArray(thoughtLog)) {
        return false;
    }

    // Check if we have a final decision step
    const hasFinalDecision = thoughtLog.some(thought => {
        const category = (thought.category || '').toLowerCase();
        const content = (thought.thought || thought.reasoning || '').toLowerCase();
        return category.includes('final') ||
            category.includes('decision') ||
            content.includes('final decision') ||
            content.includes('recommendation');
    });

    // If we have more than 5 steps and a final decision, consider it complete
    return thoughtLog.length > 5 && hasFinalDecision;
};

/**
 * Show loading state with progress simulation
 * ENHANCED: Added loading state for thought log and cleanup on unmount
 */
SmartLaneAnalysis.showLoadingState = function () {
    // Stop any existing polling when starting new analysis
    this.stopThoughtLogPolling();

    const initialState = document.getElementById('initial-state');
    const analysisResults = document.getElementById('analysis-results');
    const loadingOverlay = document.getElementById('loading-overlay');

    if (initialState) initialState.style.display = 'none';
    if (analysisResults) analysisResults.style.display = 'block';
    if (loadingOverlay) loadingOverlay.style.display = 'flex';

    // Reset thought log to loading state
    const thoughtLogContainer = document.getElementById('thought-log');
    if (thoughtLogContainer) {
        thoughtLogContainer.innerHTML = `
            <div class="text-center py-4 text-muted">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p>Generating AI reasoning...</p>
            </div>
        `;
    }

    // Disable form
    const analyzeBtn = document.getElementById('analyze-btn');
    if (analyzeBtn) {
        analyzeBtn.disabled = true;
        analyzeBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Analyzing...';
    }

    // Simulate loading progress
    this.simulateLoadingProgress();
};

/**
 * Hide loading state and restore form
 * ENHANCED: Stops polling when hiding loading state
 */
SmartLaneAnalysis.hideLoadingState = function () {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'none';
    }

    // Re-enable form
    const analyzeBtn = document.getElementById('analyze-btn');
    if (analyzeBtn) {
        analyzeBtn.disabled = false;
        analyzeBtn.innerHTML = '<i class="bi bi-cpu me-2"></i>Start Analysis';
    }

    // Stop polling if analysis is complete or failed
    this.stopThoughtLogPolling();
};

/**
 * Simulate loading progress with status updates
 */
SmartLaneAnalysis.simulateLoadingProgress = function () {
    const stages = [
        'Initializing analyzers...',
        'Checking contract security...',
        'Analyzing liquidity pools...',
        'Scanning for honeypot patterns...',
        'Evaluating social sentiment...',
        'Running technical analysis...',
        'Assessing market structure...',
        'Generating AI insights...',
        'Finalizing recommendations...'
    ];

    let currentStage = 0;
    const statusEl = document.getElementById('loading-status');

    const updateProgress = () => {
        if (currentStage < stages.length && statusEl) {
            statusEl.textContent = stages[currentStage];
            currentStage++;
            setTimeout(updateProgress, 1500);
        }
    };

    updateProgress();
};

// ============================================================================
// RESULTS DISPLAY FUNCTIONS
// ============================================================================

/**
 * Display analysis results in the UI
 * FIXED: No longer expects thought_log in initial response
 */
SmartLaneAnalysis.displayAnalysisResults = function (analysis) {
    console.log('Displaying analysis results:', analysis);

    this.hideLoadingState();

    // Update recommendation summary
    this.updateRecommendationSummary(analysis);

    // Update token info if available
    if (analysis.token_data) {
        this.updateTokenInfo(analysis.token_data);
    }

    // Show trading panel if recommendation is actionable
    if (analysis.recommendation && analysis.recommendation !== 'HOLD') {
        this.updateTradingPanel(analysis);
    }

    // Update analyzer results if available
    if (analysis.analyzer_results) {
        this.updateAnalyzerResults(analysis.analyzer_results);
    } else if (analysis.result && analysis.result.analyzer_results) {
        this.updateAnalyzerResults(analysis.result.analyzer_results);
    }

    // Note: Thought log will be fetched separately
    // Show loading state for thought log until it arrives
    const thoughtLogContainer = document.getElementById('thought-log');
    if (thoughtLogContainer && !analysis.thought_log) {
        thoughtLogContainer.innerHTML = `
            <div class="text-center py-4 text-muted">
                <div class="spinner-border spinner-border-sm text-primary mb-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="small">Retrieving AI reasoning...</p>
            </div>
        `;
    }

    // Update detailed analysis if available
    if (analysis.detailed_data) {
        this.updateDetailedAnalysis(analysis.detailed_data);
    }

    // Trigger custom event for trading manager
    document.dispatchEvent(new CustomEvent('analysis:complete', {
        detail: analysis
    }));
};

/**
 * Update recommendation summary display
 */
SmartLaneAnalysis.updateRecommendationSummary = function (analysis) {
    const recommendationCard = document.getElementById('recommendation-summary');
    const icon = document.getElementById('recommendation-icon');
    const text = document.getElementById('recommendation-text');
    const summary = document.getElementById('recommendation-summary-text');
    const confidenceFill = document.getElementById('confidence-fill');
    const confidenceText = document.getElementById('confidence-percentage');
    const riskIndicator = document.getElementById('risk-indicator');
    const riskScore = document.getElementById('risk-score');

    if (!recommendationCard) return;

    // Update recommendation
    const recommendation = analysis.recommendation || 'ANALYZING';
    const confidence = analysis.confidence || 0;
    const risk = analysis.risk_score || 50;

    // Set card style based on recommendation
    recommendationCard.className = `card analysis-container mb-4 recommendation-card ${recommendation.toLowerCase()}`;

    // Update icon and text
    const recommendationConfig = {
        'STRONG_BUY': {
            icon: 'bi-arrow-up-circle-fill',
            text: 'Strong Buy Recommendation',
            summary: 'High confidence buy signal with favorable risk/reward ratio',
            color: 'text-success'
        },
        'BUY': {
            icon: 'bi-arrow-up-circle',
            text: 'Buy Recommendation',
            summary: 'Positive analysis suggests buying opportunity',
            color: 'text-success'
        },
        'HOLD': {
            icon: 'bi-dash-circle',
            text: 'Hold Recommendation',
            summary: 'Neutral analysis - no clear trading signal',
            color: 'text-warning'
        },
        'SELL': {
            icon: 'bi-arrow-down-circle',
            text: 'Sell Recommendation',
            summary: 'Analysis suggests selling or avoiding this token',
            color: 'text-danger'
        },
        'STRONG_SELL': {
            icon: 'bi-arrow-down-circle-fill',
            text: 'Strong Sell Recommendation',
            summary: 'High confidence sell signal - significant risks detected',
            color: 'text-danger'
        }
    };

    const config = recommendationConfig[recommendation] || recommendationConfig['HOLD'];

    if (icon) {
        icon.className = `bi ${config.icon} display-4 ${config.color}`;
    }
    if (text) {
        text.textContent = config.text;
        text.className = `mb-1 ${config.color}`;
    }
    if (summary) {
        summary.textContent = config.summary;
    }

    // Update confidence bar
    if (confidenceFill) {
        confidenceFill.style.width = `${confidence}%`;
    }
    if (confidenceText) {
        confidenceText.textContent = `${confidence}%`;
    }

    // Update risk indicator
    if (riskIndicator) {
        riskIndicator.style.left = `${risk}%`;
    }
    if (riskScore) {
        riskScore.textContent = `${risk}/100`;
    }
};

/**
 * Update token information display
 */
SmartLaneAnalysis.updateTokenInfo = function (tokenData) {
    if (!tokenData) return;

    const symbolEl = document.getElementById('token-symbol');
    const nameEl = document.getElementById('token-name');
    const priceEl = document.getElementById('token-price');

    if (symbolEl) {
        symbolEl.textContent = tokenData.symbol || '---';
    }
    if (nameEl) {
        nameEl.textContent = tokenData.name || 'Unknown Token';
    }
    if (priceEl) {
        priceEl.textContent = tokenData.price ? `$${parseFloat(tokenData.price).toFixed(6)}` : '$0.00';
    }
};

/**
 * Update trading panel with recommendations
 */
SmartLaneAnalysis.updateTradingPanel = function (analysis) {
    const panel = document.getElementById('trading-panel');
    const recommendedAction = document.getElementById('recommended-action');
    const recommendedConfidence = document.getElementById('recommended-confidence');
    const suggestedAmount = document.getElementById('suggested-amount');
    const riskLevel = document.getElementById('risk-level');
    const expectedSlippage = document.getElementById('expected-slippage');
    const buyBtn = document.getElementById('execute-buy-btn');
    const sellBtn = document.getElementById('execute-sell-btn');

    if (!panel) return;

    // Update text content
    if (recommendedAction) {
        recommendedAction.textContent = analysis.recommendation.toLowerCase().replace('_', ' ');
    }
    if (recommendedConfidence) {
        recommendedConfidence.textContent = `${analysis.confidence}%`;
    }
    if (suggestedAmount) {
        suggestedAmount.textContent = `${analysis.suggested_amount || '0.1'} ETH`;
    }
    if (riskLevel) {
        riskLevel.textContent = analysis.risk_level || 'Medium';
    }
    if (expectedSlippage) {
        expectedSlippage.textContent = `${analysis.expected_slippage || '0.5'}%`;
    }

    // Configure buttons based on recommendation
    if (buyBtn) buyBtn.style.display = 'none';
    if (sellBtn) sellBtn.style.display = 'none';

    if (analysis.recommendation === 'BUY' || analysis.recommendation === 'STRONG_BUY') {
        if (buyBtn) {
            buyBtn.style.display = 'inline-block';
            buyBtn.dataset.tokenAddress = analysis.token_address;
            buyBtn.dataset.amount = analysis.suggested_amount || '0.1';
        }
    } else if (analysis.recommendation === 'SELL' || analysis.recommendation === 'STRONG_SELL') {
        if (sellBtn) {
            sellBtn.style.display = 'inline-block';
            sellBtn.dataset.tokenAddress = analysis.token_address;
            sellBtn.dataset.amount = analysis.suggested_sell_amount || '100';
        }
    }

    // Show panel with glow effect
    panel.style.display = 'block';
    panel.classList.add('pulse-glow');

    // Remove glow after animation
    setTimeout(() => {
        panel.classList.remove('pulse-glow');
    }, 4000);
};

/**
 * Update analyzer results display
 */
SmartLaneAnalysis.updateAnalyzerResults = function (analyzerResults) {
    const container = document.getElementById('analyzer-results');

    if (!container) return;

    if (!analyzerResults || Object.keys(analyzerResults).length === 0) {
        container.innerHTML = `
            <div class="text-center py-4 text-muted">
                <i class="bi bi-exclamation-triangle display-4 d-block mb-3"></i>
                <p>No analyzer results available</p>
            </div>
        `;
        return;
    }

    const analyzersHtml = Object.entries(analyzerResults).map(([name, result]) => {
        const statusIcon = result.status === 'COMPLETED' ? 'bi-check-circle text-success' :
            result.status === 'FAILED' ? 'bi-x-circle text-danger' :
                'bi-hourglass-split text-warning';

        return `
            <div class="analyzer-card p-3 mb-2">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="mb-1">
                            <i class="bi ${statusIcon} me-2"></i>
                            ${name.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </h6>
                        <small class="text-muted">${result.summary || 'Analysis completed'}</small>
                    </div>
                    <div class="text-end">
                        <div class="badge ${result.risk_level === 'HIGH' ? 'bg-danger' :
                result.risk_level === 'MEDIUM' ? 'bg-warning' : 'bg-success'}">
                            ${result.risk_level || 'UNKNOWN'}
                        </div>
                        ${result.score ? `<div class="small text-muted mt-1">Score: ${result.score}/100</div>` : ''}
                    </div>
                </div>
                ${result.details ? `
                    <div class="mt-2 small text-muted">
                        ${Array.isArray(result.details) ? result.details.join(', ') : result.details}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');

    container.innerHTML = analyzersHtml;
};

/**
 * Update thought log display
 * ENHANCED: Better formatting and error handling
 */
SmartLaneAnalysis.updateThoughtLog = function (thoughtLog) {
    const container = document.getElementById('thought-log');

    if (!container) {
        console.warn('Thought log container not found');
        return;
    }

    console.log('Updating thought log with data:', thoughtLog);

    // Handle empty or invalid thought log
    if (!thoughtLog || (Array.isArray(thoughtLog) && thoughtLog.length === 0)) {
        container.innerHTML = `
            <div class="text-center py-4 text-muted">
                <i class="bi bi-brain display-4 d-block mb-3"></i>
                <p>No AI reasoning available</p>
            </div>
        `;
        return;
    }

    // Convert thought log to array if it's not already
    const thoughts = Array.isArray(thoughtLog) ? thoughtLog : [thoughtLog];

    const thoughtsHtml = thoughts.map((thought, index) => {
        // Handle different thought log formats
        let stepNumber = thought.step || (index + 1);
        let category = thought.category || '';
        let reasoning = thought.thought || thought.reasoning || thought.content || thought;
        let confidence = thought.confidence || thought.confidence_level || null;
        let timestamp = thought.timestamp || '';

        // Format the thought entry
        return `
            <div class="mb-3 pb-3 ${index < thoughts.length - 1 ? 'border-bottom border-secondary' : ''}">
                <div class="d-flex align-items-start">
                    <i class="bi bi-lightbulb text-warning me-2 mt-1"></i>
                    <div class="flex-grow-1">
                        <div class="d-flex justify-content-between align-items-start mb-1">
                            <small class="text-muted">
                                Step ${stepNumber}
                                ${category ? `- ${category}` : ''}
                            </small>
                            ${timestamp ? `<small class="text-muted">${new Date(timestamp).toLocaleTimeString()}</small>` : ''}
                        </div>
                        <p class="mb-1">${reasoning}</p>
                        ${confidence !== null ? `
                            <div class="d-flex align-items-center">
                                <small class="text-info me-2">Confidence:</small>
                                <div class="progress" style="width: 100px; height: 10px;">
                                    <div class="progress-bar bg-info" role="progressbar" 
                                         style="width: ${confidence}%"
                                         aria-valuenow="${confidence}" 
                                         aria-valuemin="0" 
                                         aria-valuemax="100">
                                    </div>
                                </div>
                                <small class="text-info ms-2">${confidence}%</small>
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = thoughtsHtml;
    console.log('Thought log updated successfully');
};

/**
 * Update detailed analysis display with tabs
 */
SmartLaneAnalysis.updateDetailedAnalysis = function (detailedData) {
    const container = document.getElementById('detailed-analysis');

    if (!container) return;

    if (!detailedData || Object.keys(detailedData).length === 0) {
        container.innerHTML = `
            <div class="text-center py-4 text-muted">
                <i class="bi bi-table display-4 d-block mb-3"></i>
                <p>No detailed data available</p>
            </div>
        `;
        return;
    }

    // Create tabbed interface for detailed data
    const tabs = Object.keys(detailedData);
    const tabsHtml = tabs.map((tab, index) => `
        <li class="nav-item" role="presentation">
            <button class="nav-link ${index === 0 ? 'active' : ''}" 
                    id="${tab}-tab" 
                    data-bs-toggle="tab" 
                    data-bs-target="#${tab}-pane" 
                    type="button">
                ${tab.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
            </button>
        </li>
    `).join('');

    const panes = tabs.map((tab, index) => {
        const data = detailedData[tab];
        let content = '';

        if (Array.isArray(data)) {
            content = `
                <div class="table-responsive">
                    <table class="table table-dark table-sm">
                        <tbody>
                            ${data.map(item => `
                                <tr>
                                    <td>${typeof item === 'object' ? JSON.stringify(item, null, 2) : item}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        } else if (typeof data === 'object') {
            content = `
                <div class="table-responsive">
                    <table class="table table-dark table-sm">
                        <tbody>
                            ${Object.entries(data).map(([key, value]) => `
                                <tr>
                                    <td class="fw-bold">${key.replace('_', ' ')}</td>
                                    <td>${typeof value === 'object' ? JSON.stringify(value) : value}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        } else {
            content = `<pre class="text-light">${data}</pre>`;
        }

        return `
            <div class="tab-pane fade ${index === 0 ? 'show active' : ''}" 
                 id="${tab}-pane" 
                 role="tabpanel">
                ${content}
            </div>
        `;
    }).join('');

    container.innerHTML = `
        <ul class="nav nav-tabs mb-3" role="tablist">
            ${tabsHtml}
        </ul>
        <div class="tab-content">
            ${panes}
        </div>
    `;
};

// ============================================================================
// TRADING EXECUTION FUNCTIONS
// ============================================================================

/**
 * Execute trade based on analysis recommendation
 */
SmartLaneAnalysis.executeTradeFromAnalysis = async function (action, tokenAddress, amount) {
    if (!window.tradingManager) {
        this.showNotification('Trading manager not available', 'error');
        return;
    }

    try {
        const tradeData = {
            token_address: tokenAddress,
            action: action,
            amount: amount,
            source: 'smart_lane_analysis'
        };

        if (action === 'buy') {
            await window.tradingManager.executeBuyOrder(tradeData);
        } else if (action === 'sell') {
            await window.tradingManager.executeSellOrder(tradeData);
        }

        this.showNotification(`${action.toUpperCase()} order executed successfully`, 'success');

    } catch (error) {
        console.error('Trade execution error:', error);
        this.showNotification(`Failed to execute ${action}: ${error.message}`, 'error');
    }
};

/**
 * Show manual trade modal
 */
SmartLaneAnalysis.showManualTradeModal = function () {
    const tokenAddress = document.getElementById('token_address')?.value;

    if (!tokenAddress) {
        this.showNotification('Please enter a token address first', 'warning');
        return;
    }

    // Use the trading manager's quick trade modal
    if (window.tradingManager && typeof window.tradingManager.showQuickTradeModal === 'function') {
        window.tradingManager.showQuickTradeModal();

        // Wait for modal to load then set token address
        setTimeout(() => {
            const tokenInput = document.querySelector('#quick-trade-modal [name="token_address"]');
            if (tokenInput) {
                tokenInput.value = tokenAddress;
            }
        }, 100);
    } else if (typeof showQuickTradeModal === 'function') {
        showQuickTradeModal();

        setTimeout(() => {
            const tokenInput = document.querySelector('input[name="token_address"]');
            if (tokenInput) {
                tokenInput.value = tokenAddress;
            }
        }, 100);
    } else {
        this.showNotification('Quick trade modal not available', 'warning');
    }
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Reset analysis state
 * ENHANCED: Stops polling when resetting
 */
SmartLaneAnalysis.resetAnalysis = function () {
    // Stop any ongoing polling
    this.stopThoughtLogPolling();

    // Hide results
    const analysisResults = document.getElementById('analysis-results');
    const initialState = document.getElementById('initial-state');

    if (analysisResults) analysisResults.style.display = 'none';
    if (initialState) initialState.style.display = 'block';

    // Reset form
    const form = document.getElementById('analysis-form');
    if (form) {
        form.reset();

        const positionSizeInput = document.getElementById('position_size');
        if (positionSizeInput) {
            positionSizeInput.value = '0.1';
        }
    }

    // Clear URL parameters
    const url = new URL(window.location);
    url.searchParams.delete('token');
    window.history.replaceState({}, document.title, url.pathname);
};

/**
 * Monitor analysis progress for long-running analyses
 */
SmartLaneAnalysis.monitorAnalysisProgress = function (analysisId) {
    const checkProgress = async () => {
        try {
            const response = await fetch(`/dashboard/api/smart-lane/analysis/${analysisId}/status/`);
            const result = await response.json();

            if (result.status === 'COMPLETED') {
                this.displayAnalysisResults(result.analysis);
                // Start polling for thought log after completion
                if (result.analysis.analysis_id) {
                    this.startThoughtLogPolling(result.analysis.analysis_id);
                }
            } else if (result.status === 'FAILED') {
                this.hideLoadingState();
                this.showNotification('Analysis failed: ' + (result.error || 'Unknown error'), 'error');
            } else {
                // Continue monitoring
                setTimeout(checkProgress, 2000);
            }
        } catch (error) {
            console.error('Error checking analysis progress:', error);
            this.hideLoadingState();
            this.showNotification('Error monitoring analysis progress', 'error');
        }
    };

    setTimeout(checkProgress, 2000);
};

/**
 * Get CSRF token from meta tag or cookies
 * ENHANCED: Better CSRF token retrieval
 */
SmartLaneAnalysis.getCsrfToken = function () {
    // First try meta tag
    const token = document.querySelector('meta[name="csrf-token"]');
    if (token) {
        return token.getAttribute('content');
    }

    // Then try cookie
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue || '';
};

/**
 * Show notification to user
 */
SmartLaneAnalysis.showNotification = function (message, type = 'info') {
    if (window.tradingManager && typeof window.tradingManager.showNotification === 'function') {
        window.tradingManager.showNotification(message, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${message}`);
        if (type === 'error' || type === 'warning') {
            alert(message);
        }
    }
};

// ============================================================================
// GLOBAL FUNCTION EXPORTS (for template compatibility)
// ============================================================================

// Export functions for backwards compatibility with template onclick handlers
window.resetAnalysis = SmartLaneAnalysis.resetAnalysis.bind(SmartLaneAnalysis);
window.showManualTradeModal = SmartLaneAnalysis.showManualTradeModal.bind(SmartLaneAnalysis);
window.startAnalysis = SmartLaneAnalysis.startAnalysis.bind(SmartLaneAnalysis);

// Export module for global access
window.smartLaneAnalysis = SmartLaneAnalysis;

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize Smart Lane Analysis when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
    SmartLaneAnalysis.init();
});

// Clean up on page unload to prevent memory leaks
window.addEventListener('beforeunload', function () {
    if (SmartLaneAnalysis.thoughtLogInterval) {
        SmartLaneAnalysis.stopThoughtLogPolling();
    }
});