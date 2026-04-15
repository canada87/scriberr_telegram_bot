from flask import Flask, jsonify, render_template, request

import db

app = Flask(__name__)


@app.route("/")
def index():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    offset = (page - 1) * per_page
    logs = db.get_logs(limit=per_page, offset=offset)
    stats = db.get_stats()
    total_pages = max(1, (stats["total"] + per_page - 1) // per_page)
    return render_template(
        "index.html",
        logs=logs,
        stats=stats,
        page=page,
        total_pages=total_pages,
        service=db.get_setting("service", "scriberr"),
    )


@app.route("/api/service", methods=["POST"])
def api_set_service():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("service") or "").lower()
    if name not in db.VALID_SERVICES:
        return jsonify({"error": f"Servizi disponibili: {', '.join(db.VALID_SERVICES)}"}), 400
    db.set_setting("service", name)
    return jsonify({"service": name})


@app.route("/api/logs")
def api_logs():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    offset = (page - 1) * per_page
    return jsonify(db.get_logs(limit=per_page, offset=offset))


@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_stats())
