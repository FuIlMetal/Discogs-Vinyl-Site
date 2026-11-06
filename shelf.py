"""Where each record sits on the shelf: A-Z by artist, mapped to an LED."""
import os
import re
import time
import unicodedata

from discogs_api import get_collection, get_shelf_anchors
from led_controller import LED_COUNT

_releases = []
_fetched_at = 0


def artist_name(basic):
    # Discogs adds " (2)" to tell apart artists who share a name
    return re.sub(r"\s\(\d+\)", "", ", ".join(a["name"] for a in basic.get("artists", [])))


def _plain(text):
    """Lowercase with accents removed, so Björk files next to Bjork."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def shelf_sort_key(item):
    basic = item.get("basic_information", {})
    # Same artist order as the home page, so The Beatles file under T and Miles Davis under M
    return _plain(artist_name(basic)), _plain(basic.get("title", "")), basic.get("id") or 0


def shelf_ids(releases):
    """Release ids in the order they sit on the shelf, left to right."""
    ids = (item.get("basic_information", {}).get("id") for item in sorted(releases, key=shelf_sort_key))
    return list(dict.fromkeys(i for i in ids if i))  # shortcut: two copies of a release share one spot


def shelf_positions(ids, anchors, led_count):
    """LED for each id: saved anchors stay exact, and the records between them are spaced evenly."""
    if not ids:
        return {}
    points = [(i, anchors[r]) for i, r in enumerate(ids) if r in anchors]
    if not points or points[0][0] != 0:
        points.insert(0, (0, 0))
    if points[-1][0] != len(ids) - 1:
        points.append((len(ids) - 1, led_count - 1))

    positions = {ids[points[0][0]]: points[0][1]}
    for (i1, led1), (i2, led2) in zip(points, points[1:]):
        for i in range(i1 + 1, i2 + 1):
            positions[ids[i]] = round(led1 + (led2 - led1) * (i - i1) / (i2 - i1))
    return positions


def positions_for(releases):
    return shelf_positions(shelf_ids(releases), get_shelf_anchors(), LED_COUNT)


def _cached_releases(max_age):
    # Anyone can press Find, and each collection fetch is a Discogs call, so don't fetch on every press
    global _releases, _fetched_at
    if time.time() - _fetched_at > max_age:
        _releases = get_collection(os.getenv("DISCOGS_USERNAME"), os.getenv("DISCOGS_TOKEN"))
        _fetched_at = time.time()
    return _releases


def spot_for(release_id):
    """The LED for a record, or None if it isn't in the collection. Can raise requests.RequestException."""
    led = positions_for(_cached_releases(300)).get(release_id)
    if led is None:  # Maybe it was just added
        led = positions_for(_cached_releases(30)).get(release_id)
    return led


def current_positions():
    return positions_for(_cached_releases(300))


def thumb_for(release_id):
    for item in _cached_releases(300):
        basic = item.get("basic_information", {})
        if basic.get("id") == release_id:
            return basic.get("thumb", "")
    return ""


if __name__ == "__main__":
    # Self-check: python shelf.py
    def item(release_id, artist, title):
        return {"basic_information": {"id": release_id, "title": title, "artists": [{"name": artist}]}}

    records = [item(1, "Zappa", "A"), item(2, "The Beatles", "Help"), item(3, "björk", "Post"),
               item(4, "Bjork (2)", "Debut"), item(5, "The Beatles", "Abbey Road"), item(5, "The Beatles", "Abbey Road")]
    assert shelf_ids(records) == [4, 3, 5, 2, 1], shelf_ids(records)

    assert shelf_positions([], {}, 102) == {}
    assert shelf_positions([7], {}, 102) == {7: 0}
    assert shelf_positions([7], {7: 40}, 102) == {7: 40}
    assert shelf_positions([1, 2, 3], {}, 101) == {1: 0, 2: 50, 3: 100}
    # Anchors stay exact, and the gaps on each side of them are evenly filled
    spots = shelf_positions(list("abcde"), {"b": 20, "d": 40}, 101)
    assert spots == {"a": 0, "b": 20, "c": 30, "d": 40, "e": 100}, spots
    spots = shelf_positions(list("abc"), {"a": 10, "c": 90}, 101)
    assert spots == {"a": 10, "b": 50, "c": 90}, spots
    print("shelf self-check OK")
