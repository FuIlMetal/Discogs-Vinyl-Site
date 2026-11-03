"""Private admin pages. Only reachable over Tailscale (nginx blocks everyone else; require_admin is the backup)."""
import ipaddress
import os
from datetime import datetime
from functools import wraps

import requests
from flask import Blueprint, abort, jsonify, render_template, request

from discogs_api import (
    delete_collection_instance,
    forget_release,
    get_all_play_counts,
    get_collection,
    get_collection_folders,
    get_collection_value,
    get_marketplace_stats,
)

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
            "instance_id": item.get("instance_id"),
            "folder_id": item.get("folder_id"),
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


if __name__ == "__main__":
    # Self-check: python admin.py
    for ip in ("100.64.0.1", "100.127.255.254", "127.0.0.1", "::1"):
        assert is_admin_ip(ip), ip
    for ip in ("192.168.1.20", "100.128.0.1", "8.8.8.8", "", None, "garbage"):
        assert not is_admin_ip(ip), ip
    print("admin self-check OK")
