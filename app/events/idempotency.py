from uuid import UUID


class InMemoryEventTracker:
    def __init__(self) -> None:
        self._completed: set[UUID] = set()
        self._retry_counts: dict[UUID, int] = {}

    def is_completed(self, event_id: UUID) -> bool:
        return event_id in self._completed

    def mark_completed(self, event_id: UUID) -> None:
        self._completed.add(event_id)
        self._retry_counts.pop(event_id, None)

    def increment_retry(self, event_id: UUID) -> int:
        count = self._retry_counts.get(event_id, 0) + 1
        self._retry_counts[event_id] = count
        return count
