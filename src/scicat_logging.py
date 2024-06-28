# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import datetime
import logging
import logging.handlers

import graypy
from scicat_configuration import ScicatConfig


def build_logger(config: ScicatConfig) -> logging.Logger:
    """Build a logger and configure it according to the ``config``."""
    run_options = config.run_options

    # Build logger and formatter
    logger = logging.getLogger('esd extract parameters')
    formatter = logging.Formatter(
        run_options.log_message_prefix
        + '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Add FileHandler
    if run_options.file_log:
        file_name_components = [run_options.log_filepath_prefix]
        if run_options.file_log_timestamp:
            file_name_components.append(
                datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S%f')
            )
        file_name_components.append('.log')

        file_name = '_'.join(file_name_components)
        file_handler = logging.FileHandler(file_name, mode='w', encoding='utf-8')
        logger.addHandler(file_handler)

    # Add SysLogHandler
    if run_options.system_log:
        logger.addHandler(logging.handlers.SysLogHandler(address='/dev/log'))

    # Add graylog handler
    if run_options.graylog:
        graylog_config = config.graylog_options
        graylog_handler = graypy.GELFTCPHandler(
            graylog_config.host,
            int(graylog_config.port),
            facility=graylog_config.facility,
        )
        logger.addHandler(graylog_handler)

    # Set the level and formatter for all handlers
    logger.setLevel(run_options.log_level)
    for handler in logger.handlers:
        handler.setLevel(run_options.log_level)
        handler.setFormatter(formatter)

    # Add StreamHandler
    # streamer handler is added last since it is using different formatter
    if run_options.verbose:
        from rich.logging import RichHandler

        logger.addHandler(RichHandler(level=run_options.log_level))

    return logger
