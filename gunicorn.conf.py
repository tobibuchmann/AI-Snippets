def post_worker_init(worker):
    try:
        import fulfillment_app
        from premium_pdf import structured_pdf_bytes as premium_structured_pdf_bytes
        fulfillment_app.structured_pdf_bytes = premium_structured_pdf_bytes
        worker.log.info("GeburtstagsQuest premium PDF renderer enabled")
    except Exception:
        worker.log.exception("Failed to enable premium PDF renderer")
