from app.core.config import Settings


def test_standard_feedback_runtime_settings_use_configured_gates() -> None:
    settings = Settings(
        feedback_min_segments=3,
        feedback_min_window_chars=30,
        feedback_trigger_interval_seconds=12,
        feedback_cooldown_seconds=60,
        feedback_score_threshold=0.7,
    )

    runtime = settings.feedback_runtime_settings()

    assert runtime.min_segments == 3
    assert runtime.min_window_chars == 30
    assert runtime.trigger_interval_seconds == 12
    assert runtime.cooldown_seconds == 60
    assert runtime.score_threshold == 0.7
    assert runtime.allow_semantic_fallback is False


def test_demo_feedback_runtime_settings_relax_only_generation_gates() -> None:
    runtime = Settings(feedback_demo_mode=True).feedback_runtime_settings()

    assert runtime.min_segments == 1
    assert runtime.min_window_chars == 1
    assert runtime.trigger_interval_seconds == 0
    assert runtime.cooldown_seconds == 10
    assert runtime.score_threshold == 0.45
    assert runtime.allow_semantic_fallback is True
