try:
    from eval_qc_env.taskset import EvalQCTaskset
except ModuleNotFoundError as e:
    if e.name != "verifiers":
        raise
    EvalQCTaskset = None

__all__ = ["EvalQCTaskset"]
