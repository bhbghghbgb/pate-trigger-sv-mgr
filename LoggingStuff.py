import asyncio
from datetime import datetime
import logging
from logging import FileHandler, LogRecord, StreamHandler
import os
from queue import Queue
from threading import Thread
import json
from discord_webhook import DiscordWebhook, AsyncDiscordWebhook

CODENAME = "pate-trigger-sv-mgr"
with open("secrets.json", "r") as f:
    secrets = json.load(f)
DISCORD_WEBHOOK_URL = secrets["DISCORD_WEBHOOK_URL"]
ROLE_TO_PING_FOR_ATTENTION = secrets["ROLE_TO_PING_FOR_ATTENTION"]
EMOJIS = {
    logging.DEBUG: "🔌",
    logging.INFO: "ℹ️",
    logging.WARNING: "⚠️",
    logging.ERROR: "💢",
    logging.CRITICAL: "🆘",
}
MESSAGE_LENGTH_LIMIT_INDEX = 1997
MESSAGE_LIMIT_SPLIT_INDICATOR = "⤵️"
MESSAGE_LIMIT_CONTINUE_INDICATOR = "↪️"


# https://github.com/CopterExpress/python-async-logging-handler/blob/master/async_logging_handler/__init__.py
# https://stackoverflow.com/questions/75090778/making-a-logging-handler-with-async-emit
class DiscordWebhookHandler(logging.Handler):
    def __init__(
        self,
        discord_webhook_url: str,
        level=0,
    ) -> None:
        super().__init__(level)
        self.discord_webhook_url = discord_webhook_url
        self.queue = Queue()
        self.thread = Thread(target=self.queue_consumer)
        self.thread.daemon = True
        self.thread.start()

    def emit(self, record: LogRecord) -> None:
        self.queue.put(record)

    def queue_consumer(self):
        while True:
            record = self.queue.get()
            try:
                self.webhook_emit(self.format(record))
            except Exception as e:
                print(e)
            self.queue.task_done()

    def webhook_emit(self, message):
        for split_message in discord_message_limit_iter(message):
            DiscordWebhook(
                url=self.discord_webhook_url,
                rate_limit_retry=True,
                content=split_message,
            ).execute()

    def format(self, record: LogRecord) -> str:
        return f"{EMOJIS[record.levelno]} {super().format(record)} {ROLE_TO_PING_FOR_ATTENTION_str if record.levelno >= logging.WARNING else ''}"

    def close(self) -> None:
        logger.debug("Waiting for all logs to be sent to discord webhook")
        self.queue.join()
        super().close()


def discord_message_limit_iter(message: str):
    is_first_message = True
    left_index = 0
    right_index = MESSAGE_LENGTH_LIMIT_INDEX

    def indicate_message(message: str, is_first_message: bool, more_messages: bool):
        return f"{MESSAGE_LIMIT_CONTINUE_INDICATOR if not is_first_message else ''}{message}{MESSAGE_LIMIT_SPLIT_INDICATOR if more_messages else ''}"

    while right_index < len(message):
        newline_index = message.rfind("\n", left_index, right_index)
        # a single line of string
        if newline_index == -1:
            yield indicate_message(
                message[left_index:right_index],
                is_first_message,
                right_index < len(message),
            )
            left_index = right_index + 1
            right_index = left_index + MESSAGE_LENGTH_LIMIT_INDEX
        else:
            yield indicate_message(
                message[left_index : newline_index - 1],
                is_first_message,
                newline_index < len(message),
            )
            left_index = newline_index + 1
            right_index = left_index + MESSAGE_LENGTH_LIMIT_INDEX
        is_first_message = False
    # whatever remaining
    yield indicate_message(message[left_index:], is_first_message, False)


def discord_ping_role(role_id: int):
    return f"<@&{role_id}>"


async def webhook_file_upload(files: list[str]):
    webhook = AsyncDiscordWebhook(
        url=DISCORD_WEBHOOK_URL,
        rate_limit_retry=True,
        content=datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f"),
    )
    for file in files:
        try:
            with open(file, "rb") as f:
                logger.debug("Loading file %s for webhook upload", file)
                webhook.add_file(f.read(), os.path.basename(file))
        except FileNotFoundError:
            logger.exception("File upload error, path %s", file)
    await webhook.execute()
    logger.debug("Attempted to upload %d files to webhook", len(files))


ROLE_TO_PING_FOR_ATTENTION_str = discord_ping_role(ROLE_TO_PING_FOR_ATTENTION)


logger = logging.getLogger(CODENAME)


def setup_logging():
    verbose_formatter = logging.Formatter(
        "%(asctime)s,%(msecs)03d %(levelname).1s %(message)s", "%H:%M:%S"
    )
    file_formatter = logging.Formatter("%(asctime)s %(levelname).1s %(message)s")
    logger.setLevel(logging.DEBUG)
    sh = StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(verbose_formatter)
    logger.addHandler(sh)
    fh = FileHandler(f"{CODENAME}.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(file_formatter)
    logger.addHandler(fh)
    dwh = DiscordWebhookHandler(DISCORD_WEBHOOK_URL)
    dwh.setLevel(logging.INFO)
    dwh.setFormatter(verbose_formatter)
    logger.addHandler(dwh)


async def main():
    setup_logging()
    logger.info("ME MAY SIEU BEO")


if __name__ == "__main__":
    asyncio.run(main())
