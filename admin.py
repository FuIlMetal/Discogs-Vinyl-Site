"""Private admin pages. Only reachable over Tailscale (nginx blocks everyone else; require_admin is the backup)."""
import ipaddress
import os
from functools import wraps

import requests
from flask import Blueprint, abort, render_template, request

from discogs_api import get_all_play_counts, get_collection, get_collection_folders, get_collection_value

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

    records = []
    for item in releases:
        basic = item.get("basic_information", {})
        formats = basic.get("formats") or [{}]
        records.append({
            "id": basic.get("id"),
            "artist": ", ".join(a["name"] for a in basic.get("artists", [])),
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

    sort = request.args.get("sort", "artist")
    if sort not in SORT_KEYS:
        sort = "artist"
    desc = request.args.get("dir") == "desc"
    records.sort(key=SORT_KEYS[sort], reverse=desc)

    return render_template("admin.html", records=records, total=len(releases), value=value,
                           errors=errors, search=search, sort=sort, desc=desc)


if __name__ == "__main__":
    # Self-check: python admin.py
    for ip in ("100.64.0.1", "100.127.255.254", "127.0.0.1", "::1"):
        assert is_admin_ip(ip), ip
    for ip in ("192.168.1.20", "100.128.0.1", "8.8.8.8", "", None, "garbage"):
        assert not is_admin_ip(ip), ip
    print("admin self-check OK")
