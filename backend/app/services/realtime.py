"""Temps réel : prévient les flux SSE de CETTE instance qu'une partie a changé.

Les évènements viennent tous de Postgres (`LISTEN traversal`, voir `store.py`), y compris
ceux émis par cette instance : un seul chemin, quelle que soit l'instance qui a joué le
coup. On ne publie qu'un signal « a changé » (avec la version) : chaque abonné recalcule
SA vue (les coups légaux dépendent de qui regarde).
"""

import asyncio
from collections import defaultdict


class Hub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, key: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=16)
        self._subs[key].add(q)
        return q

    def unsubscribe(self, key: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(key)
        if subs:
            subs.discard(q)
            if not subs:
                del self._subs[key]

    def publish(self, key: str, event=None) -> None:
        for q in list(self._subs.get(key, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # l'abonné est en retard : il relira l'état complet de toute façon

    def watchers(self, key: str) -> int:
        return len(self._subs.get(key, ()))

    def on_event(self, ev: dict) -> None:
        """Notification Postgres -> abonnés locaux."""
        kind = ev.get("k")
        if kind == "game":
            self.publish(ev["id"], ev.get("v"))
        elif kind == "match":
            self.publish(f"match:{ev['id']}", ev.get("v"))
        elif kind == "watch":
            self.publish(ev["id"], "watch")  # le nombre de spectateurs a changé
        elif kind == "analysis":
            self.publish(f"analysis:{ev['id']}")
        elif kind == "reconnect":
            self.wake_all()

    def wake_all(self) -> None:
        """Après une coupure de l'écoute : chacun relit son état (évènements manqués)."""
        for key in list(self._subs):
            self.publish(key)


hub = Hub()
