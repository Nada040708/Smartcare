from src.domain.technical_event import TechnicalEvent


class EventRepository:
    """In-memory counterpart retained for offline demonstrations."""
    def __init__(self):
        self.events: list[TechnicalEvent] = []

    def save(self, event):
        for index, existing in enumerate(self.events):
            if existing.event_id == event.event_id:
                self.events[index] = event
                return
        self.events.append(event)

    def getHistory(self):
        return self.events.copy()
