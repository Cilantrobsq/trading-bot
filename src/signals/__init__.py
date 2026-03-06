"""
Signal modules for the trading bot.

Exports all signal dataclasses and fetcher classes for use by
the orchestration layer.
"""

from src.signals.macro import TickerSignal, MacroSignalFetcher
from src.signals.news import NewsItem, NewsFeedMonitor
from src.signals.fred_macro import FredSignal, FredMacroFetcher
from src.signals.sentiment import SentimentSignal, SentimentFetcher
from src.signals.prediction_markets import PredictionMarketSignal, PredictionMarketAggregator
from src.signals.llm_analyzer import LLMAnalysis, LLMNewsAnalyzer
from src.signals.earnings import EarningsSignal, EarningsFetcher

__all__ = [
    # Existing
    "TickerSignal", "MacroSignalFetcher",
    "NewsItem", "NewsFeedMonitor",
    # New
    "FredSignal", "FredMacroFetcher",
    "SentimentSignal", "SentimentFetcher",
    "PredictionMarketSignal", "PredictionMarketAggregator",
    "LLMAnalysis", "LLMNewsAnalyzer",
    "EarningsSignal", "EarningsFetcher",
]
