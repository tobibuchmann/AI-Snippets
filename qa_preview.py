import io
import json
import os
import secrets

from flask import abort, jsonify, request, send_file


def install_preview(legacy):
    token = os.getenv("QA_PREVIEW_TOKEN", "").strip()
    if token:
        @legacy.app.get("/qa/preview/<order_id>")
        def qa_preview(order_id):
            supplied = request.args.get("token", "")
            if not supplied or not secrets.compare_digest(supplied, token):
                abort(404)
            order = legacy.get_order(order_id)
            if not order or order.get("status") != "delivered" or not order.get("generated_text"):
                abort(404)
            payload = json.loads(order["payload"])
            pdf_bytes = legacy.quest_pdf_bytes(payload, order["generated_text"])
            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=False,
                download_name=f"GeburtstagsQuest-{order_id}.pdf",
            )

    content_token = os.getenv("QA_CONTENT_TOKEN", "").strip()
    allowed_order = os.getenv("QA_CONTENT_ORDER", "").strip()
    if content_token and allowed_order:
        @legacy.app.get("/qa/content/<order_id>")
        def qa_content(order_id):
            supplied = request.args.get("token", "")
            if order_id != allowed_order or not supplied or not secrets.compare_digest(supplied, content_token):
                abort(404)
            order = legacy.get_order(order_id)
            if not order or not order.get("generated_text"):
                abort(404)
            payload = json.loads(order["payload"])
            quest = json.loads(order["generated_text"])
            return jsonify({
                "order_id": order_id,
                "child_name": payload.get("child_name"),
                "age": payload.get("age"),
                "theme": payload.get("theme"),
                "interests": payload.get("interests"),
                "quest": quest,
            })
