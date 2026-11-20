"""Pure deterministic risk evaluation over structured event evidence."""

from shared.contracts import (
    AlertDecision,
    AlertLevel,
    DecisionReasonCode,
    EventContext,
    PolicyConfig,
)


def evaluate_risk(
    event_context: EventContext,
    policy_config: PolicyConfig,
) -> AlertDecision:
    """Return the same decision for the same context and policy configuration."""

    if not event_context.detections:
        return AlertDecision(
            should_alert=False,
            alert_level=AlertLevel.NONE,
            reason_codes=[DecisionReasonCode.NO_DETECTIONS],
        )

    qualifying = [
        detection
        for detection in event_context.detections
        if detection.max_confidence >= policy_config.minimum_confidence
        and detection.track_frames >= policy_config.minimum_track_frames
    ]
    if qualifying:
        if any(detection.road_overlap for detection in qualifying):
            return AlertDecision(
                should_alert=True,
                alert_level=AlertLevel.WARNING,
                reason_codes=[DecisionReasonCode.PERSISTENT_ANIMAL_ON_ROAD],
            )
        return AlertDecision(
            should_alert=True,
            alert_level=AlertLevel.CAUTION,
            reason_codes=[DecisionReasonCode.PERSISTENT_ANIMAL_NEAR_ROAD],
        )

    reason_codes = []
    if any(
        detection.max_confidence < policy_config.minimum_confidence
        for detection in event_context.detections
    ):
        reason_codes.append(DecisionReasonCode.BELOW_CONFIDENCE_THRESHOLD)
    if any(
        detection.track_frames < policy_config.minimum_track_frames
        for detection in event_context.detections
    ):
        reason_codes.append(DecisionReasonCode.INSUFFICIENT_TRACK_PERSISTENCE)
    return AlertDecision(
        should_alert=False,
        alert_level=AlertLevel.NONE,
        reason_codes=reason_codes,
    )
