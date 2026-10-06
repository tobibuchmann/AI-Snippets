import copy


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
