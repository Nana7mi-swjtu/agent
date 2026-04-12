import os
import logging

from app import create_app


app = create_app()
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info("Starting Flask development server", extra={"event": "app.server.start", "port": port})
    app.run(host="0.0.0.0", port=port, debug=False)
