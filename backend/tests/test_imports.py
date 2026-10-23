"""Import d'une partie de traversalgame.com : conversion (pure) et API (sans réseau)."""

import copy
import json
import re
from pathlib import Path

import pytest
from conftest import KEY, new_player

from app.services import imports
from app.services.games import GameError

# Partie réelle (`/api/games/<uuid>/full-state`), pseudos et classements remplacés.
DATA = json.loads((Path(__file__).parent / "data" / "traversalgame_full_state.json").read_text())
REF = DATA["game_id"]


def test_parse_ref_accepts_game_and_signup_links():
    assert imports.parse_ref(f"https://www.traversalgame.com/game/{REF}") == REF
    assert imports.parse_ref(f"https://www.traversalgame.com/signup?redirect=/game/{REF}") == REF
    assert imports.parse_ref(f"  {REF.upper()} ") == REF
    for bad in ("https://www.traversalgame.com/games", f"https://example.com/game/{REF}", "n'importe quoi"):
        with pytest.raises(GameError):
            imports.parse_ref(bad)


def test_convert_replays_every_move_with_our_engine():
    game = imports.convert(DATA, REF, "me")
    assert game.mode == "import" and game.status == "finished" and not game.rated
    assert len(game.moves) == len(DATA["move_history"]) == 17
    # Même case d'arrivée et même prise que là-bas (leur rangée 9 = notre rangée 1).
    for rec, theirs in zip(game.moves, DATA["move_history"]):
        dest = re.compile(r"[a-j]\d+")
        assert dest.findall(rec.notation)[-1] == dest.findall(theirs["notation"])[-1]
        assert (rec.kind == "attack") == theirs["isCapture"]
    assert game.state.over and game.state.winner == 1 and game.state.reason == "resign"
    assert game.imported["names"] == ["Alice", "Bob"] and game.imported["ratings"] == [1600, 1500]


def test_convert_refuses_unfinished_and_illegal_games():
    live = {**DATA, "status": "active", "game_over": False}
    with pytest.raises(GameError) as exc:
        imports.convert(live, REF, "me")
    assert exc.value.status == 409
    bad = copy.deepcopy(DATA)
    bad["move_history"][0]["toRow"] = 2  # l'Explorateur ne va pas si loin
    with pytest.raises(GameError) as exc:
        imports.convert(bad, REF, "me")
    assert exc.value.status == 422


async def test_import_api_creates_the_game_once(client, monkeypatch):
    calls = []

    async def fake_fetch(ref):
        calls.append(ref)
        return DATA

    monkeypatch.setattr(imports, "fetch", fake_fetch)
    me = await new_player(client)
    link = f"https://www.traversalgame.com/signup?redirect=/game/{REF}"
    r = await client.post("/api/imports", json={"url": link}, headers=me)
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    view = (await client.get(f"/api/games/{gid}", headers=me)).json()
    assert view["mode"] == "import" and view["status"] == "finished"
    assert [p["name"] for p in view["players"]] == ["Alice", "Bob"]
    assert view["source"]["url"].endswith(REF) and view["result"] == {"winner": 1, "reason": "resign"}
    # Même lien, autre joueur : la même partie, sans nouvel appel au site.
    other = await new_player(client)
    r = await client.post("/api/imports", json={"url": link}, headers=other)
    assert r.json()["id"] == gid and calls == [REF]
    # Le bilan s'y applique comme à toute partie terminée.
    r = await client.post(f"/api/games/{gid}/analysis", json={}, headers=KEY)
    assert r.status_code == 200 and r.json()["status"] in ("queued", "running", "done")


async def test_import_without_account_is_closed(client, monkeypatch):
    monkeypatch.delenv("TRAVERSAL_LOGIN", raising=False)
    me = await new_player(client)
    r = await client.post("/api/imports", json={"url": REF}, headers=me)
    assert r.status_code == 503
