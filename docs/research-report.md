# Polymarket Trading Bots: Research Report and Architecture Proposals

Prepared for: Andres Hofmann (andres@thebsq.com)
Prepared by: Thymian (Research Specialist), Cilantro System
Date: 2026-03-06
Classification: Internal, Executive Decision-Making


## Executive Summary

Polymarket is the dominant prediction market platform, processing billions in trading volume on a hybrid architecture: off-chain order matching for speed, on-chain Polygon settlement in USDC for transparency. The platform re-entered the US market in December 2025 as a CFTC-regulated Designated Contract Market, adding KYC requirements and broker-mediated access for US users.

The bot ecosystem is mature and brutally competitive. Between April 2024 and April 2025, arbitrage bots extracted approximately $40 million in profits, with 73% captured by sub-100ms execution bots. Only 7.6% of wallets on Polymarket are profitable. The average arbitrage window has compressed from 12.3 seconds in 2024 to just 2.7 seconds today, making pure speed arbitrage effectively dead for newcomers without institutional-grade infrastructure.

We identified and cataloged 10 documented failure modes affecting bot operators. The three most catastrophic failures are all oracle-related (UMA voting manipulation), totaling over $263 million in affected markets, and are largely unhedgeable. The most preventable failures relate to security hygiene (a $230K bot hack, malicious open-source code) and strategy selection (trying to compete on speed against sub-100ms bots).

Four concrete bot architectures were designed and analyzed: (1) Conservative Market Making ($50K minimum, 10-18% expected annual return, Sharpe 1.5-2.5), (2) Cross-Platform Statistical Arbitrage ($20K minimum, 12-30% expected annual return, Sharpe 2.0-3.0), (3) AI-Driven Information Edge ($10K minimum, 24-48% expected annual return, Sharpe 0.8-1.5), and (4) Hybrid Market Making plus Information Edge ($50K minimum, 18-42% expected annual return, Sharpe 1.2-2.0).

Our recommendation: Start with Architecture 2 (Cross-Platform Arbitrage) as the entry point. It offers the best risk-adjusted returns (highest Sharpe ratio), lowest capital requirement, and exploits structural market inefficiencies rather than requiring superior speed or models. Simultaneously develop Architecture 3 (AI Information Edge) as a medium-term high-upside play. The hybrid Architecture 4 is the long-term target but should not be the entry point due to complexity. Do not build pure speed arbitrage under any circumstances.


## 1. Market Overview

### 1.1 How Polymarket Works

Polymarket structures events as binary questions with YES and NO outcomes. Each share is priced between $0.00 and $1.00, representing the market-implied probability. YES and NO shares for any market always sum to $1.00. Winning shares pay out $1.00 USDC; losing shares pay $0.00.

The platform migrated from an Automated Market Maker (AMM) to a hybrid Central Limit Order Book (CLOB) in late 2022. Orders are matched off-chain for low latency and tight spreads, while settlement occurs on-chain via smart contracts on Polygon. The CLOB supports limit orders, market orders, Fill or Kill (FOK), Immediate or Cancel (IOC), and post-only orders (added January 2026).

Settlement costs on Polygon are negligible ($0.01-$0.50 per trade), with 2-3 second confirmation times. All trading is denominated in USDC (transitioning from bridged USDC.e to native USDC under a Circle partnership).

### 1.2 Resolution Mechanism

Market resolution relies on UMA's Optimistic Oracle, which operates as an escalation game:
1. Anyone proposes an answer by submitting a bond
2. A 2-hour challenge period follows; if unchallenged, the proposal is accepted
3. First disputes are ignored (anti-spam); second disputes escalate to UMA tokenholder vote
4. Approximately 98.5% of resolutions settle without escalation

Critical vulnerability: Concentrated UMA token ownership means a whale with ~5 million UMA tokens (25% of typical vote participation) can force false resolutions. This has been exploited multiple times (see Section 5).

### 1.3 Fee Structure

Most markets have no trading fees. Exceptions:
- 15-minute crypto markets: taker fees up to 3% (effective ~1.56% at p=0.50)
- US exchange (DCM): 0.10% taker fee
- Maker Rebates Program: post-only orders that add liquidity earn daily USDC rebates

For arbitrage bots, spreads must exceed 2.5-3% to be profitable after costs in fee-enabled markets.

### 1.4 Competitive Landscape

- 92% of Polymarket traders lose money
- 73% of arbitrage profits captured by sub-100ms bots
- Average arbitrage window: 2.7 seconds (down from 12.3s in 2024)
- Top leaderboard positions dominated by quant funds, prop shops, and full-time specialists
- Consistently profitable traders hold positions 7+ days (information-edge approach)
- No native stop-losses, position limits, or circuit breakers on the platform

### 1.5 Regulatory Status

Polymarket paid a $1.4M CFTC penalty in 2022 for operating unregistered. In November 2025, it received CFTC Designated Contract Market status and relaunched for US residents in December 2025. US users must complete KYC and trade through approved brokers. The DOJ and CFTC ended their investigations without new charges in July 2025.

State-level complications remain: Nevada's Gaming Control Board filed a civil complaint in January 2026 arguing event contracts resemble sports betting. Other states may follow.

Non-US users can still trade directly from crypto wallets without KYC on the global platform.


## 2. Existing Bot Strategies

### 2.1 Market Making

Place simultaneous buy and sell orders on both sides to capture bid-ask spread. Win rates of 78-85%, monthly returns of 0.5-2%, low drawdown (<1%). Requires $50K+ capital. Open-source implementations exist (poly-maker, polymarket-market-maker-bot). Key risk: adverse selection from informed traders during breaking events.

### 2.2 Arbitrage

Three types operate on Polymarket:

Intra-market logical arbitrage: When YES + NO shares deviate from summing to $1.00, or correlated markets have inconsistent pricing. "Shockingly common" according to multiple sources.

Cross-platform arbitrage: Exploiting price differences between Polymarket and Kalshi or traditional bookmakers. Less speed-dependent, more operationally complex. Open-source Polymarket-Kalshi BTC arbitrage bot exists.

Temporal/speed arbitrage: Exploiting the lag between real-world events and Polymarket price adjustment. Documented 98% win rate on $4K-$5K trades in BTC/ETH/SOL 15-minute markets. Declining viability as windows shrink.

### 2.3 Information-Edge

The highest-potential approach. Includes:
- News-reactive bots: NLP on breaking news, 30-second to 5-minute window
- Model-based probability estimation: ML models vs. market price divergence
- Private data: The French Whale (Theo) made $85M using commissioned private polling data

Polymarket's official AI agent framework (github.com/Polymarket/agents) provides a reference architecture.

### 2.4 Sentiment and Copy Trading

Sentiment bots analyze social media signals but are the least proven category (noisy, slow). Copy trading mirrors profitable wallets but faces front-running risk from target wallets running decoy trades.


## 3. Bot Architecture Proposals

### Architecture 1: Conservative Market Making

Strategy: Two-sided liquidity provision across 5-20 markets, capturing bid-ask spread and maker rebates.

Capital: $50K minimum, $100K recommended
Monthly ops: ~$300
Expected return: 0.8-1.5% monthly (10-18% annualized)
Worst case: -5 to -15% annualized
Sharpe ratio: 1.5-2.5
Complexity: 6/10
Time to market: 11-14 weeks

Stack: Python (py-clob-client), WebSocket feeds, custom OMS, SQLite, VPS + Polygon RPC
Key mitigations: Rapid quote cancellation on news (2s target), $10K max net directional exposure per market, kill switch on heartbeat loss

### Architecture 2: Cross-Platform Statistical Arbitrage (RECOMMENDED ENTRY POINT)

Strategy: Exploit pricing differences between Polymarket and Kalshi for equivalent events. Buy cheap, sell expensive, lock in spread minus fees. Structural edge, not speed-dependent.

Primary targets: BTC/ETH/SOL price markets, US political events, sports with parallel markets.

Capital: $20K minimum, $50K recommended
Monthly ops: ~$350
Expected return: 1-2.5% monthly (12-30% annualized)
Worst case: -3 to -10% annualized
Sharpe ratio: 2.0-3.0 (best of all architectures)
Complexity: 7/10
Time to market: 13-16 weeks

Stack: Python, py-clob-client + Kalshi API, NLP market mapping engine, dual-platform execution (<500ms combined), basis risk monitoring
Key mitigations: Atomic execution (unwind Leg 1 within 5s if Leg 2 fails), curated market pair registry with verified resolution sources, 1.5% minimum spread threshold after fees

### Architecture 3: AI-Driven Information Edge

Strategy: Continuously retrained probability models identifying markets where price diverges from "true" probability. NLP on news, social, polling, on-chain signals. Directional positions on high-conviction opportunities.

Capital: $10K minimum, $25-50K recommended
Monthly ops: ~$800-1,200
Expected return: 2-4% monthly (24-48% annualized)
Worst case: -20 to -40% annualized
Sharpe ratio: 0.8-1.5 (returns are episodic, richest during election seasons)
Complexity: 8/10
Time to market: 19-24 weeks

Stack: Python, ensemble models (logistic regression + XGBoost + LLM), walk-forward validation, Kelly criterion position sizing (0.25x fractional), GPU VPS, multiple data APIs
Key mitigations: Automated Brier score monitoring, max 5% portfolio per market, max 15% per event category, monthly retrain cycle

### Architecture 4: Hybrid Market Making + Information Edge (LONG-TERM TARGET)

Strategy: Combine market making revenue with information-edge directional positions. Market making provides baseline income and order flow intelligence. Information model takes high-conviction positions and tilts quotes to accumulate favorable inventory.

Capital: $50K minimum, $100K recommended
Monthly ops: ~$1,000-1,500
Expected return: 1.5-3.5% monthly (18-42% annualized)
Worst case: -10 to -25% annualized
Sharpe ratio: 1.2-2.0
Complexity: 9/10
Time to market: 25-31 weeks

Stack: All components from Architecture 1 + 3, Redis Pub/Sub event bus, order flow analytics, dynamic capital allocation engine, Python primary + Rust for latency-sensitive quote management
Key mitigations: Hard 60/40 capital separation, fallback to market-making-only on information layer failure, model suggestions advisory only (cannot override risk controls)


## 4. Technical Implementation Details

### 4.1 API and SDK

Three API surfaces:
- CLOB API (clob.polymarket.com): real-time prices, order book, order placement
- Data API (data-api.polymarket.com): positions, trade history, analytics
- Gamma Markets API: market metadata, conditions, events

Authentication: Two levels. L1 uses Ethereum private key to derive credentials. L2 uses apiKey/secret/passphrase with HMAC-SHA256 signing.

Rate limits (Cloudflare throttling, requests delayed not rejected):
- Public endpoints: 60 req/min
- /books endpoint: 300 req/10s
- Non-trading queries: up to 1,000/hour
- WebSocket: virtually unlimited for subscribed instruments

Official SDKs:
- Python: py-clob-client (github.com/Polymarket/py-clob-client)
- Rust: rs-clob-client (github.com/Polymarket/rs-clob-client)

Known limitations: no official backtesting framework, no sandbox/testnet, documentation gaps on edge cases, WebSocket drops during high-traffic events.

### 4.2 Open-Source Implementations

- Polymarket/agents: official AI agent framework (news retrieval, LLM prompting, trade execution)
- poly-maker: configurable market making with Google Sheets parameter management
- OctoBot-Prediction-Market: copy trading and arbitrage
- polymarket-kalshi-btc-arbitrage-bot: cross-platform BTC price market arbitrage
- 0xalberto/polymarket-arbitrage-bot: intra-market arbitrage scanner

### 4.3 Infrastructure Requirements

Minimum for competitive operation:
- VPS near Polymarket infrastructure: $50-200/month
- Polygon RPC node access: $50-200/month
- Data feeds (news, social, polling): $100-500/month
- Total baseline: $200-900/month


## 5. Risk Analysis

### 5.1 Documented Failure Catalog

10 documented failures affecting Polymarket bot operators:

1. Oracle manipulation, Ukraine mineral deal (March 2025): $7M market. UMA whale cast 5M tokens across 3 accounts to force false resolution. Polymarket refused refunds.

2. Oracle manipulation, UFO declassification (December 2025): $16M market resolved incorrectly via whale UMA voting on ambiguous criteria.

3. Oracle manipulation, Zelenskyy suit case (2025): $240M market affected by interpretation gap and conflicted voters.

4. Polycule Telegram bot hacked (January 2026): $230K stolen due to third-party custody compromise.

5. Malicious GitHub copy trading bot (2025): Supply chain attack stealing private keys via trojanized dependencies.

6. Viral arbitrage bot failure (2025-26): Users lost money trying speed arbitrage without competitive infrastructure.

7. Copy trading front-running (ongoing): Target wallets running decoy trades to exploit copiers.

8. Cloudflare outage (November 2025): Unmanaged positions during centralized CLOB downtime.

9. Polygon network congestion (December 2025): Settlement delays locking capital.

10. Model overfit / regime change (ongoing): Backtest-to-live divergence from small samples and market structure changes.

### 5.2 Failure Mitigation Matrix

Architecture 2 (Cross-Platform Arb) and Architecture 1 (Market Making) have zero EXPOSED ratings. Architecture 3 (Information Edge) has two EXPOSED ratings (oracle manipulation on directional positions, model overfit). Architecture 4 (Hybrid) has the broadest coverage with no EXPOSED or N/A ratings.

The three most catastrophic failures (oracle manipulation) are largely outside bot operator control. The only defense is position sizing: never concentrate more than 5% of total capital in any single market.

### 5.3 Survivorship Bias Warning

Publicly shared P&L data overwhelmingly comes from winners. The $85M French Whale, the $2.2M AI bot, and the $40M aggregate arbitrage profits are exceptions. For every documented success, hundreds of undocumented losses exist. New entrants should budget for a 2-3 month learning phase with potential losses of 20-50% of initial capital.


## 6. Recommendations

### Recommended Execution Plan

Phase 1 (Weeks 1-16): Build Architecture 2 (Cross-Platform Arbitrage)
- Lowest capital requirement ($20K), best risk-adjusted returns (Sharpe 2.0-3.0)
- Set up Kalshi account and Polymarket wallet
- Build NLP market mapping engine and dual-platform execution
- Paper trade 3-4 weeks targeting crypto price markets first
- Deploy $5K initial, ramp to $20K over 4-6 weeks based on live results

Phase 2 (Weeks 8-24, overlapping): Develop Architecture 3 (Information Edge)
- Highest absolute return potential (24-48% annualized)
- Build data pipeline (news, social, polling) and ensemble probability model
- Paper trade alongside live Phase 1 operations
- Deploy $5-10K initial when model calibration is validated

Phase 3 (Month 6+): Evaluate Architecture 4 (Hybrid)
- Only pursue if both Phase 1 and Phase 2 are individually profitable after 3 months live
- If either is underperforming, optimize it first before adding complexity

### Capital Summary

- Minimum to start (Phase 1 only): $20,000 trading capital + ~$350/month infrastructure
- Recommended to start (Phase 1 + Phase 2 development): $30,000 trading capital + ~$1,000/month infrastructure
- Full deployment (all architectures): $100,000+ trading capital + ~$1,500/month infrastructure
- First $5,000 should be considered tuition / learning cost

### Critical "Do Not" List

- Do not build pure speed arbitrage (sub-100ms bots dominate, impenetrable without institutional infrastructure)
- Do not use third-party bots or copy trading services (security and front-running risks well documented)
- Do not deploy real capital without completing paper trading phase
- Do not concentrate more than 5% of capital in any single market (oracle manipulation risk)
- Do not ignore operational costs in breakeven calculations
- Do not assume backtest results will hold in live trading
- Do not skip the paper trading timeline under any circumstances

### Key Success Factors

1. Discipline on paper trading timelines
2. Robust position sizing (Kelly criterion, fractional sizing)
3. Continuous strategy refresh every 2-3 months for information-edge models
4. Monitoring UMA oracle governance as ongoing operational intelligence
5. Regulatory tracking (CFTC changes, EU MiCA, state-level actions)


## Sources

Platform and API:
- Polymarket Documentation: https://docs.polymarket.com/
- CLOB Introduction: https://docs.polymarket.com/developers/CLOB/introduction
- UMA Oracle: https://docs.uma.xyz/protocol-overview/how-does-umas-oracle-work
- Fee Structure: https://docs.polymarket.com/trading/fees
- Rate Limits: https://docs.polymarket.com/quickstart/introduction/rate-limits
- Circle/USDC Partnership: https://www.pymnts.com/blockchain/2026/polymarket-taps-circle-to-support-dollar-denominated-settlements/

SDKs and Open Source:
- py-clob-client: https://github.com/Polymarket/py-clob-client
- rs-clob-client: https://github.com/Polymarket/rs-clob-client
- Polymarket/agents: https://github.com/Polymarket/agents
- poly-maker: https://github.com/warproxxx/poly-maker
- Polymarket-Kalshi arbitrage: https://github.com/CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot
- Arbitrage scanner: https://github.com/0xalberto/polymarket-arbitrage-bot

Trading Performance:
- Arbitrage Bots (Yahoo Finance): https://finance.yahoo.com/news/arbitrage-bots-dominate-polymarket-millions-100000888.html
- 92% Loss Rate (Medium): https://medium.com/technology-hits/why-92-of-polymarket-traders-lose-money-and-how-bots-changed-the-game-2a60cd27df36
- 4 Bot Strategies (Medium): https://medium.com/illumination/beyond-simple-arbitrage-4-polymarket-strategies-bots-actually-profit-from-in-2026-ddacc92c5b4f
- French Whale Case Study: https://www.polytrackhq.app/blog/polymarket-french-whale-case-study
- Market Making Guide: https://news.polymarket.com/p/automated-market-making-on-polymarket
- Leaderboard: https://polymarket.com/leaderboard/overall/monthly/profit

Failures and Risks:
- Oracle Manipulation 2025: https://orochi.network/blog/oracle-manipulation-in-polymarket-2025
- Users Lost Millions to Bots: https://www.dlnews.com/articles/markets/polymarket-users-lost-millions-of-dollars-to-bot-like-bettors-over-the-past-year/

Legal and Regulatory:
- CFTC 2022 Settlement: https://www.cftc.gov/PressRoom/PressReleases/8478-22
- US Legality 2026: https://www.gamblinginsider.com/in-depth/106291/is-polymarket-legal-in-the-us
- Polymarket Returns to US: https://reason.com/2026/01/04/the-return-of-polymarket/
