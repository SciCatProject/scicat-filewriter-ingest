# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 Scicatproject contributors (https://github.com/ScicatProject)
# ruff: noqa: E402, F401

import importlib.metadata
import logging
import pathlib
import subprocess

try:
    __version__ = importlib.metadata.version(__package__ or __name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

del importlib
from pathlib import Path

from scicat_configuration import (
    FileHandlingOptions,
    OnlineIngestorConfig,
    build_arg_parser,
    build_dataclass,
    merge_config_and_input_args,
)
from scicat_kafka import (
    WritingFinished,
    build_consumer,
    save_message_to_file,
    wrdn_messages,
)
from scicat_logging import build_logger
from scicat_path_helpers import (
    compose_ingestor_directory,
    compose_ingestor_output_file_path,
)
from system_helpers import handle_daemon_loop_exceptions


def dump_message_to_file_if_needed(
        *,
        logger: logging.Logger,
        message_file_path: pathlib.Path,
        file_handling_options: FileHandlingOptions,
        message: WritingFinished,
) -> None:
    """Dump the message to a file according to the configuration."""
    if not file_handling_options.message_to_file:
        logger.info("Message saving to file is disabled. Skipping saving message.")
        return
    elif not message_file_path.parent.exists():
        logger.info("Message file directory not accessible. Skipping saving message.")
        return

    logger.info("Message will be saved in %s", message_file_path)
    save_message_to_file(
        message=message,
        message_file_path=message_file_path,
    )
    logger.info("Message file saved")


def _individual_message_commit(offline_ingestors, consumer, logger: logging.Logger):
    logger.info("%s offline ingestors running", len(offline_ingestors))
    for job_id, job_item in offline_ingestors.items():
        result = job_item["proc"].poll()
        if result is not None:
            logger.info(
                "Offline ingestor for job id %s ended with result %s", job_id, result
            )
            if result == 0:
                logger.info("Offline ingestor successful for job id %s", job_id)
                logger.info("Executing commit for message with job id %s", job_id)
                consumer.commit(message=job_item["message"])
            else:
                logger.error("Offline ingestor error for job id %s", job_id)
            logger.info(
                "Removed ingestor for message with job id %s from queue", job_id
            )
            offline_ingestors.pop(job_id)


def build_online_config(logger: logging.Logger | None = None) -> OnlineIngestorConfig:
    arg_parser = build_arg_parser(
        OnlineIngestorConfig, mandatory_args=('--config-file',)
    )
    arg_namespace = arg_parser.parse_args()
    merged_configuration = merge_config_and_input_args(
        Path(arg_namespace.config_file), arg_namespace
    )

    return build_dataclass(
        tp=OnlineIngestorConfig, data=merged_configuration, logger=logger, strict=False
    )


def _pre_executable_offline_ingestor(offline_ingestor: str | list[str]) -> list[str]:
    return [offline_ingestor] if isinstance(offline_ingestor, str) else offline_ingestor


def main() -> None:
    """Main entry point of the app."""
    tmp_config = build_online_config()
    logger = build_logger(tmp_config)
    config = build_online_config(logger=logger)

    # Log the configuration as dictionary so that it is easier to read from the logs
    logger.info('Starting the Scicat online Ingestor with the following configuration:')
    logger.info(config.to_dict())

    with ((handle_daemon_loop_exceptions(logger=logger))):
        # Kafka consumer
        if (consumer := build_consumer(config.kafka, logger)) is None:
            raise RuntimeError("Failed to build the Kafka consumer")

        # this is the dictionary that contains the list of offline ingestor running
        offline_ingestors: dict = {}

        # Receive messages
        for message in wrdn_messages(consumer, logger):
            logger.info("Processing message: %s", message)

            # Check if we have received a WRDN message.
            # ``message: None | WritingFinished``
            if message:
                # extract job id
                job_id = message.job_id
                logger.info("Processing file writer job id: %s", job_id)
                # Extract nexus file path from the message.
                nexus_file_path = pathlib.Path(message.file_name)
                logger.info("Processing nexus file: %s", nexus_file_path)

                # instantiate a new process and runs background ingestor
                # on the nexus file
                # use open process and wait for outcome
                """
                background_ingestor
                    -c configuration_file
                    --nexus-file nexus_filename
                    --done-writing-message-file message_file_path
                    # optional depending on the message_saving_options.message_output
                """
                cmd = _pre_executable_offline_ingestor(config.ingestion.offline_ingestor_executable) + [
                    "-c",
                    config.config_file,
                    "--nexus-file",
                    str(nexus_file_path),
                ]
                if config.ingestion.file_handling.message_to_file:
                    ingestor_directory = compose_ingestor_directory(
                        config.ingestion.file_handling, nexus_file_path
                    )
                    done_writing_message_file_path = compose_ingestor_output_file_path(
                        ingestor_directory=ingestor_directory,
                        file_name=nexus_file_path.stem,
                        file_extension=config.ingestion.file_handling.message_file_extension,
                    )
                    dump_message_to_file_if_needed(
                        logger=logger,
                        file_handling_options=config.ingestion.file_handling,
                        message=message,
                        message_file_path=done_writing_message_file_path,
                    )
                    cmd += [
                        "--done-writing-message-file",
                        done_writing_message_file_path,
                    ]

                logger.info("Command to be run: \n\n%s\n\n", cmd)
                if config.ingestion.dry_run:
                    logger.info("Dry run mode enabled. Skipping background ingestor.")
                else:
                    logger.info("Running background ingestor with command above")
                    proc = subprocess.Popen(cmd)  #  noqa: S603
                    # save info about the background process
                    offline_ingestors[job_id] = {"proc": proc, "message": message}

                    # if background process is successful
                    # check if we need to commit the individual message
                    if config.kafka.individual_message_commit:
                        _individual_message_commit(offline_ingestors, consumer, logger)


if __name__ == "__main__":
    main()
