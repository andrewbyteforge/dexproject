# DEX Auto-Trading Bot – Project Overview (Control Framework Edition)

---

## Vision & Control Philosophy
<!-- Project high-level vision with delivery discipline -->
The goal of this project is to develop a **DEX auto-trading / sniping bot** that operates with industrial-grade risk controls and professional-level intelligence, while remaining explainable and user-friendly.

**Control Principle:** Every component has a **Definition of Done (DoD)**, clear **risk if ignored**, and **MVP specification** to prevent feature creep and ensure controlled delivery.

The system is designed to:
* Monitor and analyze **new token launches** on decentralized exchanges (DEXs).
* Automatically decide whether to buy, hold, or skip opportunities based on advanced risk checks and intelligence scoring.
* Provide **explainable reasoning** for every decision in the form of an **AI Thought Log**.
* Compete with commercial sniping bots in terms of speed, safety, and profit potential.

---

## Architecture Decisions (LOCKED)
<!-- Foundational choices that drive implementation -->

### Database & Infrastructure
**Decision:** SQLite → PostgreSQL + Redis migration later  
**Rationale:** Fastest MVP path without DevOps overhead  
**Migration Checkpoint:** Migrate before production deployment (defined in Phase 6)

### Trading Engine Process Model  
**Decision:** Django management command (`python manage.py run_trading_engine`)  
**Rationale:** Lowest friction, Django ecosystem integration, dashboard control  
**Evolution Path:** Option to separate async service once stability proven

### Frontend Strategy
**Decision:** Hybrid - Django templates + REST API foundation  
**Rationale:** Immediate visibility via templates, future-proofed with APIs  
**API Requirement:** Minimum one working API endpoint per app (even if unused initially)

### Security Boundaries
**Decision:** Testnet-only + environment variables for keys/endpoints  
**Hard Rule:** **NO MAINNET TRADES** until all DoD criteria met and reviewed  
**Key Management:** Environment variables for MVP, keystore evolution later

---

## Control Framework Implementation Plan

### **Phase 1: Foundation URLs & Views**
**Priority:** CRITICAL PATH - Everything downstream blocked until complete

**Definition of Done:**
- [ ] All 5 apps have at least one working view + API endpoint
- [ ] URL routing complete for: `/dashboard/`, `/trading/`, `/risk/`, `/wallet/`, `/analytics/`
- [ ] Health check endpoint per app returns 200 OK
- [ ] Django admin accessible for all models

**Risk if Ignored:** No way to interact with system → development paralyzed

**MVP Implementation:**
- Basic health check endpoints (`/app/api/health/`)
- Simple list views for core models (using Django generic views)
- Placeholder templates with "Coming Soon" messaging
- REST API skeleton with at least one GET endpoint per app

**Control Check:** Can navigate to each app URL without 404 errors

**Files to Create/Update:**
- `dexproject/dexproject/urls.py` - Add app URL includes
- `dashboard/urls.py` + `views.py` - Dashboard routes and views
- `trading/urls.py` + `views.py` - Trading API endpoints
- `risk/urls.py` + `views.py` - Risk assessment endpoints
- `wallet/urls.py` + `views.py` - Wallet status endpoints
- `analytics/urls.py` + `views.py` - Analytics/reporting endpoints

---

### **Phase 2: Minimal Dashboard (IMMEDIATE FEEDBACK)**
**Priority:** HIGH - Provides external visibility into system state

**Definition of Done:**
- [ ] Django template with bot start/stop controls
- [ ] System status display (engine running/stopped, queue health)
- [ ] Basic portfolio display (positions, P&L placeholder)
- [ ] Real-time status updates (polling or WebSocket)
- [ ] Navigation to other app sections

**Risk if Ignored:** No external visibility → flying blind during development/testing

**MVP Implementation:**
- Single dashboard template with status cards
- Manual bot start/stop buttons (POST endpoints)
- Simple JavaScript polling for status updates
- Bootstrap/Tailwind for basic styling
- Integration with Django management command controls

**Control Check:** Can start/stop trading engine from web interface, see current status

**Files to Create/Update:**
- `templates/dashboard/index.html` - Main dashboard template
- `dashboard/views.py` - Dashboard view logic
- `dashboard/static/dashboard/` - CSS/JS assets
- `dashboard/management/commands/run_trading_engine.py` - Engine command

---

### **Phase 3: Blockchain Connectivity (INTEGRATION PROOF)**
**Priority:** CRITICAL - Proves external integration works

**Definition of Done:**
- [ ] Web3 provider connects to testnet (Sepolia recommended)
- [ ] Can query ETH balance for configured wallet
- [ ] Can listen to PairCreated events on one DEX (Uniswap V2)
- [ ] Events logged to Django models
- [ ] Dashboard displays connection status and latest event

**Risk if Ignored:** Trading engine has no live data → entire system useless

**MVP Implementation:**
- Single RPC provider connection (Alchemy/Infura)
- Environment variable configuration for RPC URL and private key
- Basic Web3 service class for blockchain interactions
- Event listener for Uniswap V2 PairCreated events (testnet only)
- Simple event storage in `TradingPair` model

**Control Check:** Dashboard shows current ETH balance + latest pair creation event

**Files to Create/Update:**
- `trading/services/web3_service.py` - Blockchain interaction service
- `trading/services/event_listener.py` - DEX event monitoring
- `dexproject/settings.py` - Add Web3 configuration
- `.env.example` - Document required environment variables

---

### **Phase 4: Discovery System (DATA PIPELINE)**
**Priority:** HIGH - Enables opportunity detection

**Definition of Done:**
- [ ] Captures new pair events from testnet DEX
- [ ] Stores events in `TradingPair` model with metadata
- [ ] Triggers risk assessment task for new pairs
- [ ] Dashboard shows recent discoveries
- [ ] Event processing latency < 30 seconds

**Risk if Ignored:** No opportunity detection → bot sits idle forever

**MVP Implementation:**
- WebSocket or HTTP polling event listener
- Celery task triggered on new pair discovery
- Basic pair metadata extraction (tokens, liquidity)
- Integration with existing risk assessment system
- Simple discovery feed in dashboard

**Control Check:** New testnet pairs appear in Django admin within 30 seconds

**Files to Create/Update:**
- `trading/tasks/discovery.py` - Pair discovery tasks
- `trading/models.py` - Update TradingPair model if needed
- `dashboard/templates/` - Add discovery feed section

---

### **Phase 5: Trading Engine MVP (END-TO-END PROOF)**
**Priority:** CRITICAL - Proves complete execution pipeline

**Definition of Done:**
- [ ] Django management command runs trading engine loop
- [ ] Can execute one buy trade on testnet when manually triggered
- [ ] Transaction appears on testnet block explorer
- [ ] Trade recorded in Django models
- [ ] Dashboard shows trade execution status
- [ ] Engine can be started/stopped from dashboard

**Risk if Ignored:** No execution capability → risk analysis without action is useless

**MVP Implementation:**
- Django management command with main trading loop
- Manual trade trigger via dashboard button
- Basic buy order execution (no automated decisions yet)
- Transaction signing and submission
- Trade result storage and status tracking

**Control Check:** Can click "Test Trade" → see transaction on testnet Etherscan

**Files to Create/Update:**
- `trading/management/commands/run_trading_engine.py` - Main engine
- `trading/services/execution_service.py` - Trade execution logic
- `trading/tasks/execution.py` - Execution Celery tasks
- Dashboard views for manual trade triggering

---

### **Phase 6: Risk + AI Thought Log Integration**
**Priority:** MEDIUM - Provides transparency and debugging capability

**Definition of Done:**
- [ ] Risk assessment runs before any trade execution
- [ ] AI Thought Log generated for each trading decision
- [ ] Dashboard panel displays recent assessments and reasoning
- [ ] Risk assessment results stored in analytics models
- [ ] Clear pass/fail indicators with explanatory text

**Risk if Ignored:** "Black box" trading → can't debug failures or improve decisions

**MVP Implementation:**
- Integration between discovery → risk assessment → trading decision
- Thought log generation using existing analytics models
- Dashboard panel showing last 10 risk assessments
- Simple reasoning display (structured data + narrative)
- Risk check result visualization

**Control Check:** Every trade attempt shows corresponding risk assessment + thought log

**Files to Create/Update:**
- Update existing risk assessment integration
- `analytics/services/thought_log_service.py` - Thought log generation
- Dashboard templates for risk assessment display

---

### **Phase 7: Production Migration Checkpoint**
**Priority:** BLOCKING - Required before any mainnet deployment

**Definition of Done:**
- [ ] PostgreSQL + Redis migration completed
- [ ] Environment configuration for production
- [ ] **Mainnet readiness checklist:** RPC redundancy, gas strategy, key rotation
- [ ] Security review of key management
- [ ] Performance testing of complete pipeline
- [ ] Backup and monitoring setup

**Risk if Ignored:** SQLite performance issues, data loss risk, security vulnerabilities

**⚠️ Control Notes:**
- Mainnet checklist required: Cannot flip to mainnet without explicit security review
- Database migration: Full data migration plan with rollback procedures
- Key management: Production-grade private key handling before mainnet access

**Control Gate:** Complete review required before mainnet authorization

---

## Control Mechanisms

### **Pre-Implementation Controls**
- **DoD Lock-in:** Each phase DoD approved before coding starts
- **Architecture Alignment:** All implementation must match locked architecture decisions
- **Scope Discipline:** No features beyond MVP specification until DoD met

### **Implementation Controls**
- **DoD-First Development:** Hit DoD criteria then STOP - no gold-plating
- **Control Check Gates:** Test each control check before proceeding to next phase
- **Risk Escalation:** If "Risk if Ignored" materializes → immediate backtrack

### **Security Controls**
- **Hard Testnet Rule:** NO mainnet configuration until Phase 7 complete
- **Environment Discipline:** All secrets in environment variables, no hardcoding
- **Review Gates:** Manual approval required for any mainnet-related changes

### **Quality Controls**
- **File Structure:** Follow project instructions (800 lines max, docstrings, annotations)
- **Error Handling:** Comprehensive error handling and logging per project standards
- **Code Review:** VS Code + Pylance + flake8 compliance required

---

## Success Metrics

### **Phase Completion Tracking**
- [ ] Phase 1: Foundation (URLs/Views working)
- [ ] Phase 2: Dashboard (Visual control interface)
- [ ] Phase 3: Blockchain (Live data integration)
- [ ] Phase 4: Discovery (Opportunity detection)
- [ ] Phase 5: Execution (End-to-end trading)
- [ ] Phase 6: Intelligence (Risk + reasoning)
- [ ] Phase 7: Production (Migration + security)

### **Control Health Indicators**
- **Scope Creep:** Zero features implemented beyond current phase MVP
- **Architecture Drift:** Zero deviations from locked architecture decisions
- **Security Compliance:** Zero mainnet access before Phase 7 completion
- **Quality Gates:** All code passes flake8, has docstrings, proper error handling

---

## Emergency Controls

### **Project Halt Conditions**
- Any security breach or mainnet exposure before Phase 7
- Architecture decisions prove fundamentally flawed (requires co-PM review)
- DoD criteria cannot be met within reasonable effort (scope too aggressive)

### **Rollback Triggers**
- Control checks failing consistently
- Implementation diverging from MVP specifications
- "Risk if Ignored" scenarios materializing

### **Escalation Path**
- Technical blockers: Document in project issues, seek co-PM guidance
- Scope questions: Refer to this document, default to MVP approach
- Architecture changes: Requires explicit co-PM approval and document update

---

*This document serves as the implementation contract. All development must align with these control frameworks and success criteria.*