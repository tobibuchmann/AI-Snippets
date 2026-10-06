import copy
import os


def apply_output_upgrade(module):
    """Normalize current quest-schema fields for the existing premium PDF renderer."""
    base_renderer = module.structured_pdf_bytes

    def structured_pdf_bytes(quest, payload):
        normalized = copy.deepcopy(quest)

        for station in normalized.get("stations") or []:
            # The premium renderer predates the current structured schema.
            # Normalize field names so children see the complete playable card
            # and parents see the generated hints and real station duration.
            station["story"] = station.get("child_card") or station.get("story") or ""
            if station.get("duration_minutes") is not None:
                station["duration"] = f"{station.get('duration_minutes')} Min."
            station["hint1"] = station.get("hint_1") or station.get("hint1") or ""
            station["hint2"] = station.get("hint_2") or station.get("hint2") or ""

        indoor = normalized.get("indoor_fallback")
        if indoor:
            normalized["indoor_plan"] = indoor

        bonus = normalized.get("bonus_game")
        if isinstance(bonus, dict):
            normalized["bonus_game"] = (
                str(bonus.get("title") or "Bonus-Mission")
                + "\n"
                + str(bonus.get("instructions") or "")
            ).strip()

        return base_renderer(normalized, payload)

    module.structured_pdf_bytes = structured_pdf_bytes

    # Expose a non-sensitive deployment marker so the live backend can be checked
    # without revealing keys or configuration values.
    previous_health = module.app.view_functions.get("health")
    if previous_health:
        def upgraded_health():
            response = previous_health()
            try:
                data = response.get_json() or {}
            except Exception:
                data = {"ok": True}
            data["product_upgrade"] = module.app.config.get("GQ_PRODUCT_UPGRADE", "unknown")
            data["adaptive_difficulty"] = True
            data["personalized_audio"] = True
            data["tts_model"] = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
            return module.jsonify(data)

        module.app.view_functions["health"] = upgraded_health
