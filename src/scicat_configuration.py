# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import argparse
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from functools import partial
from inspect import get_annotations
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar, get_origin
from urllib.parse import urljoin


def _load_config(config_file: Path) -> dict:
    """Load configuration from the configuration file path."""
    import json

    if config_file.is_file():
        return json.loads(config_file.read_text())
    else:
        raise FileNotFoundError(f"Configuration file not found: {config_file}")


def _insert_item(d: dict, key: str, value: Any) -> None:
    """Insert a key-value pair into a dictionary.

    If ``key`` is a nested key, the function creates the nested dictionary.

    Example:
    >>> d = {}
    >>> _insert_item(d, "a.b.c", 1)
    >>> d
    {'a': {'b': {'c': 1}}}
    """
    key_parts = key.split(".")
    for key_part in key_parts[:-1]:
        d = d.setdefault(key_part, {})
    d[key_parts[-1]] = value


def _parse_nested_input_args(input_args: argparse.Namespace) -> dict:
    nested_args = {}
    for key, value in vars(input_args).items():
        _insert_item(nested_args, key, value)
    return nested_args


_SHORTENED_ARG_NAMES = MappingProxyType(
    {
        "config-file": "c",
        "ingestion.dry-run": "d",
    }
)

_HELP_TEXT = {
    "config-file": "Path to the configuration file.",
    "ingestion.dry-run": "Dry run mode. No data will be sent to SciCat.",
}


def _wrap_arg_names(name: str, *prefixes: str) -> tuple[str, ...]:
    long_name = (".".join((*prefixes, name)) if prefixes else name).replace("_", "-")
    long_arg_name = "--" + long_name
    return (
        (long_arg_name,)
        if (short_arg_name := _SHORTENED_ARG_NAMES.get(long_name)) is None
        else ("-" + short_arg_name, long_arg_name)
    )


def build_arg_parser(
    config_dataclass: type, mandatory_args: tuple[str, ...] = ()
) -> argparse.ArgumentParser:
    """Build an argument parser from a dataclass.

    **Note**: It can't parse the annotations from parent class.
    """
    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)

    def _add_arguments(dataclass_tp: type, prefixes: tuple[str, ...] = ()) -> None:
        # Add argument group if prefixes are provided
        if len(prefixes) > 0:
            group_name = " ".join(
                prefix.replace("_", " ").capitalize() for prefix in prefixes
            )
            group = parser.add_argument_group(group_name)
        else:
            group = parser

        all_types = get_annotations(dataclass_tp)
        # Add arguments for atomic types
        atomic_types = {
            name: tp for name, tp in all_types.items() if not is_dataclass(tp)
        }

        for name, tp in atomic_types.items():
            arg_names = _wrap_arg_names(name, *prefixes)
            required = any(arg_name in mandatory_args for arg_name in arg_names)
            long_name = arg_names[-1].replace("--", "")
            arg_adder = partial(
                group.add_argument,
                *arg_names,
                required=required,
                help=_HELP_TEXT.get(long_name),
            )
            if tp is bool:
                arg_adder(action="store_true")
            elif tp in (int, float, str):
                arg_adder(type=tp)
            elif (
                tp is list
                or tp is tuple
                or (orig := get_origin(tp)) is list
                or orig is tuple
            ):
                arg_adder(nargs="+")
            elif tp is dict:
                ...  # dict type is not supported from the command line
            elif tp == str | None:
                arg_adder(type=str)
            else:
                raise ValueError(
                    f"Unsupported type for argument parsing: {tp} in {dataclass_tp}"
                )

        # Recursively add arguments for nested dataclasses
        # It is done separately to use argument groups
        sub_dataclasses = {
            name: tp
            for name, tp in all_types.items()
            if is_dataclass(tp) and isinstance(tp, type)
        }

        for name, tp in sub_dataclasses.items():
            _add_arguments(tp, (*prefixes, name))

    _add_arguments(config_dataclass)
    return parser


def _recursive_deepcopy(obj: Any) -> dict:
    """Recursively deep copy a dictionary."""
    if not isinstance(obj, dict | MappingProxyType):
        return obj

    copied = dict(obj)
    for key, value in copied.items():
        if isinstance(value, Mapping | MappingProxyType):
            copied[key] = _recursive_deepcopy(value)

    return copied


@dataclass(kw_only=True)
class LoggingOptions:
    """
    LoggingOptions dataclass to store the configuration options.

    Most of options don't have default values because they are expected
    to be set by the user either in the configuration file or through
    command line arguments.
    """

    verbose: bool = False
    file_log: bool = False
    file_log_base_name: str = "scicat_ingestor_log"
    file_log_timestamp: bool = False
    logging_level: str = "INFO"
    log_message_prefix: str = "SFI"
    system_log: bool = False
    system_log_facility: str | None = "mail"
    graylog: bool = False
    graylog_host: str = ""
    graylog_port: str = ""
    graylog_facility: str = "scicat.ingestor"


@dataclass(kw_only=True)
class KafkaOptions:
    """
    KafkaOptions dataclass to store the configuration options.

    Default values are provided as they are not
    expected to be set by command line arguments.
    """

    topics: str = "KAFKA_TOPIC_1,KAFKA_TOPIC_2"
    """List of Kafka topics. Multiple topics can be separated by commas."""
    group_id: str = "GROUP_ID"
    """Kafka consumer group ID."""
    bootstrap_servers: str = "localhost:9093"
    """List of Kafka bootstrap servers. Multiple servers can be separated by commas."""
    security_protocol: str = "sasl_ssl"
    """Security protocol """
    sasl_mechanism: str = "SCRAM-SHA-256"
    """Kafka SASL mechanism."""
    sasl_username: str = "USERNAME"
    """Kafka SASL username."""
    sasl_password: str = "PASSWORD"
    """Kafka SASL password."""
    ssl_ca_location: str = "FULL_PATH_TO_CERTIFICATE_FILE"
    """Kafka SSL CA location."""
    individual_message_commit: bool = True
    """Commit for each topic individually."""
    enable_auto_commit: bool = True
    """Enable Kafka auto commit."""
    auto_offset_reset: str = "earliest"
    """Kafka auto offset reset."""


@dataclass(kw_only=True)
class FileHandlingOptions:
    compute_file_stats: bool = True
    compute_file_hash: bool = True
    file_hash_algorithm: str = "blake2b"
    save_file_hash: bool = True
    hash_file_extension: str = "b2b"
    ingestor_files_directory: str = "../ingestor"
    message_to_file: bool = True
    message_file_extension: str = "message.json"
    file_path_type: str = "relative"  # allowed values: absolute and relative


@dataclass(kw_only=True)
class IngestionOptions:
    dry_run: bool = False
    offline_ingestor_executable: str | list[str]= "background_ingestor"
    schemas_directory: str = "schemas"
    check_if_dataset_exists_by_pid: bool = True
    check_if_dataset_exists_by_metadata: bool = True
    check_if_dataset_exists_by_metadata_key: str = "job_id"
    file_handling: FileHandlingOptions = field(default_factory=FileHandlingOptions)


def default_access_groups() -> list[str]:
    return ["ACCESS_GROUP_1"]


@dataclass(kw_only=True)
class DatasetOptions:
    allow_dataset_pid: bool = True
    generate_dataset_pid: bool = False
    dataset_pid_prefix: str = "20.500.12269"
    default_instrument_id: str = "ID_OF_FALLBACK_INSTRUMENT"
    default_proposal_id: str = "DEFAULT_PROPOSAL_ID"
    default_owner_group: str = "DEFAULT_OWNER_GROUP"
    default_access_groups: list[str] = field(default_factory=default_access_groups)


@dataclass(kw_only=True)
class _ScicatAPIURLs:
    datasets: str
    proposals: str
    origdatablocks: str
    instruments: str


@dataclass(kw_only=True)
class ScicatEndpoints:
    datasets: str = "datasets"
    proposals: str = "proposals"
    origdatablocks: str = "origdatablocks"
    instruments: str = "instruments"


@dataclass(kw_only=True)
class SciCatOptions:
    host: str = "https://scicat.host"
    token: str = "JWT_TOKEN"
    additional_headers: dict = field(default_factory=dict)
    timeout: int = 0
    stream: bool = True
    verify: bool = False
    api_endpoints: ScicatEndpoints = field(default_factory=ScicatEndpoints)

    @property
    def urls(self) -> _ScicatAPIURLs:
        return _ScicatAPIURLs(
            datasets=urljoin(self.host_address, self.api_endpoints.datasets),
            proposals=urljoin(self.host_address, self.api_endpoints.proposals),
            origdatablocks=urljoin(
                self.host_address, self.api_endpoints.origdatablocks
            ),
            instruments=urljoin(self.host_address, self.api_endpoints.instruments),
        )

    @property
    def headers(self) -> dict:
        return {
            **self.additional_headers,
            **{"Authorization": f"Bearer {self.token}"},
        }

    @property
    def host_address(self) -> str:
        """Return the host address ready to be used."""
        return self.host.removesuffix('/') + "/"


@dataclass(kw_only=True)
class OnlineIngestorConfig:
    # original_dict: Mapping
    """Original configuration dictionary in the json file."""

    config_file: str
    id: str = ""
    dataset: DatasetOptions = field(default_factory=DatasetOptions)
    ingestion: IngestionOptions = field(default_factory=IngestionOptions)
    kafka: KafkaOptions = field(default_factory=KafkaOptions)
    logging: LoggingOptions = field(default_factory=LoggingOptions)
    scicat: SciCatOptions = field(default_factory=SciCatOptions)

    def to_dict(self) -> dict:
        """Return the configuration as a dictionary."""

        return asdict(self)


@dataclass(kw_only=True)
class OfflineIngestorConfig:
    nexus_file: str
    """Full path of the input nexus file to be ingested."""
    done_writing_message_file: str
    """Full path of the done writing message file that match the ``nexus_file``."""
    config_file: str
    id: str
    dataset: DatasetOptions = field(default_factory=DatasetOptions)
    ingestion: IngestionOptions = field(default_factory=IngestionOptions)
    logging: LoggingOptions = field(default_factory=LoggingOptions)
    scicat: SciCatOptions = field(default_factory=SciCatOptions)

    def to_dict(self) -> dict:
        """Return the configuration as a dictionary."""

        return asdict(self)


T = TypeVar("T")


def build_dataclass(
    *,
    tp: type[T],
    data: dict,
    prefixes: tuple[str, ...] = (),
    logger: logging.Logger | None = None,
    strict: bool = False,
) -> T:
    type_hints = get_annotations(tp)
    unused_keys = set(data.keys()) - set(type_hints.keys())
    if unused_keys:
        # If ``data`` contains unnecessary fields.
        unused_keys_repr = "\n\t\t- ".join(
            ".".join((*prefixes, unused_key)) for unused_key in unused_keys
        )
        error_message = f"Invalid argument found: \n\t\t- {unused_keys_repr}"
        if logger is not None:
            logger.warning(error_message)
        if strict:
            raise ValueError(error_message)
    return tp(
        **{
            key: build_dataclass(tp=sub_tp, data=value, prefixes=(*prefixes, key))
            if is_dataclass(sub_tp := type_hints.get(key))
            else value
            for key, value in data.items()
            if key not in unused_keys
        }
    )


def _merge_config_and_input_args(config_dict: dict, input_args_dict: dict) -> dict:
    """Merge nested dictionaries.

    ``input_args_dict`` has higher priority than ``config_dict``.
    """
    return {
        key: _merge_config_and_input_args(
            config_dict.get(key, {}), input_args_dict.get(key, {})
        )
        if (
            isinstance(config_dict.get(key), dict)
            or isinstance(input_args_dict.get(key), dict)
        )
        else i_value
        if (i_value := input_args_dict.get(key)) is not None
        else config_dict.get(key)
        for key in set(config_dict.keys()).union(set(input_args_dict.keys()))
    }


def merge_config_and_input_args(
    config_file: Path, arg_namespace: argparse.Namespace
) -> dict[str, Any]:
    config_from_file = _load_config(config_file)
    return _merge_config_and_input_args(
        config_from_file, _parse_nested_input_args(arg_namespace)
    )


def _validate_config_file(target_type: type[T], config_file: Path) -> T:
    config = {**_load_config(config_file), "config_file": config_file.as_posix()}
    return build_dataclass(tp=target_type, data=config, strict=True)


def validate_config_file() -> None:
    """Validate the configuration file."""
    import logging

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        help="Configuration file path to validate.", dest="config_file"
    )
    config_file = Path(arg_parser.parse_args().config_file)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Always debug level since it is for validation
    logger.addHandler(logging.StreamHandler())
    logger.info("Scicat file ingestor configuration file validation test.")
    logger.info("Note that it does not validate type of the field.")
    logger.debug("It only validate the file for %s.", OnlineIngestorConfig)
    logger.debug("Configuration file: %s", config_file)

    if not config_file.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    logger.debug(
        "Configuration built successfully. %s",
        _validate_config_file(OnlineIngestorConfig, config_file),
    )
    logger.info("Configuration file %s is valid.", config_file)


def synchronize_config_file() -> None:
    """Synchronize the configurations from the dataclass and json file."""
    import json

    config_file_from_repo = Path("resources/config.sample.json")
    default_config = OnlineIngestorConfig(config_file="")

    target_file = Path(__file__).parent.parent / config_file_from_repo
    target_file.write_text(json.dumps(default_config.to_dict(), indent=2) + "\n")


if __name__ == "__main__":
    validate_config_file()
