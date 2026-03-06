"""
Walk-forward validator for the trading bot.

Prevents overfitting -- the #2 killer of trading bots -- by
testing signal accuracy on out-of-sample data using rolling
train/test windows.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] backtester: {msg}")


@dataclass
class SignalValidation:
    """Results of walk-forward validation for a single signal."""
    signal_name: str
    avg_accuracy: float            # mean accuracy across all test windows
    accuracy_std: float            # std dev of accuracy across windows
    is_degrading: bool             # True if accuracy is declining over time
    windows_tested: int
    best_window_accuracy: float
    worst_window_accuracy: float
    recommendation: str            # "use", "caution", or "discard"
    window_accuracies: List[float] = field(default_factory=list)
    information_ratio: Optional[float] = None
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_name": self.signal_name,
            "avg_accuracy": round(self.avg_accuracy, 4),
            "accuracy_std": round(self.accuracy_std, 4),
            "is_degrading": self.is_degrading,
            "windows_tested": self.windows_tested,
            "best_window_accuracy": round(self.best_window_accuracy, 4),
            "worst_window_accuracy": round(self.worst_window_accuracy, 4),
            "recommendation": self.recommendation,
            "window_accuracies": [round(a, 4) for a in self.window_accuracies],
            "information_ratio": round(self.information_ratio, 4) if self.information_ratio is not None else None,
            "timestamp": self.timestamp,
        }


class WalkForwardValidator:
    """
    Walk-forward validation framework for trading signals.

    Splits historical data into rolling train/test windows and
    measures signal accuracy on each test set. Detects overfitting
    by checking for accuracy degradation over time.

    Usage:
        validator = WalkForwardValidator("/path/to/trading-bot")

        # With raw signal/outcome arrays
        signals = [1, 0, 1, 1, 0, ...]  # predicted outcomes
        outcomes = [1, 1, 1, 0, 0, ...]  # actual outcomes
        result = validator.validate_signal("my_signal", signals, outcomes)
        print(result.recommendation)  # "use", "caution", or "discard"
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.validations_dir = os.path.join(project_root, "data", "validations")
        os.makedirs(self.validations_dir, exist_ok=True)
        _log("initialized")

    def validate_signal(
        self,
        signal_name: str,
        signals: List[Any],
        outcomes: List[Any],
        window_size: int = 30,
        step_size: int = 7,
    ) -> SignalValidation:
        """
        Run walk-forward validation on a signal.

        Splits data into rolling windows of window_size, stepping
        by step_size. For each window, the first half is "training"
        context and the second half is the test set where accuracy
        is measured.

        Args:
            signal_name: Name identifier for the signal.
            signals: List of signal predictions (any type, compared via ==).
            outcomes: List of actual outcomes (same length as signals).
            window_size: Size of each rolling window.
            step_size: Number of observations to step forward between windows.

        Returns:
            SignalValidation with accuracy metrics and recommendation.
        """
        now = datetime.now(timezone.utc).isoformat()

        if len(signals) != len(outcomes):
            _log(f"signal/outcome length mismatch: {len(signals)} vs {len(outcomes)}")
            return self._empty_validation(signal_name, now,
                                          "Cannot validate: signal/outcome length mismatch")

        n = len(signals)
        if n < window_size:
            _log(f"insufficient data: {n} < window_size {window_size}")
            return self._empty_validation(signal_name, now,
                                          f"Cannot validate: need {window_size} data points, have {n}")

        # Walk forward through windows
        accuracies = []
        test_size = max(1, window_size // 2)

        start = 0
        while start + window_size <= n:
            # Test set is the second half of the window
            test_start = start + window_size - test_size
            test_end = start + window_size

            window_signals = signals[test_start:test_end]
            window_outcomes = outcomes[test_start:test_end]

            # Calculate accuracy for this window
            if len(window_signals) > 0:
                correct = sum(
                    1 for s, o in zip(window_signals, window_outcomes)
                    if s == o
                )
                accuracy = correct / len(window_signals)
                accuracies.append(accuracy)

            start += step_size

        if not accuracies:
            return self._empty_validation(signal_name, now,
                                          "No valid windows produced")

        # Compute metrics
        avg_acc = float(np.mean(accuracies))
        std_acc = float(np.std(accuracies)) if len(accuracies) > 1 else 0.0
        best_acc = float(np.max(accuracies))
        worst_acc = float(np.min(accuracies))

        # Check for degradation: is accuracy trending downward?
        is_degrading = self._check_degradation(accuracies)

        # Recommendation logic
        recommendation = self._make_recommendation(avg_acc, std_acc, is_degrading, len(accuracies))

        result = SignalValidation(
            signal_name=signal_name,
            avg_accuracy=avg_acc,
            accuracy_std=std_acc,
            is_degrading=is_degrading,
            windows_tested=len(accuracies),
            best_window_accuracy=best_acc,
            worst_window_accuracy=worst_acc,
            recommendation=recommendation,
            window_accuracies=accuracies,
            timestamp=now,
        )

        _log(
            f"validated '{signal_name}': avg_acc={avg_acc:.3f}, "
            f"std={std_acc:.3f}, degrading={is_degrading}, "
            f"recommendation={recommendation}"
        )

        # Persist
        self._save_validation(result)

        return result

    def validate_signal_with_scorer(
        self,
        signal_name: str,
        data: List[Any],
        scorer: Callable[[List[Any], List[Any]], float],
        window_size: int = 30,
        step_size: int = 7,
    ) -> SignalValidation:
        """
        Walk-forward validation with a custom scoring function.

        The scorer receives (train_data, test_data) and returns
        an accuracy/score float between 0 and 1.

        This is useful for signals that require training (e.g.,
        ML models) before prediction.

        Args:
            signal_name: Name identifier.
            data: Full historical dataset.
            scorer: Function(train_data, test_data) -> float score.
            window_size: Rolling window size.
            step_size: Step between windows.

        Returns:
            SignalValidation result.
        """
        now = datetime.now(timezone.utc).isoformat()
        n = len(data)

        if n < window_size:
            return self._empty_validation(signal_name, now,
                                          f"Need {window_size} points, have {n}")

        accuracies = []
        train_size = window_size // 2
        test_size = window_size - train_size

        start = 0
        while start + window_size <= n:
            train_data = data[start:start + train_size]
            test_data = data[start + train_size:start + window_size]

            try:
                score = scorer(train_data, test_data)
                accuracies.append(float(score))
            except Exception as e:
                _log(f"scorer failed on window at {start}: {e}")

            start += step_size

        if not accuracies:
            return self._empty_validation(signal_name, now, "No valid windows")

        avg_acc = float(np.mean(accuracies))
        std_acc = float(np.std(accuracies)) if len(accuracies) > 1 else 0.0
        is_degrading = self._check_degradation(accuracies)
        recommendation = self._make_recommendation(avg_acc, std_acc, is_degrading, len(accuracies))

        result = SignalValidation(
            signal_name=signal_name,
            avg_accuracy=avg_acc,
            accuracy_std=std_acc,
            is_degrading=is_degrading,
            windows_tested=len(accuracies),
            best_window_accuracy=float(np.max(accuracies)),
            worst_window_accuracy=float(np.min(accuracies)),
            recommendation=recommendation,
            window_accuracies=accuracies,
            timestamp=now,
        )

        self._save_validation(result)
        return result

    def calculate_information_ratio(
        self,
        signal_returns: List[float],
        benchmark_returns: List[float],
    ) -> Optional[float]:
        """
        Calculate the information ratio: how much alpha does a signal provide?

        IR = mean(excess_returns) / std(excess_returns)
        where excess_returns = signal_returns - benchmark_returns

        A positive IR means the signal adds value. IR > 0.5 is good,
        IR > 1.0 is excellent.

        Args:
            signal_returns: Returns when following the signal.
            benchmark_returns: Returns of the benchmark (e.g., buy-and-hold).

        Returns:
            Information ratio float, or None if insufficient data.
        """
        if len(signal_returns) != len(benchmark_returns):
            _log("IR calculation: length mismatch")
            return None

        if len(signal_returns) < 5:
            _log("IR calculation: insufficient data")
            return None

        excess = np.array(signal_returns) - np.array(benchmark_returns)
        excess_std = float(np.std(excess))

        if excess_std == 0:
            return 0.0

        ir = float(np.mean(excess)) / excess_std
        _log(f"information ratio: {ir:.4f}")
        return ir

    def _check_degradation(self, accuracies: List[float]) -> bool:
        """
        Check if accuracy is degrading over time.

        Uses a simple linear regression slope. If the slope is
        significantly negative, the signal is degrading.
        """
        if len(accuracies) < 4:
            return False

        x = np.arange(len(accuracies), dtype=float)
        y = np.array(accuracies, dtype=float)

        # Simple linear regression
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        ss_xx = np.sum((x - x_mean) ** 2)

        if ss_xx == 0:
            return False

        slope = np.sum((x - x_mean) * (y - y_mean)) / ss_xx

        # Degrading if slope is meaningfully negative
        # Threshold: -0.005 per window (e.g., 0.5% accuracy loss per window)
        return slope < -0.005

    def _make_recommendation(
        self,
        avg_accuracy: float,
        accuracy_std: float,
        is_degrading: bool,
        windows_tested: int,
    ) -> str:
        """
        Generate a recommendation based on validation metrics.

        Returns: "use", "caution", or "discard"
        """
        # Hard discard criteria
        if avg_accuracy < 0.45:
            return "discard"  # Worse than random
        if is_degrading and avg_accuracy < 0.55:
            return "discard"  # Degrading and barely above random

        # Caution criteria
        if is_degrading:
            return "caution"  # Degrading even if currently accurate
        if accuracy_std > 0.2:
            return "caution"  # Too inconsistent
        if windows_tested < 3:
            return "caution"  # Not enough data
        if avg_accuracy < 0.55:
            return "caution"  # Marginal edge

        # Good signal
        if avg_accuracy >= 0.55 and accuracy_std < 0.15:
            return "use"

        return "caution"

    def _empty_validation(
        self, signal_name: str, timestamp: str, reason: str
    ) -> SignalValidation:
        """Create a validation result for when validation cannot be performed."""
        return SignalValidation(
            signal_name=signal_name,
            avg_accuracy=0.0,
            accuracy_std=0.0,
            is_degrading=False,
            windows_tested=0,
            best_window_accuracy=0.0,
            worst_window_accuracy=0.0,
            recommendation="discard",
            window_accuracies=[],
            timestamp=timestamp,
        )

    def _save_validation(self, validation: SignalValidation) -> None:
        """Persist a validation result to disk."""
        try:
            filename = f"{validation.signal_name.replace(' ', '_').lower()}.json"
            filepath = os.path.join(self.validations_dir, filename)
            with open(filepath, "w") as f:
                json.dump(validation.to_dict(), f, indent=2)
            _log(f"saved validation to {filepath}")
        except Exception as e:
            _log(f"failed to save validation: {e}")

    def load_validations(self) -> List[Dict[str, Any]]:
        """Load all persisted validation results."""
        results = []
        if not os.path.isdir(self.validations_dir):
            return results
        for filename in sorted(os.listdir(self.validations_dir)):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.validations_dir, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                results.append(data)
            except Exception as e:
                _log(f"failed to load {filename}: {e}")
        return results


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import random

    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    validator = WalkForwardValidator(root)

    # Generate synthetic signal data
    random.seed(42)
    n = 200
    outcomes = [random.choice([0, 1]) for _ in range(n)]

    # Good signal: 70% accurate
    good_signals = []
    for o in outcomes:
        if random.random() < 0.70:
            good_signals.append(o)
        else:
            good_signals.append(1 - o)

    # Bad signal: 45% accurate
    bad_signals = []
    for o in outcomes:
        if random.random() < 0.45:
            bad_signals.append(o)
        else:
            bad_signals.append(1 - o)

    print("--- Good Signal ---")
    good_result = validator.validate_signal("good_signal", good_signals, outcomes)
    print(json.dumps(good_result.to_dict(), indent=2))

    print("\n--- Bad Signal ---")
    bad_result = validator.validate_signal("bad_signal", bad_signals, outcomes)
    print(json.dumps(bad_result.to_dict(), indent=2))

    # Information ratio
    signal_returns = [random.gauss(0.002, 0.01) for _ in range(100)]
    bench_returns = [random.gauss(0.001, 0.01) for _ in range(100)]
    ir = validator.calculate_information_ratio(signal_returns, bench_returns)
    print(f"\nInformation Ratio: {ir:.4f}" if ir else "IR: N/A")
