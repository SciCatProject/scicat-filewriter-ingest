# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import argparse
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any


def _load_config(config_file: Any) -> dict:
    """Load configuration from the configuration file path."""
    import json
    import pathlib

    if (
        isinstance(config_file, str | pathlib.Path)
        and (config_file_path := pathlib.Path(config_file)).is_file()
    ):
        return json.loads(config_file_path.read_text())
    return {}


def _merge_config_options(
        config_dict: dict,
        input_args_dict: dict,
        keys: list[str] | None = None
) -> dict:
    """Merge configuration from the configuration file and input arguments."""

    if keys == None:
        keys = config_dict.keys();

    return {
        **config_dict.setdefault("options", {}),
        **{key: input_args_dict[key] for key in keys if input_args_dict[key] is not None},
    }


def _freeze_dict_items(d: dict) -> MappingProxyType:
    """Freeze the dictionary to make it read-only."""
    return MappingProxyType(
        {
            key: MappingProxyType(value) if isinstance(value, dict) else value
            for key, value in d.items()
        }
    )


def _recursive_deepcopy(obj: Any) -> dict:
    """Recursively deep copy a dictionary."""
    if not isinstance(obj, dict | MappingProxyType):
        return obj

    copied = dict(obj)
    for key, value in copied.items():
        if isinstance(value, Mapping | MappingProxyType):
            copied[key] = _recursive_deepcopy(value)

    return copied


def build_online_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    group = parser.add_argument_group("Scicat Ingestor Options")

    group.add_argument(
        "-c",
        "--cf",
        "--config",
        "--config-file",
        default="config.20240405.json",
        dest="config_file",
        help="Configuration file name. Default: config.20240405.json",
        type=str,
    )
    group.add_argument(
        "-d", "--dry-run",
        dest="dry_run",
        help="Dry run. Does not produce any output file nor modify entry in SciCat",
        action="store_true",
        default=False,
    )
    group.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        help="Provide logging on stdout",
        action="store_true",
        default=False,
    )
    group.add_argument(
        "--file-log",
        dest="file_log",
        help="Provide logging on file",
        action="store_true",
        default=False,
    )
    group.add_argument(
        "--file-log-base-name",
        dest="file_log_base_name",
        help="Prefix of the log file path",
        default=".scicat_ingestor_log",
    )
    group.add_argument(
        "--file-log-timestamp",
        dest="file_log_timestamp",
        help="Provide logging on the system log",
        action="store_true",
        default=False,
    )
    group.add_argument(
        "--system-log",
        dest="system_log",
        help="Provide logging on the system log",
        action="store_true",
        default=False,
    )
    group.add_argument(
        "--system-log-facility",
        dest="system_log_facility",
        help="Facility for system log",
        default="mail",
    )
    group.add_argument(
        "--log-message-prefix",
        dest="log_message_prefix",
        help="Prefix for log messages",
        default=" SFI: ",
    )
    group.add_argument(
        "--logging-level",
        dest="logging_level",
        help="Logging level",
        default="INFO",
        type=str,
    )
    group.add_argument(
        "--check-by-job-id",
        dest="check_by_job_id",
        help="Check the status of a job by job_id",
        action="store_true",
        default=True,
    )
    group.add_argument(
        "--graylog",
        dest="graylog",
        help="Use graylog for additional logs",
        action="store_true",
        default=False,
    )
    return parser


def build_offline_ingestor_arg_parser() -> argparse.ArgumentParser:
    parser = build_online_arg_parser()
    group = parser.add_argument_group('Scicat Offline Ingestor Options')

    group.add_argument(
        '-f',
        '--nf',
        '--file',
        '--nexus-file',
        default='',
        dest='nexus_file',
        help='Full path of the input nexus file to be ingested',
        type=str,
    )

    group.add_argument(
        '-m',
        '--dm',
        '--wrdm',
        '--done-writing-message-file',
        default='',
        dest='done_writing_message_file',
        help="""
          Full path of the input done writing message
          file that match the nexus file to be ingested
        """,
        type=str,
    )

    return parser


@dataclass
class LoggingOptions:
    """
    LoggingOptions dataclass to store the configuration options.

    Most of options don't have default values because they are expected
    to be set by the user either in the configuration file or through
    command line arguments.
    """

    verbose: bool
    file_log: bool
    file_log_base_name: str
    file_log_timestamp: bool
    logging_level: str
    log_message_prefix: str
    system_log: bool
    system_log_facility: str | None = None
    graylog: bool = False
    graylog_host: str = ""
    graylog_port: str = ""
    graylog_facility: str = "scicat.ingestor"


@dataclass
class KafkaOptions:
    """
    KafkaOptions dataclass to store the configuration options.

    Default values are provided as they are not
    expected to be set by command line arguments.
    """

    topics: list[str] | str = "KAFKA_TOPIC_1,KAFKA_TOPIC_2"
    """List of Kafka topics. Multiple topics can be separated by commas."""
    group_id: str = "GROUP_ID"
    """Kafka consumer group ID."""
    bootstrap_servers: list[str] | str = "localhost:9092"
    """List of Kafka bootstrap servers. Multiple servers can be separated by commas."""
    sasl_mechanism: str = "PLAIN"
    """Kafka SASL mechanism."""
    sasl_username: str = ""
    """Kafka SASL username."""
    sasl_password: str = ""
    """Kafka SASL password."""
    ssl_ca_location: str = ""
    """Kafka SSL CA location."""
    individual_message_commit: bool = False
    """Commit for each topic individually."""
    enable_auto_commit: bool = True
    """Enable Kafka auto commit."""
    auto_offset_reset: str = "earliest"
    """Kafka auto offset reset."""

    @classmethod
    def from_configurations(cls, config: dict) -> "KafkaOptions":
        """Create kafkaOptions from a dictionary."""
        return cls(**config)


@dataclass
class FileHandlingOptions:
    compute_file_stats: bool = False
    compute_file_hash: bool = False
    file_hash_algorithm: str = "blake2b"
    save_file_hash: bool = False
    hash_file_extension: str = "b2b"
    ingestor_files_directory: str = "../ingestor"
    message_to_file: bool = True
    message_file_extension: str = "message.json"

@dataclass
class IngestionOptions:
    file_handling: FileHandlingOptions
    dry_run: bool = False
    schemas_directory: str = "schemas"
    offline_ingestor_executable: str = "./scicat_offline_ingestor.py"
    check_if_dataset_exists_by_pid: bool = False,
    check_if_dataset_exists_by_metadata: bool = False,
    check_if_dataset_exists_by_metadata_key: str = "",

    @classmethod
    def from_configurations(cls, config: dict) -> "IngestionOptions":
        """Create IngestionOptions from a dictionary."""
        return cls(
            FileHandlingOptions(**config.get("file_handling_options", {})),
            dry_run=config.get("dry_run", False),
            schemas_directory=config.get("schemas_directory", "schemas"),
        )


@dataclass
class DatasetOptions:
    allow_dataset_pid: bool = True,
    generate_dataset_pid: bool = False,
    dataset_pid_prefix: str = "20.500.12269",
    default_instrument_id: str = "",
    default_proposal_id: str = "",
    default_owner_group: str = "",
    default_access_groups: list[str] = field(default_factory=list)

    @classmethod
    def from_configurations(cls, config: dict) -> "DatasetOptions":
        """Create DatasetOptions from a dictionary."""
        return cls(**config)


@dataclass
class SciCatOptions:
    host: str = ""
    token: str = ""
    headers: dict = field(default_factory=dict)
    timeout: int = 0
    stream: bool = True
    verify: bool = False

    @classmethod
    def from_configurations(cls, config: dict) -> "SciCatOptions":
        """Create SciCatOptions from a dictionary."""
        options = cls(**config)
        options.headers = {
            "Authorization": "Bearer {}".format(options.token)
        }
        return options


@dataclass
class OnlineIngestorConfig:
    original_dict: Mapping
    """Original configuration dictionary in the json file."""
    dataset: DatasetOptions
    kafka: KafkaOptions
    logging: LoggingOptions
    ingestion: IngestionOptions
    scicat: SciCatOptions

    def to_dict(self) -> dict:
        """Return the configuration as a dictionary."""

        return asdict(
            OnlineIngestorConfig(
                _recursive_deepcopy(
                    self.original_dict
                ),  # asdict does not support MappingProxyType
                self.dataset,
                self.kafka,
                self.logging,
                self.ingestion,
                self.scicat,
            )
        )


def build_scicat_online_ingestor_config(input_args: argparse.Namespace) -> OnlineIngestorConfig:
    """Merge configuration from the configuration file and input arguments."""
    config_dict = _load_config(input_args.config_file)
    logging_dict = _merge_config_options(config_dict.setdefault("logging",{}), vars(input_args))
    ingestion_dict = _merge_config_options(config_dict.setdefault("ingestion",{}), vars(input_args), ["dry-run"])

    # Wrap configuration in a dataclass
    return OnlineIngestorConfig(
        original_dict=_freeze_dict_items(config_dict),
        dataset=DatasetOptions(**config_dict.setdefault("dataset",{})),
        ingestion=IngestionOptions.from_configurations(ingestion_dict),
        kafka=KafkaOptions(**config_dict.setdefault("kafka", {})),
        logging=LoggingOptions(**logging_dict),
        scicat=SciCatOptions(**config_dict.setdefault("scicat", {})),
    )


@dataclass
class OfflineRunOptions:
    nexus_file: str
    """Full path of the input nexus file to be ingested."""
    done_writing_message_file: str
    """Full path of the done writing message file that match the ``nexus_file``."""

@dataclass
class OfflineIngestorConfig(OnlineIngestorConfig):
    offline_run: OfflineRunOptions
    """Single run configuration options for background ingestor."""

    def to_dict(self) -> dict:
        """Return the configuration as a dictionary."""

        return asdict(
            OfflineIngestorConfig(
                _recursive_deepcopy(
                    self.original_dict
                ),  # asdict does not support MappingProxyType
                self.dataset,
                self.kafka,
                self.logging,
                self.ingestion,
                self.scicat,
                self.offline_run,
            )
        )


def build_scicat_offline_ingestor_config(
    input_args: argparse.Namespace,
) -> OfflineIngestorConfig:
    """Merge configuration from the configuration file and input arguments."""
    config_dict = _load_config(input_args.config_file)
    input_args_dict = vars(input_args)
    logging_dict = _merge_config_options(config_dict.setdefault("logging",{}), input_args_dict)
    ingestion_dict = _merge_config_options(config_dict.setdefault("ingestion",{}), input_args_dict, ["dry-run"])
    offline_run_option_dict = {
        "nexus_file": input_args_dict.pop("nexus_file"),
        "done_writing_message_file": input_args_dict.pop("done_writing_message_file"),
    }

    # Wrap configuration in a dataclass
    return OfflineIngestorConfig(
        original_dict=_freeze_dict_items(config_dict),
        dataset=DatasetOptions(**config_dict.setdefault("dataset",{})),
        ingestion=IngestionOptions.from_configurations(ingestion_dict),
        kafka=KafkaOptions(**config_dict.setdefault("kafka", {})),
        logging=LoggingOptions(**logging_dict),
        scicat=SciCatOptions(**config_dict.setdefault("scicat", {})),
        offline_run=OfflineRunOptions(**offline_run_option_dict),
    )
