def post_worker_init(worker):
    try:
        import fulfillment_app
        worker.log.info("GeburtstagsQuest fulfillment package initialized")
        worker.log.info("GeburtstagsQuest premium QA, adaptive difficulty, PDF normalization and audio delivery are installed by fulfillment_app/__init__.py")
    except Exception:
        worker.log.exception("Failed to initialize GeburtstagsQuest fulfillment package")
