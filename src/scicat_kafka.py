# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import logging
from collections.abc import Generator

from confluent_kafka import Consumer
from scicat_configuration import kafkaOptions
from streaming_data_types import deserialise_wrdn
from streaming_data_types.finished_writing_wrdn import (
    FILE_IDENTIFIER as WRDN_FILE_IDENTIFIER,
)
from streaming_data_types.finished_writing_wrdn import WritingFinished


def collect_consumer_options(options: kafkaOptions) -> dict:
    """Build a Kafka consumer and configure it according to the ``options``."""
    from dataclasses import asdict

    # Build logger and formatter
    config_dict = {
        key.replace("_", "."): value
        for key, value in asdict(options).items()
        if key not in ("topics", "individual_message_commit")
    }
    config_dict["enable.auto.commit"] = (
        not options.individual_message_commit
    ) and options.enable_auto_commit
    if isinstance(bootstrap_servers := options.bootstrap_servers, list):
        # Convert the list to a comma-separated string
        config_dict["bootstrap.servers"] = ",".join(bootstrap_servers)
    else:
        config_dict["bootstrap.servers"] = bootstrap_servers

    return config_dict


def collect_kafka_topics(options: kafkaOptions) -> list[str]:
    """Return the Kafka topics as a list."""
    if isinstance(options.topics, str):
        return options.topics.split(",")
    elif isinstance(options.topics, list):
        return options.topics
    else:
        raise TypeError("The topics must be a list or a comma-separated string.")


def build_consumer(kafka_options: kafkaOptions, logger: logging.Logger) -> Consumer:
    """Build a Kafka consumer and configure it according to the ``options``."""
    consumer_options = collect_consumer_options(kafka_options)
    logger.info("Connecting to Kafka with the following parameters:")
    logger.info(consumer_options)
    consumer = Consumer(consumer_options)
    if not validate_consumer(consumer, logger):
        return None

    kafka_topics = collect_kafka_topics(kafka_options)
    logger.info("Subscribing to the following Kafka topics: %s", kafka_topics)
    consumer.subscribe(kafka_topics)
    return Consumer(consumer_options)


def validate_consumer(consumer: Consumer, logger: logging.Logger) -> bool:
    try:
        consumer.list_topics(timeout=1)
    except Exception as err:
        logger.error(
            "Kafka consumer could not be instantiated. "
            "Error message from kafka thread: \n%s",
            err,
        )
        return False
    else:
        logger.info("Kafka consumer successfully instantiated")
        return True


def _validate_data_type(message_content: bytes, logger: logging.Logger) -> bool:
    logger.info("Data type: %s", (data_type := message_content[4:8]))
    if data_type == WRDN_FILE_IDENTIFIER:
        logger.info("WRDN message received.")
        return True
    else:
        logger.error("Unexpected data type: %s", data_type)
        return False


def _filter_error_encountered(
    wrdn_content: WritingFinished, logger: logging.Logger
) -> WritingFinished | None:
    """Filter out messages with the ``error_encountered`` flag set to True."""
    if wrdn_content.error_encountered:
        logger.error(
            "``error_encountered`` flag True. "
            "Unable to deserialize message. Skipping the message."
        )
        return wrdn_content
    else:
        return None


def _deserialise_wrdn(
    message_content: bytes, logger: logging.Logger
) -> WritingFinished | None:
    if _validate_data_type(message_content, logger):
        logger.info("Deserialising WRDN message")
        wrdn_content: WritingFinished = deserialise_wrdn(message_content)
        logger.info("Deserialised WRDN message: %.5000s", wrdn_content)
        return _filter_error_encountered(wrdn_content, logger)


def wrdn_messages(
    consumer: Consumer, logger: logging.Logger
) -> Generator[WritingFinished | None, None, None]:
    """Wait for a WRDN message and yield it.

    Yield ``None`` if no message is received or an error is encountered.
    """
    while True:
        # The decision to proceed or stop will be done by the caller.
        message = consumer.poll(timeout=1.0)
        if message is None:
            logger.info("Received no messages")
            yield None
        elif message.error():
            logger.error("Consumer error: %s", message.error())
            yield None
        else:
            # retrieve type of message
            message_value = message.value()
            message_type = message_value[4:8]
            logger.info("Received message. Type : %s", message_type)
            if message_type == b"wrdn":
                yield _deserialise_wrdn(message_value, logger)
            else:
                yield None
