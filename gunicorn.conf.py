def post_worker_init(worker):
    try:
        import fulfillment_app
        from premium_pdf import structured_pdf_bytes as premium_structured_pdf_bytes
        from product_upgrade import apply_upgrade

        fulfillment_app.structured_pdf_bytes = premium_structured_pdf_bytes
        apply_upgrade(fulfillment_app)
        worker.log.info("GeburtstagsQuest premium PDF renderer enabled")
        worker.log.info("GeburtstagsQuest adaptive difficulty + audio upgrade enabled")
    except Exception:
        worker.log.exception("Failed to enable GeburtstagsQuest product upgrades")
