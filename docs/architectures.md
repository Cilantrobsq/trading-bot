# Polymarket Trading Bot Architectures: Executive Report

Prepared by: Thymian (Research Specialist)
Date: 2026-03-06
Classification: Internal, Executive Decision-Making

---

## Executive Summary

This report proposes four concrete Polymarket trading bot architectures, ranked by risk/reward, for executive evaluation. The analysis is grounded in comprehensive platform research, documented bot operator failures, and real-world performance data.

Polymarket is the dominant prediction market ($billions in volume), operating a hybrid CLOB with off-chain matching and on-chain Polygon settlement. The bot ecosystem is mature and brutally competitive: 92% of traders lose money, 73% of arbitrage profits go to sub-100ms bots, and the average arbitrage window has shrunk to 2.7 seconds. However, specific strategies remain viable for new entrants with the right approach.

We catalog 10 documented failure modes (including three oracle manipulation incidents totaling $263M+ in affected markets, a $230K bot hack, and malicious open-source code attacks) and map how each proposed architecture addresses them.

Our recommendation: Start with Architecture 2 (Cross-Platform Arbitrage, $20K minimum, 13-16 weeks to market) for immediate, structural returns. Simultaneously develop Architecture 3 (AI Information Edge) as a medium-term high-upside play. The hybrid Architecture 4 is the long-term target but should not be the entry point due to complexity.

Do not build Architecture 1 (Market Making) unless capital exceeds $100K and the goal is low-variance income. Do not build pure speed arbitrage (not proposed here) under any circumstances.

---

## Architecture 1: Conservative Market Making

### Strategy Description

Provide two-sided liquidity across multiple Polymarket markets by placing simultaneous buy and sell orders on both YES and NO outcomes. Profit comes from capturing the bid-ask spread while maintaining balanced inventory. Additional revenue from Polymarket's Maker Rebates Program (launched January 2026).

The bot continuously quotes on both sides of selected markets, adjusting spreads dynamically based on order book depth, recent volatility, and inventory skew. When inventory becomes unbalanced, the bot widens spreads on the overweight side to encourage rebalancing flow.

### Technical Stack

- Python 3.12 (py-clob-client), migration path to Rust for latency-sensitive components
- WebSocket for real-time order book updates, REST API for order management
- Custom OMS tracking open orders, fills, inventory state
- Real-time inventory tracking, position limits per market, automatic quoting halt on extreme skew
- Dedicated VPS ($100/mo), Polygon RPC ($100/mo), monitoring via Grafana + PagerDuty
- SQLite for trade history and analytics

### Capital Requirements

- Minimum viable: $50,000 (5-10 markets, $5-10K per market per side)
- Recommended: $100,000 (15-20 markets with meaningful book depth)
- Monthly ops: ~$300
- First-year total (minimum): $53,600

### Expected Returns

| Scenario | Monthly | Annualized |
|----------|---------|------------|
| Best case | 2-3% | 24-36% |
| Expected | 0.8-1.5% | 10-18% |
| Worst case | -0.4 to -1.25% | -5 to -15% |

Estimated Sharpe ratio: 1.5-2.5

### Risk Factors

1. Adverse selection from informed traders picking off stale quotes during breaking events
2. Inventory concentration during sharp directional moves
3. Oracle manipulation causing total loss on affected markets
4. Spread compression from competing market makers
5. Low volatility periods reducing spread revenue below operational costs

### Failure Modes and Mitigations

- Stale quote exploitation: Rapid quote cancellation on news triggers (2-second target)
- Runaway inventory: Hard $10K max net directional exposure per market
- API outage: Kill switch cancels all orders on heartbeat loss; positions sized for 24h unmanaged survival
- Oracle loss: Per-market cap ensures any single oracle failure bounded to 10% of portfolio

### Complexity to Build

Rating: 6/10 (Moderate)

### Time to Market

- Development: 4-5 weeks
- Paper trading: 3-4 weeks
- Controlled live launch: 2 weeks
- Full deployment: 2-3 weeks ramp
- Total: 11-14 weeks

---

## Architecture 2: Cross-Platform Statistical Arbitrage (RECOMMENDED ENTRY POINT)

### Strategy Description

Exploit systematic pricing differences between Polymarket and Kalshi (and potentially traditional betting markets) for equivalent events. When the same event is priced differently across platforms, buy on the cheaper platform and sell on the more expensive one, locking in a risk-free spread minus fees.

Primary targets: BTC/ETH/SOL price markets, US political events, and sports/entertainment with parallel markets on both platforms.

This is structurally different from intra-Polymarket speed arbitrage (which is dead for newcomers). Cross-platform arb depends on identifying equivalent markets, achieving near-simultaneous execution on both sides, and managing basis risk from non-identical resolution criteria.

### Technical Stack

- Python 3.12 (py-clob-client for Polymarket, Kalshi API client)
- NLP-based market mapping engine for cross-platform event matching
- Real-time spread calculator accounting for fees on both platforms
- Near-simultaneous dual-platform execution engine (target: <500ms combined)
- Basis risk monitoring and maximum exposure per pair
- VPS ($100/mo), Polygon RPC ($100/mo), Kalshi API (free tier), NewsAPI ($50/mo)

### Capital Requirements

- Minimum viable: $20,000 ($10K per platform)
- Recommended: $50,000 ($25K per platform)
- Monthly ops: ~$350
- First-year total (minimum): $24,200

### Expected Returns

| Scenario | Monthly | Annualized |
|----------|---------|------------|
| Best case | 3-5% | 36-60% |
| Expected | 1-2.5% | 12-30% |
| Worst case | -0.25 to -0.8% | -3 to -10% |

Estimated Sharpe ratio: 2.0-3.0

### Risk Factors

1. Basis risk: subtly different resolution criteria across platforms
2. One-leg execution failure creating unhedged directional exposure
3. Fee erosion on thin spreads (Polymarket 0-0.10% + Kalshi 7-10c per contract)
4. Kalshi lower liquidity limiting position sizes
5. Regulatory asymmetry between platforms
6. Oracle risk on Polymarket side

### Failure Modes and Mitigations

- One-leg failure: Atomic execution logic (unwind Leg 1 within 5 seconds if Leg 2 fails)
- Resolution mismatch: Curated market pair registry with verified identical resolution sources
- Platform outage: Per-platform heartbeats; halt new positions if either API unreachable
- Spread compression: 1.5% minimum spread threshold after all fees

### Complexity to Build

Rating: 7/10 (Moderate-High)

### Time to Market

- Development: 6-7 weeks
- Paper trading: 3-4 weeks
- Controlled live launch: 2 weeks
- Full deployment: 2-3 weeks ramp
- Total: 13-16 weeks

---

## Architecture 3: AI-Driven Information Edge

### Strategy Description

Build a continuously retrained probability estimation system that identifies markets where the price diverges significantly from "true" probability. Use NLP on news, social media, polling data, and on-chain signals to generate probability estimates. Take directional positions when model confidence exceeds a threshold and the market price diverges by a meaningful margin.

This is the highest-risk, highest-potential-return strategy. The French Whale (Theo) proved the information-edge approach can generate extraordinary returns ($85M), though his edge came from private polling data. This architecture automates the principle using public data sources.

Targets: Political events (polling aggregation), crypto price events (sentiment + on-chain), geopolitical events (news NLP), and niche markets with fewer sophisticated participants.

### Technical Stack

- Python 3.12 (py-clob-client, transformers, scikit-learn/XGBoost)
- Data pipeline: NewsAPI, GDELT, Google News RSS, X API, Reddit API, polling aggregator scrapers, Dune Analytics, PolyTrack whale tracking
- Model: Ensemble of logistic regression baseline + XGBoost feature model + LLM probability estimator (Claude API)
- Walk-forward validation with weekly retraining, Platt scaling for calibration
- Kelly criterion position sizing (0.25x fractional Kelly)
- VPS with GPU ($200-400/mo), Polygon RPC ($100/mo), data APIs ($300-500/mo), Claude API ($100-300/mo)
- Model performance dashboard (calibration curves, Brier scores), automated degradation alerts

### Capital Requirements

- Minimum viable: $10,000 (diversified small positions across 10-20 markets)
- Recommended: $25,000-$50,000 (20-40 markets with meaningful sizes)
- Monthly ops: ~$800-1,200
- First-year total (minimum): $19,600-$24,400

### Expected Returns

| Scenario | Monthly | Annualized |
|----------|---------|------------|
| Best case | 5-10% | 60-120% |
| Expected | 2-4% | 24-48% |
| Worst case | -1.7 to -3.3% | -20 to -40% |

Estimated Sharpe ratio: 0.8-1.5. Returns are episodic: richest during election seasons and major events, flat or negative during quiet periods.

### Risk Factors

1. Model miscalibration (systematic bias across all positions)
2. Edge decay (2-3 month strategy refresh cycle documented)
3. Overfitting on small sample sizes
4. Data source failure degrading model accuracy
5. Oracle manipulation (directional positions fully exposed)
6. Black swan events with no training data
7. Regulatory scrutiny from aggressive trading patterns

### Failure Modes and Mitigations

- Model degradation: Automated Brier score monitoring; halt trading if rolling 30-day calibration exceeds threshold
- Catastrophic single-event loss: Max 5% of portfolio per market, max 15% per event category
- Data pipeline failure: Redundant data sources; reduced position size when data is partial
- Edge decay: Monthly retrain cycle; automated alpha decay detection vs. random baseline
- Oracle manipulation: Position caps + avoidance of markets with subjective resolution criteria

### Complexity to Build

Rating: 8/10 (High)

### Time to Market

- Development: 9-10 weeks
- Paper trading and model validation: 4-6 weeks
- Controlled live launch: 3-4 weeks
- Full deployment: 3-4 weeks ramp
- Total: 19-24 weeks

---

## Architecture 4: Hybrid Market Making + Information Edge (LONG-TERM TARGET)

### Strategy Description

Combine the consistent revenue of market making with the higher-upside potential of information-edge trading. The market-making component provides baseline revenue and order flow intelligence. The information-edge component takes directional positions on high-conviction opportunities. The two interact: market making order flow serves as an additional signal for the information model, and the information model can tilt market-making quotes to accumulate inventory on the favored side.

This is the recommended long-term architecture for a serious operator. It hedges against the weaknesses of each standalone approach.

### Technical Stack

- All components from Architecture 1 + Architecture 3
- Integration layer: Redis Pub/Sub event bus connecting OMS with information model
- Order flow analytics: real-time aggressive order tracking, imbalance detection
- Capital allocation engine: dynamic allocation between components based on model confidence
- Python 3.12 primary, Rust for latency-sensitive quote management
- VPS with GPU ($300-500/mo), full data stack ($400-800/mo), Redis ($50/mo)

### Capital Requirements

- Minimum viable: $50,000 ($30K market making, $20K directional)
- Recommended: $100,000 ($60K market making, $40K directional)
- Monthly ops: ~$1,000-1,500
- First-year total (minimum): $62,000-$68,000

### Expected Returns

| Scenario | Monthly | Annualized |
|----------|---------|------------|
| Best case | 4-8% | 48-96% |
| Expected | 1.5-3.5% | 18-42% |
| Worst case | -0.8 to -2.1% | -10 to -25% |

Estimated Sharpe ratio: 1.2-2.0

### Risk Factors

All risks from Architecture 1 and Architecture 3 apply, plus:
- Interaction risk (information model overriding market making risk controls)
- Capital allocation conflicts between components
- Increased system complexity creating additional failure points

### Failure Modes and Mitigations

All mitigations from Architecture 1 and Architecture 3 apply, plus:
- Capital conflict: Hard 60/40 capital separation, max 20% overflow
- Complexity: Falls back to market-making-only mode if information layer fails
- Interaction bugs: Model suggestions are advisory only, market maker risk controls cannot be overridden

### Complexity to Build

Rating: 9/10 (Very High)

### Time to Market

- Development: 14-16 weeks
- Paper trading: 5-7 weeks
- Controlled live launch: 3-4 weeks
- Full deployment: 3-4 weeks ramp
- Total: 25-31 weeks

---

## Failure Analysis

### Catalog of Documented Failures

10 documented failures affecting Polymarket bot operators:

| # | Failure | Year | Impact | Root Cause | Preventable? |
|---|---------|------|--------|------------|-------------|
| 1 | Oracle manipulation: Ukraine mineral deal | Mar 2025 | $7M market | UMA whale (5M tokens, 3 accounts) | No |
| 2 | Oracle manipulation: UFO declassification | Dec 2025 | $16M market | Ambiguous criteria + whale voting | Partially |
| 3 | Oracle manipulation: Zelenskyy suit case | 2025 | $240M market | Interpretation gap + conflicted voters | Partially |
| 4 | Polycule Telegram bot hacked | Jan 2026 | $230K stolen | Third-party custody compromise | Yes |
| 5 | Malicious GitHub copy trading bot | 2025 | Multiple wallets drained | Supply chain malware in dependencies | Yes |
| 6 | Viral arbitrage bot failure | 2025-26 | User losses on fees/gas | Latency disadvantage (73% to sub-100ms bots) | Yes |
| 7 | Copy trading front-running | Ongoing | Systematic copier losses | Target wallets running decoy trades | Partially |
| 8 | Cloudflare outage | Nov 2025 | Unmanaged positions | Single point of failure (centralized CLOB) | Partially |
| 9 | Polygon network congestion | Dec 2025 | Settlement delays, locked capital | L2 dependency for settlement | Partially |
| 10 | Model overfit / regime change | Ongoing | Backtest-to-live divergence | Small samples, market structure changes | Partially |

### Key Insight

The three most catastrophic failures (F1, F2, F3) are all oracle-related and largely outside bot operator control. The most preventable failures (F4, F5, F6) relate to security hygiene and strategy selection. Infrastructure failures (F8, F9) require architectural resilience. Strategy failures (F7, F10) require continuous adaptation.

---

## Failure Mitigation Matrix

How each architecture addresses each documented failure mode.

Legend: MITIGATED (specific controls), PARTIAL (reduces risk), EXPOSED (vulnerable), N/A (not applicable)

| Failure | Arch 1: Market Making | Arch 2: Cross-Platform Arb | Arch 3: Info Edge | Arch 4: Hybrid |
|---------|----------------------|---------------------------|-------------------|----------------|
| F1: Oracle (Ukraine) | PARTIAL | PARTIAL | EXPOSED | PARTIAL |
| F2: Oracle (UFO) | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| F3: Oracle (Zelenskyy) | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| F4: Bot hack | MITIGATED | MITIGATED | MITIGATED | MITIGATED |
| F5: Malicious code | MITIGATED | MITIGATED | MITIGATED | MITIGATED |
| F6: Latency arb failure | N/A | PARTIAL | N/A | N/A |
| F7: Copy trade front-run | N/A | N/A | PARTIAL | PARTIAL |
| F8: Cloudflare outage | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| F9: Polygon congestion | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| F10: Model overfit | PARTIAL | PARTIAL | EXPOSED | PARTIAL |

### Mitigation Scores

| Architecture | MITIGATED | PARTIAL | EXPOSED | N/A | Defensive Score |
|---|---|---|---|---|---|
| Arch 1: Market Making | 2 | 6 | 0 | 2 | Strong |
| Arch 2: Cross-Platform Arb | 2 | 7 | 0 | 1 | Strong |
| Arch 3: Info Edge | 2 | 5 | 2 | 1 | Moderate |
| Arch 4: Hybrid | 2 | 8 | 0 | 0 | Strongest |

Architecture 4 has the broadest coverage (no EXPOSED or N/A ratings). Architecture 3 is the only one with EXPOSED ratings (oracle manipulation and model overfit).

---

## Capital and Timeline Comparison

| Dimension | Arch 1 | Arch 2 | Arch 3 | Arch 4 |
|-----------|--------|--------|--------|--------|
| Minimum Capital | $50,000 | $20,000 | $10,000 | $50,000 |
| Recommended Capital | $100,000 | $50,000 | $25,000-$50,000 | $100,000 |
| Monthly Ops Cost | $300 | $350 | $800-$1,200 | $1,000-$1,500 |
| First-Year Cost (min) | $53,600 | $24,200 | $19,600-$24,400 | $62,000-$68,000 |
| Development Time | 4-5 weeks | 6-7 weeks | 9-10 weeks | 14-16 weeks |
| Paper Trading | 3-4 weeks | 3-4 weeks | 4-6 weeks | 5-7 weeks |
| Total to Full Operation | 11-14 weeks | 13-16 weeks | 19-24 weeks | 25-31 weeks |
| Complexity (1-10) | 6 | 7 | 8 | 9 |
| Expected Monthly Return | 0.8-1.5% | 1-2.5% | 2-4% | 1.5-3.5% |
| Annualized Return (expected) | 10-18% | 12-30% | 24-48% | 18-42% |
| Worst Case Annual | -5 to -15% | -3 to -10% | -20 to -40% | -10 to -25% |
| Sharpe Ratio (est.) | 1.5-2.5 | 2.0-3.0 | 0.8-1.5 | 1.2-2.0 |

---

## Recommended Next Steps

### Phase 1 (Weeks 1-16): Build Architecture 2 (Cross-Platform Arb)

Rationale: Lowest capital requirement ($20K), best risk-adjusted returns (highest Sharpe ratio at 2.0-3.0), structural rather than speed-dependent edge, and moderate complexity. Cross-platform arb is the most accessible entry point because it exploits market structure inefficiencies rather than requiring superior models or infrastructure.

Actions:
1. Set up Kalshi account and verify API access
2. Create Polymarket wallet and fund with initial USDC
3. Build market mapping engine (NLP matching of equivalent events across platforms)
4. Build dual-platform execution engine with atomic leg protection
5. Paper trade for 3-4 weeks, targeting crypto price markets first (most frequent, most liquid)
6. Deploy $5K initial capital across 3-5 market pairs
7. Ramp to $20K over 4-6 weeks based on live performance

### Phase 2 (Weeks 8-24, overlapping): Develop Architecture 3 (Information Edge)

Rationale: Highest absolute return potential. Begin development while Phase 1 generates revenue. The data pipeline and model development take 9-10 weeks, and an additional 4-6 weeks of paper trading are needed before deploying capital.

Actions:
1. Build data ingestion pipeline (news, social, polling)
2. Develop ensemble probability model
3. Paper trade alongside live Phase 1 arb operations
4. Deploy $5-10K initial capital when model calibration is validated

### Phase 3 (Month 6+): Evaluate Architecture 4 (Hybrid)

Rationale: Only pursue the hybrid if both Phase 1 and Phase 2 are individually profitable. The hybrid adds significant complexity and should only be built when the components are proven.

Decision gate: If Phase 1 and Phase 2 are each generating positive returns after 3 months of live operation, begin hybrid integration. If either is underperforming, optimize it first.

### What NOT to Do

- Do not build pure speed arbitrage. The sub-100ms bot ecosystem is impenetrable without institutional infrastructure.
- Do not use third-party bots or copy trading services. The security and front-running risks are well documented.
- Do not deploy real capital without completing the paper trading phase. The gap between backtest and live performance is large and well documented.
- Do not concentrate more than 5% of total capital in any single market. Oracle manipulation risk makes this a portfolio-survival issue.
- Do not ignore operational costs. At minimum capital levels, $300-1,200/month in infrastructure eats directly into returns and must be accounted for in breakeven calculations.

### Critical Success Factors

1. Discipline on paper trading timelines (do not skip or shorten)
2. Robust position sizing (never risk more than you can afford to lose entirely on oracle manipulation)
3. Continuous strategy refresh (2-3 month cycle for information-edge models)
4. Monitoring oracle governance (UMA token distribution, upcoming disputes) as ongoing operational intelligence
5. Regulatory awareness (track CFTC rule changes, EU MiCA developments, state-level actions)

---

## Sources

All data points in this report are sourced from the sub1 comprehensive research document, supplemented by targeted research on specific failure incidents. Key sources include:

Platform and API:
- Polymarket Documentation (docs.polymarket.com)
- py-clob-client SDK (github.com/Polymarket/py-clob-client)
- UMA Oracle documentation (docs.uma.xyz)

Failure Incidents:
- Oracle Manipulation 2025 (orochi.network/blog/oracle-manipulation-in-polymarket-2025)
- UFO Market Resolution (cryptoslate.com, December 2025)
- $2M Whale Loss Analysis (ainvest.com, January 2026)
- Polycule Bot Hack (rootdata.com, January 2026)
- Malicious GitHub Bot (bitrue.com, 2025)
- Viral Arbitrage Bot Failure (phemex.com, 2025)

Performance Data:
- Arbitrage Bot Profits (finance.yahoo.com)
- 92% Trader Loss Rate (medium.com/technology-hits)
- French Whale Case Study (polytrackhq.app)
- AI Bot $2.2M Profit (medium.com/illumination)
- Automated Market Making Guide (news.polymarket.com)

Infrastructure Incidents:
- Cloudflare Outage November 2025 (thestreet.com)
- Polygon Network Issues December 2025 (bitget.com)

Regulatory:
- CFTC Settlement and Relaunch (cftc.gov, gamblinginsider.com)
- Nevada Gaming Board Action (gamblinginsider.com, January 2026)
