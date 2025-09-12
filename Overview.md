# DEX Auto-Trading Bot – Project Overview

---

## Vision
<!-- Project high-level vision and differentiator -->
The goal of this project is to develop a **DEX auto-trading / sniping bot** that operates with industrial-grade risk controls and professional-level intelligence, while remaining explainable and user-friendly.

The system is designed to:

* Monitor and analyze **new token launches** on decentralized exchanges (DEXs).
* Automatically decide whether to buy, hold, or skip opportunities based on advanced risk checks and intelligence scoring.
* Provide **explainable reasoning** for every decision in the form of an **AI Thought Log**.
* Compete with commercial sniping bots in terms of speed, safety, and profit potential.

The project begins as **single-user** (for the author), but is designed with future multi-user expansion in mind.

---

## Core Goals
<!-- What success means at the core of the system -->
1. **Speed** – Respond to new opportunities with low latency (sub-second reaction times on L1/L2 where possible).  
2. **Safety** – Industrial-grade risk management to minimize exposure to scams, rugs, and honeypots.  
3. **Transparency** – An **AI Thought Log** that explains every decision with structured signals and human-readable rationale.  
4. **Profitability** – Execute trades with strategies that mirror professional traders, with strong portfolio and bankroll management.  

---

## Key Components
<!-- Major system modules and their responsibilities -->

### 1. Control Plane (Django Backend)
* Provides the **dashboard** to start/stop the bot and monitor activity.  
* Stores **trade history, risk findings, intelligence scores, and thought logs** in Postgres.  
* Exposes APIs for configuration, telemetry, and reporting.  
* Displays portfolio performance (PnL, positions, exposure).  
* Implements user wallet connection and policy controls (spend caps, blacklists/whitelists).  

### 2. Trading Engine (Async Worker)
* Always-on async service optimized for **latency-critical paths**.  
* Responsibilities:  
  * **Discovery**: listen for new pairs (factory events, liquidity adds, mempool).  
  * **Risk**: pre-trade simulation (honeypot, taxes, LP lock, ownership).  
  * **Intelligence**: risk-adjusted scoring and decision-making.  
  * **Execution**: submit transactions via private relays, apply slippage/gas strategies, manage sell exits.  
  * **Portfolio**: enforce bankroll limits, daily loss caps, and circuit breakers.  
* Communicates with the Django backend via event streaming (e.g., Redis).  

### 3. AI Thought Log
* Every decision is logged with:  
  * **Signals** (raw values, weights, pass/fail checks).  
  * **Narrative summary** (1–3 sentences of rationale).  
  * **Verdict** (buy/sell/skip with context).  
  * **Counterfactuals** (e.g., “Would trade if top_holder_concentration < 20%”).  
* Serves as both an **audit trail** and an **educational tool** for understanding decisions.  

---

## Risk & Intelligence System
<!-- Risk management design with hard blocks, soft penalties, and execution safety -->

An **industrial-grade risk system** to compete with professional bots:

* **Hard Blocks**: honeypot detection, LP not locked, ownership not renounced, excessive buy/sell taxes, proxy contracts with no timelock.  
* **Soft Penalties**: holder concentration too high, dev wallet funded by mixers, no verified source code, bytecode similarity to scams.  
* **Market Microstructure**: pool depth, expected slippage, impact analysis.  
* **Execution Safety**: gas strategy, max slippage enforcement, relay preference.  
* **Post-trade Guards**: automatic stop-losses, profit-taking ladders, and circuit breakers.  

---

## Competitive Landscape
<!-- Market positioning vs existing bots -->

Current leaders: **Maestro Bot, Banana Gun, Unibot**.  
They focus on: Telegram UX, high execution speed, private mempool, basic risk checks, copy trading.  

**Our differentiators**:  
* Rich **AI Thought Log** (transparent, auditable reasoning).  
* Stronger **risk intelligence** with industrial-grade checks.  
* Safer custody model (non-custodial default, optional vaults).  
* **Professional dashboard** (Django-based) instead of Telegram-only.  

---

## Security Principles
<!-- Security baselines: custody, auditability, separation -->

* **Non-custodial default**: user connects wallet, grants limited permissions.  
* **Optional custody mode**: hot wallet with strict spend limits, encrypted storage, instant withdrawal.  
* **Auditability**: every decision, config, and risk check logged.  
* **Separation of concerns**: secrets and signing isolated from web tier.  

---

## Deployment & Operations
<!-- Infra and deployment strategy -->

* Services: Django backend, async engine, Postgres, Redis.  
* Deployment: local dev, Docker Compose for staging, future k8s for production.  
* Observability: engine latency metrics, provider health, trade success/failure, circuit breaker/error reporting.  
* Backups: regular Postgres dumps, configuration versioning.  

---

## Extended Architecture
<!-- All deeper architecture choices and clarifications -->

### Event Bus & Task Queue
* **Celery + Redis** for retries, back-pressure, task chaining, and DLQs.  
* Independent queues for `risk.urgent`, `execution.critical`, and `analytics.background`.  
* DLQ convention (`*.dlq`) for failed tasks with monitoring/alerting.

### Feature Store
* Persist **decision-time feature vectors** for replay, learning, and explainability.  
* Versioned and tied to config hash for reproducibility.

### Strategy Registry
* Versioned **strategy presets** with export/import (YAML/JSON).  
* Immutable past configs linked to trades/backtests; promote presets to live.

### Learning Ops (Self-Learning Loop)
* Persist features + actions.  
* Evaluate after 5m/30m/24h windows (PnL, slippage, drawdown).  
* Label decisions as good/neutral/bad.  
* Methods: weight tuning (bandits), Bayesian optimization, later ML classifiers.  
* Guardrails: staged rollout, paper testing first, drift caps.  
* Changelog + explainability surfaced in UI.

### Paper Trading & Replay
* **Live Mirror**: simulate orders with live pool quotes.  
* **Historical Replay**: run strategies against archived data.  
* **Shadow Trading**: parallel paper/live comparison.  
* Includes slippage/fee modeling, latency injection.  
* Outputs: backtest runs, KPIs, comparative reports.  

### Provider Manager
* Pool of RPC/relay providers with latency metrics + failover.  
* Auto-fallback and circuit-breaking per chain.  

### Execution Guards
* Enforce max slippage, gas ceilings, nonce handling, dry-run validation.  
* Circuit-break on repeated failures.  

### Wallet & Signing
* **Phase 1:** Local encrypted keystore (path in env, password in keyring/vault).  
* **Phase 2:** Hardware wallet integration (Ledger/Trezor).  
* **Phase 3:** WalletConnect in dashboard.  
* No secrets in code/images; vault-managed in production.  

### Panic Button
* Halts new decisions + cancels pending orders.  
* Places protective exits (market-out or trailing stops).  
* Freezes learning updates for the session.  
* Auto-saves logs, trades, provider latency, config snapshot.  

### Observability
* **Prometheus + Grafana** baseline.  
* Structured logging + OpenTelemetry tracing.  
* Sentry/Rollbar for error aggregation.  
* Critical alerts for execution failures; soft alerts for risk timeouts.  

### Feature Flags & Circuit Breakers
* Runtime toggles: paper mode, shadow trading, panic, model staging.  
* Supports safe rollouts + instant kill-switches.  

### Permissions & Auth (Future-Proof)
* Minimal role model (execution, config promotion, panic).  
* Single-user now; multi-user ready later.  

### Frontend UX
* Strategy diff viewer.  
* Paper vs live A/B comparison charts.  
* Provider/queue health panel.  
* Desktop notifications for panic + circuit breaker events.  

---

## Technical Architecture Clarifications
<!-- Direct answers to critical design choices -->

* **Chains & DEXs (MVP):** Ethereum mainnet + Base. Uniswap V2/V3 on Ethereum; Uniswap V3 on Base.  
* **Discovery:** WebSocket subscriptions via Alchemy/Infura/Ankr; HTTP fallback; archive nodes added later.  
* **Engine separation:** Django for control; async engine for hot path; Redis + Celery for queues.  
* **Risk checks:** Parallelized with per-check timeouts + provider failover.  
* **DB strategy:** Django ORM for admin/API; asyncpg for engine.  
* **Indexing:** General GIN + targeted indexes for hot JSONB keys.  
* **Wallet security:** Env path for keystore, secrets in Vault/keyring, hardware wallet support later.  
* **Monitoring:** Prometheus/Grafana baseline, with optional cloud observability later.  
* **Latency SLAs:**  
  - Discovery → risk start ≤ 150 ms  
  - Risk eval ≤ 1200 ms (P95)  
  - Decision → tx submit ≤ 300 ms  
  - End-to-end ≤ 2s on L1, ≤ 1.2s on Base.  

---

## Roadmap (MVP First Steps)
<!-- Implementation order, not calendar -->

1. Event bus + task queue foundation.  
2. Discovery listeners (PairCreated, LiquidityAdded).  
3. Risk v1: ownership, LP lock, honeypot, taxes, concentration.  
4. Execution v1: private relay buy, slippage guard, gas strategy.  
5. Sell v1: TP/SL exits.  
6. AI Thought Log with structured features + rationale.  
7. Dashboard: start/stop, portfolio view, Thought Log panel.  
8. Safety defaults: bankroll cap, daily loss cap, blacklist.  
9. Paper trading mirror.  

---
DEX Auto-Trading Bot - Current Project Overview
You have built a sophisticated Django-based DEX auto-trading bot designed for automated cryptocurrency trading on decentralized exchanges like Uniswap. The project is architected as a multi-app Django system with distinct modules handling different aspects of automated trading, risk management, wallet operations, and analytics.
Core Architecture & Apps
The project follows a modular Django structure with five main applications:

trading/ - Handles trade execution, order management, and DEX interactions
risk/ - Comprehensive risk assessment system (your main focus area)
wallet/ - Wallet management, key storage, and transaction signing
analytics/ - Performance tracking, reporting, and ML-based insights
dashboard/ - Web interface for monitoring and control

The system uses PostgreSQL for data persistence, Redis for caching and task queues, Celery for asynchronous task processing, and REST APIs for external integrations. It's designed to handle high-frequency trading decisions with real-time risk assessment.
Advanced Risk Management System
The risk management module is the heart of the project and what we just completed. It implements an industrial-grade risk assessment pipeline that evaluates tokens before any trades are executed. The system performs multiple parallel checks including:

Honeypot Detection - Identifies scam tokens that prevent selling
Liquidity Analysis - Ensures sufficient liquidity and reasonable slippage
Ownership Analysis - Checks contract ownership and admin functions
Tax Analysis - Detects buy/sell taxes and transfer restrictions
LP Token Security - Verifies liquidity provider token locks/burns

Each risk check runs as an independent Celery task that can execute in parallel, with a coordinator module that aggregates results and makes final trading decisions based on configurable risk profiles (Conservative/Moderate/Aggressive).
Production-Ready Trading Engine
The project is built for production deployment with comprehensive error handling, retry mechanisms, logging, and monitoring. It supports multiple risk profiles allowing different trading strategies, bulk token assessment for portfolio management, and real-time decision making with sub-second response times for critical checks.
The codebase follows enterprise standards with proper type annotations, comprehensive docstrings, full test coverage, and Django best practices. It's designed to scale horizontally with multiple worker processes and can be deployed across multiple environments with environment-based configuration. The system is currently ready to integrate with actual Web3 providers and start live trading operations once RPC endpoints and private keys are configured.