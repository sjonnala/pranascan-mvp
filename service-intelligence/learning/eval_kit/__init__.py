"""Stratified rPPG evaluation kit: per-window/per-session scoring, fairness gates, error analysis.

Entry points:

- ``python -m learning.eval_kit.eval_runner`` evaluates estimators on a ``DatasetSessionV2``
  manifest and exits 0 when the release gates pass, 1 when they fail.
- ``python -m learning.eval_kit.error_analysis`` exports the worst sessions for open coding.
"""
