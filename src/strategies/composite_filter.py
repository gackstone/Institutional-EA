"""
Composite filter module that combines multiple FilterModule instances.
It evaluates each filter in order and returns the first failure, otherwise passes.
"""

from __future__ import annotations

from typing import List

from src.strategies.base import FilterModule, FilterResult, RawSignal, StrategyContext


class CompositeFilter(FilterModule):
    def __init__(self, filters: List[FilterModule]):
        self.filters = filters

    def filter_signal(self, signal: RawSignal, ctx: StrategyContext) -> FilterResult:
        for f in self.filters:
            result = f.filter_signal(signal, ctx)
            if not result.passed:
                return result
        return FilterResult(passed=True, details="All composite filters passed")
