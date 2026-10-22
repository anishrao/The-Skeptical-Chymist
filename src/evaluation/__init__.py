# Lazy attribute resolution to break circular imports between agents and benchmark_runner
__all__ = ["PerturbMatBenchmarkRunner", "compute_brier_score"]


def __getattr__(name: str):
    if name == "PerturbMatBenchmarkRunner":
        from .benchmark_runner import PerturbMatBenchmarkRunner
        return PerturbMatBenchmarkRunner
    elif name == "compute_brier_score":
        from .calibration import compute_brier_score
        return compute_brier_score
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
