"""Private admin pages. Only reachable over Tailscale (nginx blocks everyone else; require_admin is the backup)."""
import ipaddress
import os
import re
import threading
from datetime import datetime
from functools import wraps

import requests
from flask import Blueprint, abort, jsonify, render_template, request

from discogs_api import (
    delete_collection_instance,
    forget_release,
    get_album_glow,
    get_all_play_counts,
    get_collection,
    get_collection_folders,
    get_collection_value,
    get_current_record,
    get_led_brightness,
    get_led_settings,
    get_marketplace_stats,
    get_shelf_anchors,
    save_led_settings,
    set_album_glow,
    set_led_brightness,
    set_shelf_anchor,
)
from led_controller import LED_COUNT, get_ambient, set_ambient, show_spots
from shelf import artist_name, current_positions, glow_for_record, neighbors, positions_for, shelf_ids

admin = Blueprint("admin", __name__)

TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")


def client_ip():
    # Flask only listens on 127.0.0.1, so X-Real-IP can only come from nginx, which overwrites it
    return request.headers.get("X-Real-IP") or request.remote_addr


def is_admin_ip(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return False
    # Loopback = someone with a shell on the Pi talking to Flask directly
    return addr in TAILSCALE_NET or addr.is_loopback


def require_admin(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin_ip(client_ip()):
            abort(404)  # 404, not 403, so the page doesn't advertise that it exists
        return view(*args, **kwargs)
    return wrapper


@admin.app_context_processor
def inject_is_admin():
    # Lets public templates render admin-only bits server-side (never sent to non-Tailscale visitors)
    return {"is_admin": is_admin_ip(client_ip())}


SORT_KEYS = {
    "shelf": lambda r: r["shelf"],
    "artist": lambda r: r["artist"].lower(),
    "title": lambda r: r["title"].lower(),
    "year": lambda r: r["year"] or 0,
    "added": lambda r: r["added"],
    "plays": lambda r: r["plays"],
}


@admin.route("/admin")
@require_admin
def admin_page():
    username, token = os.getenv("DISCOGS_USERNAME"), os.getenv("DISCOGS_TOKEN")
    releases = get_collection(username, token)
    play_counts = get_all_play_counts()

    errors, folders, value = [], {}, None
    try:
        folders = get_collection_folders(username, token)
    except requests.RequestException as e:
        errors.append(f"Couldn't load folder names: {e}")
    try:
        value = get_collection_value(username, token)
    except requests.RequestException as e:
        errors.append(f"Couldn't load collection value: {e}")

    shelf_numbers = {release_id: i + 1 for i, release_id in enumerate(shelf_ids(releases))}
    positions = positions_for(releases)
    anchors = get_shelf_anchors()
    beside = neighbors(releases)

    records = []
    for item in releases:
        basic = item.get("basic_information", {})
        formats = basic.get("formats") or [{}]
        records.append({
            "id": basic.get("id"),
            "shelf": shelf_numbers.get(basic.get("id"), 0),
            "led": positions.get(basic.get("id"), 0),
            "pinned": basic.get("id") in anchors,
            "after": beside.get(basic.get("id"), (None, None))[0],
            "before": beside.get(basic.get("id"), (None, None))[1],
            "instance_id": item.get("instance_id"),
            "folder_id": item.get("folder_id"),
            "artist": artist_name(basic),
            "title": basic.get("title", ""),
            "year": basic.get("year") or None,
            "format": formats[0].get("name", ""),
            "folder": folders.get(item.get("folder_id"), item.get("folder_id", "")),
            "added": (item.get("date_added") or "")[:10],
            "plays": play_counts.get(basic.get("id"), 0),
        })

    search = request.args.get("search", "").strip()
    if search:
        q = search.lower()
        records = [r for r in records if q in r["artist"].lower() or q in r["title"].lower()]

    sort = request.args.get("sort", "shelf")
    if sort not in SORT_KEYS:
        sort = "shelf"
    desc = request.args.get("dir") == "desc"
    records.sort(key=SORT_KEYS[sort], reverse=desc)

    return render_template("admin.html", records=records, total=len(releases), value=value,
                           errors=errors, search=search, sort=sort, desc=desc,
                           led_count=LED_COUNT, brightness=get_led_brightness(), album_glow=get_album_glow(),
                           led_settings=get_led_settings())


@admin.route("/api/admin/price/<int:release_id>")
@require_admin
def price(release_id):
    try:
        return jsonify(get_marketplace_stats(release_id, os.getenv("DISCOGS_TOKEN")))
    except requests.RequestException as e:
        return jsonify({"error": f"Couldn't load price: {e}"}), 502


@admin.route("/api/admin/delete", methods=["POST"])
@require_admin
def delete_record():
    # JSON only: a cross-site <form> can't send it, and there's no CORS, so other sites can't trigger deletes
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 415
    data = request.get_json(silent=True) or {}
    try:
        release_id, instance_id, folder_id = (int(data[k]) for k in ("release_id", "instance_id", "folder_id"))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "release_id, instance_id and folder_id must be integers"}), 400

    try:
        delete_collection_instance(os.getenv("DISCOGS_USERNAME"), os.getenv("DISCOGS_TOKEN"),
                                   folder_id, release_id, instance_id)
    except requests.RequestException as e:
        return jsonify({"error": f"Discogs refused the delete: {e}"}), 502

    forget_release(release_id)
    print(f"{datetime.now().isoformat(timespec='seconds')} ADMIN DELETE release={release_id} "
          f"instance={instance_id} folder={folder_id} by {client_ip()}")
    return jsonify({"deleted": release_id})


def parse_led(value):
    """An LED number from JSON, or None if it isn't one on the strip."""
    if type(value) is not int or not 0 <= value < LED_COUNT:
        return None
    return value


@admin.route("/api/admin/leds", methods=["POST"])
@require_admin
def set_lights():
    """Lights on in a color ({"color": "#rrggbb"}), off ({"off": true}), {"brightness": 0-100}, and/or {"album_glow": bool}."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 415
    data = request.get_json(silent=True) or {}

    colors = get_ambient()
    if "color" in data:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(data["color"])):
            return jsonify({"error": "color must look like #rrggbb"}), 400
        colors = [tuple(bytes.fromhex(data["color"][1:]))]
    if "brightness" in data:
        brightness = data["brightness"]
        if type(brightness) is not int or not 0 <= brightness <= 100:
            return jsonify({"error": "brightness must be a whole number from 0 to 100"}), 400
        set_led_brightness(brightness)
    if "album_glow" in data:
        if type(data["album_glow"]) is not bool:
            return jsonify({"error": "album_glow must be true or false"}), 400
        set_album_glow(data["album_glow"])
        if not data["album_glow"]:
            colors = None
    if data.get("off"):
        colors = None

    if not set_ambient(colors):
        return jsonify({"error": "The shelf lights aren't connected"}), 503
    playing = get_current_record()
    if data.get("album_glow") and playing:  # Switched on mid-record, so start glowing now
        threading.Thread(target=glow_for_record, args=(playing,), daemon=True).start()
    return jsonify({"on": colors is not None, "brightness": get_led_brightness(), "album_glow": get_album_glow()})


@admin.route("/api/admin/leds/settings", methods=["POST"])
@require_admin
def save_light_settings():
    """{"first_led", "last_led", "spot_seconds", "find_color", "wave_speed"}: strip range, Find light and album wave."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 415
    data = request.get_json(silent=True) or {}
    first_led, last_led = parse_led(data.get("first_led")), parse_led(data.get("last_led"))
    if first_led is None or last_led is None or first_led >= last_led:
        return jsonify({"error": f"Start and end must be LEDs from 0 to {LED_COUNT - 1}, with start before end"}), 400
    spot_seconds = data.get("spot_seconds")
    if type(spot_seconds) is not int or not 5 <= spot_seconds <= 600:
        return jsonify({"error": "Light time must be a whole number of seconds from 5 to 600"}), 400
    find_color = str(data.get("find_color"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", find_color):
        return jsonify({"error": "find_color must look like #rrggbb"}), 400
    wave_speed = data.get("wave_speed")
    if type(wave_speed) is not int or not 1 <= wave_speed <= 10:
        return jsonify({"error": "Wave speed must be a whole number from 1 to 10"}), 400

    save_led_settings(first_led=first_led, last_led=last_led, spot_seconds=spot_seconds, find_color=find_color.lower(),
                      wave_speed=wave_speed)
    if len(get_ambient() or ()) > 1:  # A wave is showing, so switch it to the new speed now
        set_ambient(get_ambient())
    try:
        positions = current_positions()
    except requests.RequestException as e:
        return jsonify({"error": f"Saved, but couldn't refresh the record spots: {e}"}), 502
    return jsonify({"positions": positions})


@admin.route("/api/admin/leds/show", methods=["POST"])
@require_admin
def show_led():
    """Light any LED, so a spot can be nudged into place before saving it."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 415
    led = parse_led((request.get_json(silent=True) or {}).get("led"))
    if led is None:
        return jsonify({"error": f"led must be a whole number from 0 to {LED_COUNT - 1}"}), 400
    if not show_spots(find=led):
        return jsonify({"error": "The shelf lights aren't connected"}), 503
    return jsonify({"led": led})


@admin.route("/api/admin/shelf/spot", methods=["POST"])
@require_admin
def save_spot():
    """Pin a record to an LED. Estimated records around it shift, so send every position back."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 415
    data = request.get_json(silent=True) or {}
    release_id, led = data.get("release_id"), parse_led(data.get("led"))
    if type(release_id) is not int or led is None:
        return jsonify({"error": f"release_id must be an integer and led from 0 to {LED_COUNT - 1}"}), 400

    set_shelf_anchor(release_id, led)
    try:
        positions = current_positions()
    except requests.RequestException as e:
        return jsonify({"error": f"Saved, but couldn't refresh the other spots: {e}"}), 502
    return jsonify({"positions": positions})


if __name__ == "__main__":
    # Self-check: python admin.py
    for ip in ("100.64.0.1", "100.127.255.254", "127.0.0.1", "::1"):
        assert is_admin_ip(ip), ip
    for ip in ("192.168.1.20", "100.128.0.1", "8.8.8.8", "", None, "garbage"):
        assert not is_admin_ip(ip), ip
    print("admin self-check OK")
