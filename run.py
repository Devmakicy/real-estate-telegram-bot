import asyncio
import logging
import multiprocessing
import sys

import uvicorn

from config import WEB_HOST, WEB_PORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_bot() -> None:
    from bot.main import main

    asyncio.run(main())


def run_web() -> None:
    uvicorn.run("admin.app:app", host=WEB_HOST, port=WEB_PORT, reload=False)


def main() -> None:
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "bot":
            run_bot()
        elif cmd == "web":
            run_web()
        else:
            print("Usage: python run.py [bot|web|all]")
            sys.exit(1)
        return

    bot_process = multiprocessing.Process(target=run_bot, daemon=True)
    bot_process.start()
    logger.info("Bot process started (pid=%s)", bot_process.pid)

    try:
        run_web()
    finally:
        bot_process.terminate()
        bot_process.join(timeout=5)


if __name__ == "__main__":
    main()
