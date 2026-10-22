"""Rangs (paliers, divisions, PL, placement, Légende)."""

import pytest
from conftest import KEY

from app.services.ranks import PLACEMENT_GAMES, ladder, rank_from


@pytest.mark.parametrize(
    ("rating", "label", "lp"),
    [
        (500, "Ardoise IV", 0),
        (800, "Ardoise IV", 0),
        (999, "Ardoise I", 98),
        (1000, "Bronze IV", 0),
        (1500, "Or II", 0),
        (1525, "Or II", 50),
        (1599.9, "Or I", 99),
        (1650, "Jade III", 0),
        (2199, "Diamant I", 98),
        (2200, "Maître", 0),
        (2350, "Maître", 150),
    ],
)
def test_rank_mapping(rating, label, lp):
    r = rank_from(rating, PLACEMENT_GAMES)
    assert r["label"] == label and r["lp"] == lp


def test_placement_then_reveal():
    assert rank_from(1700, PLACEMENT_GAMES - 1)["placement"] == {"played": 4, "total": 5}
    assert rank_from(1700, PLACEMENT_GAMES - 1)["tier"] is None
    assert rank_from(1700, PLACEMENT_GAMES)["tier"] == "jade"


def test_next_step_and_legend():
    assert rank_from(1590, 10)["next"] == {"label": "Jade IV", "rating": 1600, "tier": "jade", "division": 4}
    assert rank_from(1510, 10)["next"] == {"label": "Or I", "rating": 1550, "tier": "gold", "division": 1}
    assert rank_from(2190, 10)["next"]["tier"] == "master" and rank_from(2190, 10)["next"]["division"] is None
    assert rank_from(2190, 10)["next"]["label"] == "Maître"
    assert rank_from(2300, 10, legend=True)["tier"] == "legend"
    assert rank_from(2100, 10, legend=True)["tier"] == "diamond"  # Légende = Maître d'abord
    assert [t["tier"] for t in ladder()][-2:] == ["master", "legend"]


async def test_rank_change_after_rated_games(client):
    a = {**KEY, "x-session": (await client.post("/api/players", json={"name": "Grimpe"}, headers=KEY)).json()["token"]}
    b = {**KEY, "x-session": (await client.post("/api/players", json={"name": "Chute"}, headers=KEY)).json()["token"]}
    last = None
    for _ in range(PLACEMENT_GAMES):
        g = (await client.post("/api/games", json={"mode": "online", "type": "classic", "side": 1},
                               headers=a)).json()
        await client.post(f"/api/games/{g['id']}/join", headers=b)
        last = (await client.post(f"/api/games/{g['id']}/resign", headers=b)).json()
    before, after = last["rankChange"][0]["before"], last["rankChange"][0]["after"]
    assert before["placement"] == {"played": 4, "total": 5}
    assert after["placement"] is None and after["tier"]  # rang révélé à la 5e partie
    me = (await client.get("/api/me", headers=a)).json()
    assert me["ratings"]["classic"]["rank"]["label"] == after["label"]
    assert last["players"][0]["rank"]["label"] == after["label"]
    lb = (await client.get("/api/leaderboard?timeClass=classic", headers=KEY)).json()
    assert lb[0]["tier"]["label"] == after["label"]
    assert (await client.get("/api/ranks", headers=KEY)).json()["placementGames"] == PLACEMENT_GAMES
