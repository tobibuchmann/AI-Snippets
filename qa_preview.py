import io
import json
import os
import secrets

from flask import abort, request, send_file


def install_preview(legacy):
    token = os.getenv("QA_PREVIEW_TOKEN", "").strip()
    if not token:
        return

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
