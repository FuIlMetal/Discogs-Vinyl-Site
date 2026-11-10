"""Where each record sits on the shelf: A-Z by artist, mapped to an LED."""
import os
import re
import time
import unicodedata

import requests

from discogs_api import (delete_shelf_anchor, get_collection, get_current_record, get_led_settings, get_shelf_anchors, get_shelf_steps,
                         save_led_settings, save_shelf_steps, set_shelf_anchor)
from led_controller import LED_COUNT, cover_wave, set_ambient

_releases = []
_fetched_at = 0


def artist_name(basic):
    # Discogs adds " (2)" to tell apart artists who share a name
    return re.sub(r"\s\(\d+\)", "", ", ".join(a["name"] for a in basic.get("artists", [])))


def _plain(text):
    """Lowercase with accents removed, so Björk files next to Bjork."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def artist_sort_name(artist):
    """How an artist files: plain lowercase without a leading "The", so The Who files under W.
    Must match artistSortName on the home page."""
    return re.sub(r"^the\s+(?=\S)", "", _plain(artist).strip())


def shelf_sort_key(item):
    basic = item.get("basic_information", {})
    # Same artist order as the home page. Miles Davis still files under M: only "The" is dropped.
    return artist_sort_name(artist_name(basic)), _plain(basic.get("title", "")), basic.get("id") or 0


def shelf_ids(releases):
    """Release ids in the order they sit on the shelf, left to right."""
    ids = (item.get("basic_information", {}).get("id") for item in sorted(releases, key=shelf_sort_key))
    return list(dict.fromkeys(i for i in ids if i))  # shortcut: two copies of a release share one spot


def _spots(ids, steps, first_led, last_led):
    """Exact (unrounded) LED of each record. Steps are spread to fill first_led..last_led, so when the
    start or end moves, or a record is added or removed, the whole shelf shifts a little to fit."""
    known = [steps[r] for r in ids[1:] if r in steps]
    default = sum(known) / len(known) if known else 1  # A new record is guessed to be as wide as the average
    gaps = [steps.get(r, default) for r in ids[1:]]
    scale = (last_led - first_led) / (sum(gaps) or 1)
    spots = [first_led]
    for gap in gaps:
        spots.append(spots[-1] + gap * scale)
    return spots


def shelf_positions(ids, steps, first_led, last_led):
    """{release_id: LED}, left to right inside first_led..last_led."""
    return {r: round(led) for r, led in zip(ids, _spots(ids, steps, first_led, last_led))}


def pin_spot(ids, pinned, steps, first_led, last_led, release_id, led):
    """Correct one record's estimate to led. Records back to the saved spot on each side (or the shelf ends)
    stretch or squeeze to fit, and saved spots beyond them stay put. Pinning the first or last record moves
    the start or end. Returns (steps, first_led, last_led). Raises ValueError if led is past a saved neighbor."""
    k = ids.index(release_id)
    spots = _spots(ids, steps, first_led, last_led)
    marks = [i for i, r in enumerate(ids) if r in pinned and i != k]
    a = max([i for i in marks if i < k], default=0)
    b = min([i for i in marks if i > k], default=len(ids) - 1)
    low = spots[a] if a < k else 0
    high = spots[b] if b > k else LED_COUNT - 1
    if not low <= led <= high:
        raise ValueError(f"That's past a saved record next to it: pick an LED from {round(low)} to {round(high)}")

    gaps = [spots[i] - spots[i - 1] for i in range(1, len(ids))]  # gaps[i - 1] is the step onto record i
    for lo, hi, start, end in ((a, k, spots[a], led), (k, b, led, spots[b])):
        old = spots[hi] - spots[lo]
        for i in range(lo + 1, hi + 1):
            gaps[i - 1] = gaps[i - 1] * (end - start) / old if old else (end - start) / (hi - lo)
    if k == 0:
        first_led = led
    if k == len(ids) - 1:
        last_led = led
    return dict(zip(ids[1:], gaps)), first_led, last_led


def unpin_spot(ids, pinned, steps, first_led, last_led, release_id):
    """Undo a saved spot: records between the saved spots on each side go back to even spacing.
    Returns the new steps."""
    k = ids.index(release_id)
    spots = _spots(ids, steps, first_led, last_led)
    marks = [i for i, r in enumerate(ids) if r in pinned and i != k]
    a = max([i for i in marks if i < k], default=0)
    b = min([i for i in marks if i > k], default=len(ids) - 1)
    gaps = [spots[i] - spots[i - 1] for i in range(1, len(ids))]
    for i in range(a + 1, b + 1):
        gaps[i - 1] = (spots[b] - spots[a]) / (b - a)
    return dict(zip(ids[1:], gaps))


def _range(settings):
    return settings["first_led"], LED_COUNT - 1 if settings["last_led"] is None else settings["last_led"]


def positions_for(releases):
    ids, steps, anchors = shelf_ids(releases), get_shelf_steps(), get_shelf_anchors()
    first_led, last_led = _range(get_led_settings())
    if anchors and not steps and len(ids) > 1:
        # Spots saved before steps existed: replay them left to right so they keep their LEDs
        for r in ids:
            if r in anchors:
                try:
                    steps, first_led, last_led = pin_spot(ids, anchors, steps, first_led, last_led, r, anchors[r])
                except ValueError:
                    pass  # Saved out of order; skip it
        save_shelf_steps(steps)
        save_led_settings(first_led=first_led, last_led=last_led)
    return shelf_positions(ids, steps, first_led, last_led)


def save_spot(release_id, led):
    """Save that a record sits at led (from the admin page). Returns every record's new LED.
    Raises ValueError if it isn't on the shelf or led doesn't fit, and requests.RequestException."""
    releases = _cached_releases(300)
    ids = shelf_ids(releases)
    if release_id not in ids:
        releases = _cached_releases(0)  # Maybe it was just added
        ids = shelf_ids(releases)
    if release_id not in ids:
        raise ValueError("That record isn't in the collection")
    positions_for(releases)  # Runs the one-time move from old saved spots first
    first_led, last_led = _range(get_led_settings())
    steps, first_led, last_led = pin_spot(ids, get_shelf_anchors(), get_shelf_steps(), first_led, last_led,
                                          release_id, led)
    if first_led >= last_led:
        raise ValueError("The first record has to be left of the last one")
    save_shelf_steps(steps)
    save_led_settings(first_led=first_led, last_led=last_led)
    set_shelf_anchor(release_id, led)
    return positions_for(releases)


def remove_spot(release_id):
    """Undo a record's saved spot (from the admin page). Returns every record's new LED.
    Can raise requests.RequestException."""
    releases = _cached_releases(300)
    ids = shelf_ids(releases)
    if release_id in ids and len(ids) > 1:
        positions_for(releases)  # Runs the one-time move from old saved spots first
        steps = unpin_spot(ids, get_shelf_anchors(), get_shelf_steps(), *_range(get_led_settings()), release_id)
        save_shelf_steps(steps)
    delete_shelf_anchor(release_id)
    return positions_for(releases)


def shelf_count(max_age=0):
    return len(shelf_ids(_cached_releases(max_age)))


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


def neighbors(releases):
    """{release_id: (label of the record on its left, label on its right)}, with None at the shelf ends."""
    ids = shelf_ids(releases)
    basics = {item.get("basic_information", {}).get("id"): item.get("basic_information", {}) for item in releases}
    labels = [f"{artist_name(basics[i])} – {basics[i].get('title', '')}" for i in ids]
    return {release_id: (labels[i - 1] if i > 0 else None, labels[i + 1] if i + 1 < len(ids) else None)
            for i, release_id in enumerate(ids)}


def placement(release_id, max_age=0):
    """Where a record goes on the shelf: its LED, its # from the left, and the records either side.
    Fetches the collection fresh by default, so a record added a moment ago is placed. None if it isn't there."""
    releases = _cached_releases(max_age)
    ids = shelf_ids(releases)
    if release_id not in ids:
        return None
    after, before = neighbors(releases)[release_id]
    return {"led": positions_for(releases)[release_id], "number": ids.index(release_id) + 1,
            "after": after, "before": before}


def current_positions():
    return positions_for(_cached_releases(300))


def thumb_for(release_id):
    for item in _cached_releases(300):
        basic = item.get("basic_information", {})
        if basic.get("id") == release_id:
            return basic.get("thumb", "")
    return ""


def glow_for_record(release_id):
    """Glow the shelf in a slow wave of the record's cover colors. Run it in the background because the image fetch is slow."""
    try:
        thumb = thumb_for(release_id)
    except requests.RequestException as e:
        print(f"LED: couldn't look up cover for {release_id}: {e}")
        thumb = ""
    colors = cover_wave(thumb)
    if get_current_record() == release_id:  # It may have been cleared during the fetch
        set_ambient(colors)


if __name__ == "__main__":
    # Self-check: python shelf.py
    def item(release_id, artist, title):
        return {"basic_information": {"id": release_id, "title": title, "artists": [{"name": artist}]}}

    records = [item(1, "Zappa", "A"), item(2, "The Beatles", "Help"), item(3, "björk", "Post"),
               item(4, "Bjork (2)", "Debut"), item(5, "The Beatles", "Abbey Road"), item(5, "The Beatles", "Abbey Road"),
               item(6, "The Who", "Tommy"), item(7, "The Alarm", "Strength"), item(8, "Theo Parrish", "X"),
               item(9, "The The", "Soul Mining")]
    # "The" is dropped (The Alarm under A, The Who under W) but not from Theo, and The The still files under T
    assert shelf_ids(records) == [7, 5, 2, 4, 3, 9, 8, 6, 1], shelf_ids(records)
    assert neighbors(records)[5] == ("The Alarm – Strength", "The Beatles – Help")
    assert neighbors(records)[7][0] is None and neighbors(records)[1][1] is None

    assert shelf_positions([], {}, 0, 101) == {}
    assert shelf_positions([7], {}, 0, 101) == {7: 0}
    assert shelf_positions([1, 2, 3], {}, 0, 100) == {1: 0, 2: 50, 3: 100}
    assert shelf_positions([1, 2, 3], {}, 4, 96) == {1: 4, 2: 50, 3: 96}

    # Pinning c stretches a..c and squeezes c..e; the ends stay put
    ids = list("abcde")
    steps, first, last = pin_spot(ids, {}, {}, 0, 100, "c", 30)
    assert (first, last) == (0, 100) and shelf_positions(ids, steps, first, last) ==         {"a": 0, "b": 15, "c": 30, "d": 65, "e": 100}
    # Pinning d next only moves records between c (saved) and the end
    steps, first, last = pin_spot(ids, {"c": 30}, steps, first, last, "d", 40)
    assert shelf_positions(ids, steps, first, last) == {"a": 0, "b": 15, "c": 30, "d": 40, "e": 100}
    # Can't pin past a saved neighbor
    try:
        pin_spot(ids, {"c": 30}, steps, first, last, "d", 20)
        raise AssertionError("pinned past a saved neighbor")
    except ValueError:
        pass
    # Pinning the last record moves the end, and everything else keeps its spot
    steps2, first2, last2 = pin_spot(ids, {"c": 30, "d": 40}, steps, first, last, "e", 90)
    assert last2 == 90 and shelf_positions(ids, steps2, first2, last2) == {"a": 0, "b": 15, "c": 30, "d": 40, "e": 90}

    # Removing d's save puts c..e back to even spacing; a..c keeps c's correction
    steps3 = unpin_spot(ids, {"c": 30, "d": 40}, steps, first, last, "d")
    assert shelf_positions(ids, steps3, first, last) == {"a": 0, "b": 15, "c": 30, "d": 65, "e": 100}

    # A record added between c and d gets the average width; with the end moved out by about that much,
    # everything left of it stays put and everything right of it moves over by one record
    wide = list("abcXde")
    spots = shelf_positions(wide, steps, first, last + 25)
    assert spots["a"] == 0 and spots["c"] == 30 and spots["X"] == 55 and spots["d"] == 65, spots
    # Removing a record without moving the end spreads everything a little to fill the gap
    spots = shelf_positions(list("abde"), steps, first, last)
    assert spots == {"a": 0, "b": 18, "d": 29, "e": 100}, spots
    print("shelf self-check OK")
