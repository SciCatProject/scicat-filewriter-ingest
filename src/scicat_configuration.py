# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import argparse
from dataclasses import dataclass
from typing import Mapping, Optional


def build_main_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    group = parser.add_argument_group('Scicat Ingestor Options')

    group.add_argument(
        '-c',
        '--cf',
        '--config',
        '--config-file',
        default='config.20240405.json',
        dest='config_file',
        help='Configuration file name. Default: config.20240405.json',
        type=str,
    )
    group.add_argument(
        '-v',
        '--verbose',
        dest='verbose',
        help='Provide logging on stdout',
        action='store_true',
        default=False,
    )
    group.add_argument(
        '--file-log',
        dest='file_log',
        help='Provide logging on file',
        action='store_true',
        default=False,
    )
    group.add_argument(
        '--log-file-suffix',
        dest='log_file_suffix',
        help='Suffix of the log file name',
        default='.scicat_ingestor_log',
    )
    group.add_argument(
        '--file-log-timestamp',
        dest='file_log_timestamp',
        help='Provide logging on the system log',
        action='store_true',
        default=False,
    )
    group.add_argument(
        '--system-log',
        dest='system_log',
        help='Provide logging on the system log',
        action='store_true',
        default=False,
    )
    group.add_argument(
        '--system-log-facility',
        dest='system_log_facility',
        help='Facility for system log',
        default='mail',
    )
    group.add_argument(
        '--log-prefix',
        dest='log_prefix',
        help='Prefix for log messages',
        default=' SFI: ',
    )
    group.add_argument(
        '--log-level', dest='log_level', help='Logging level', default='INFO', type=str
    )
    group.add_argument(
        '--check-by-job-id',
        dest='check_by_job_id',
        help='Check the status of a job by job_id',
        action='store_true',
        default=True,
    )
    group.add_argument(
        '--pyscicat',
        dest='pyscicat',
        help='Location where a specific version of pyscicat is available',
        default=None,
        type=str,
    )
    return parser


@dataclass
class RunOptions:
    config_file: str
    verbose: bool
    file_log: bool
    log_file_suffix: str
    file_log_timestamp: bool
    system_log: bool
    system_log_facility: str
    log_prefix: str
    log_level: str
    check_by_job_id: bool
    pyscicat: Optional[str] = None


@dataclass
class ScicatConfig:
    original_dict: Mapping
    """Original configuration dictionary in the json file."""
    run_options: RunOptions
    """Merged configuration dictionary with command line arguments."""


def build_scicat_config(input_args: argparse.Namespace) -> ScicatConfig:
    """Merge configuration from the configuration file and input arguments."""
    import copy
    import json
    import pathlib
    from types import MappingProxyType

    # Read configuration file
    if (
        input_args.config_file
        and (config_file_path := pathlib.Path(input_args.config_file)).is_file()
    ):
        config_dict = json.loads(config_file_path.read_text())
    else:
        config_dict = dict()

    # Overwrite deep-copied options with command line arguments
    run_option_dict: dict = copy.deepcopy(config_dict.setdefault('options', dict()))
    for arg_name, arg_value in vars(input_args).items():
        if arg_value is not None:
            run_option_dict[arg_name] = arg_value

    # Protect original configuration by making it read-only
    for key, value in config_dict.items():
        config_dict[key] = MappingProxyType(value)

    # Wrap configuration in a dataclass
    return ScicatConfig(
        original_dict=MappingProxyType(config_dict),
        run_options=RunOptions(**run_option_dict),
    )