# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import ast
import copy
import datetime
import logging
import os.path
import pathlib
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any

import h5py
from scicat_communication import render_full_url, retrieve_value_from_scicat
from scicat_configuration import (
    DatasetOptions,
    FileHandlingOptions,
    OfflineIngestorConfig,
)
from scicat_metadata import (
    HIGH_LEVEL_METADATA_TYPE,
    SCIENTIFIC_METADATA_TYPE,
    VALID_METADATA_TYPES,
    MetadataItem,
    MetadataSchemaVariable,
    NexusFileMetadataVariable,
    ScicatMetadataVariable,
    ValueMetadataVariable,
    render_variable_value,
)


def to_string(value: Any) -> str:
    return str(value)


def to_string_array(value: list[Any]) -> list[str]:
    return [
        str(v) for v in (ast.literal_eval(value) if isinstance(value, str) else value)
    ]


def to_integer(value: Any) -> int:
    return int(value)


def to_float(value: Any) -> float:
    return float(value)


def to_date(value: Any) -> str | None:
    if isinstance(value, str):
        return datetime.datetime.fromisoformat(value).isoformat()
    elif isinstance(value, int | float):
        return datetime.datetime.fromtimestamp(value, tz=datetime.UTC).isoformat()
    return None


def to_dict(value: Any) -> dict:
    return dict(value)


_DtypeConvertingMap = MappingProxyType(
    {
        "string": to_string,
        "string[]": to_string_array,
        "integer": to_integer,
        "float": to_float,
        "date": to_date,
        "dict": to_dict,
        "email": to_string,
        # TODO: Add email converter
    }
)


def convert_to_type(input_value: Any, dtype_desc: str) -> Any:
    if (converter := _DtypeConvertingMap.get(dtype_desc)) is None:
        raise ValueError(
            "Invalid dtype description. Must be one of: ",
            "string, string[], integer, float, date.",
            f"Got: {dtype_desc}",
        )
    return converter(input_value)


_OPERATOR_REGISTRY = MappingProxyType(
    {
        "DO_NOTHING": lambda value: value,
        "join_with_space": lambda value: ", ".join(
            ast.literal_eval(value) if isinstance(value, str) else value
        ),
        "evaluate": lambda value: ast.literal_eval(value),
        "filename": lambda value: os.path.basename(value),
        "dirname-2": lambda value: os.path.dirname(os.path.dirname(value)),
    }
)


def _get_operator(operator: str | None) -> Callable:
    return _OPERATOR_REGISTRY.get(operator or "DO_NOTHING", lambda _: _)


def _retrieve_as_string(
    h5file: h5py.File, path: str, *, encoding: str = "utf-8"
) -> str:
    return h5file[path][...].item().decode(encoding)


def _retrieve_values_from_file(
    variable_recipe: NexusFileMetadataVariable, h5file: h5py.File
) -> Any:
    if "*" in variable_recipe.path:  # Selectors are used
        path = variable_recipe.path.split("/")[1:]
        path[0] += "/"
        paths = extract_paths_from_h5_file(h5file, path)
        value = [_retrieve_as_string(h5file, p) for p in paths]
    else:
        value = _retrieve_as_string(h5file, variable_recipe.path)
    return value


def extract_variables_values(
    variables: dict[str, MetadataSchemaVariable],
    h5file: h5py.File,
    config: OfflineIngestorConfig,
) -> dict:
    variable_map = {
        "filepath": pathlib.Path(config.nexus_file),
        "now": datetime.datetime.now(tz=datetime.UTC).isoformat(),
    }
    for variable_name, variable_recipe in variables.items():
        source = variable_recipe.source
        if isinstance(variable_recipe, NexusFileMetadataVariable):
            value = _retrieve_values_from_file(variable_recipe, h5file)
        elif isinstance(variable_recipe, ScicatMetadataVariable):
            value = retrieve_value_from_scicat(
                config=config.scicat,
                scicat_endpoint_url=render_full_url(
                    render_variable_value(variable_recipe.url, variable_map),
                    config.scicat,
                ),
                field_name=variable_recipe.field,
            )
        elif isinstance(variable_recipe, ValueMetadataVariable):
            value = variable_recipe.value
            value = (
                render_variable_value(value, variable_map)
                if isinstance(value, str)
                else value
            )
            value = _get_operator(variable_recipe.operator)(value)
        else:
            raise Exception("Invalid variable source: ", source)
        variable_map[variable_name] = convert_to_type(value, variable_recipe.value_type)

    return variable_map


def extract_paths_from_h5_file(
    _h5_object: h5py.Group | h5py.File,
    _path: list[str],
) -> list[str]:
    master_key = _path.pop(0)
    output_paths = [master_key]
    if "*" in master_key:
        temp_keys = [k2 for k2 in _h5_object.keys() if re.search(master_key, k2)]
        for key in temp_keys:
            output_paths += [
                key + "/" + subkey
                for subkey in extract_paths_from_h5_file(
                    _h5_object[key], copy.deepcopy(_path)
                )
            ]
    else:
        if _path:
            output_paths = [
                master_key + "/" + subkey
                for subkey in extract_paths_from_h5_file(_h5_object[master_key], _path)
            ]

    return output_paths


@dataclass(kw_only=True)
class TechniqueDesc:
    pid: str
    "Technique PID"
    name: str
    "Technique Name"


@dataclass(kw_only=True)
class ScicatDataset:
    pid: str | None
    size: int
    numberOfFiles: int
    isPublished: bool = False
    datasetName: str
    description: str | None = None
    principalInvestigator: str
    creationLocation: str
    scientificMetadata: dict
    owner: str
    ownerEmail: str
    sourceFolder: str
    contactEmail: str
    creationTime: str
    type: str = "raw"
    sampleId: str | None = None
    techniques: list[TechniqueDesc] = field(default_factory=list)
    instrumentId: str | None = None
    proposalId: str | None = None
    ownerGroup: str | None = None
    accessGroups: list[str] | None = None


@dataclass(kw_only=True)
class DataFileListItem:
    path: str
    "Relative path of the file to the source folder."
    size: int | None = None
    "Size of the single file in bytes."
    time: str
    chk: str | None = None
    uid: str | None = None
    gid: str | None = None
    perm: str | None = None


@dataclass(kw_only=True)
class OrigDataBlockInstance:
    datasetId: str
    size: int
    chkAlg: str
    dataFileList: list[DataFileListItem]
    ownerGroup: str | None = None
    accessGroups: list[str] | None = None


def _calculate_checksum(file_path: pathlib.Path, algorithm_name: str) -> str | None:
    """Calculate the checksum of a file."""
    import hashlib

    if not file_path.exists():
        return None

    if algorithm_name != "blake2b":
        raise ValueError(
            "Only b2blake hash algorithm is supported for now. Got: ",
            f"{algorithm_name}",
        )

    chk = hashlib.new(algorithm_name, usedforsecurity=False)
    buffer = memoryview(bytearray(128 * 1024))
    with open(file_path, "rb", buffering=0) as file:
        for n in iter(lambda: file.readinto(buffer), 0):
            chk.update(buffer[:n])

    return chk.hexdigest()


def _create_single_data_file_list_item(
    *,
    file_path: pathlib.Path,
    compute_file_hash: bool,
    compute_file_stats: bool,
    file_hash_algorithm: str = "",
) -> DataFileListItem:
    """``DataFileListItem`` constructing helper."""

    file_info: dict[str, Any] = {
        "path": file_path.absolute().as_posix(),
        "time": datetime.datetime.now(tz=datetime.UTC).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        ),
    }
    if file_path.exists():
        if compute_file_stats:
            file_stats = file_path.stat()
            timestamp_str = datetime.datetime.fromtimestamp(
                file_stats.st_ctime, tz=datetime.UTC
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            file_info = {
                **file_info,
                **{
                    "size": file_stats.st_size,
                    "time": timestamp_str,
                    "uid": str(file_stats.st_uid),
                    "gid": str(file_stats.st_gid),
                    "perm": oct(file_stats.st_mode),
                },
            }

        if compute_file_hash:
            file_info["chk"] = _calculate_checksum(file_path, file_hash_algorithm)

    return DataFileListItem(**file_info)


def _build_hash_path(
    *,
    original_file_instance: DataFileListItem,
    dir_path: pathlib.Path,
    hash_file_extension: str,
) -> pathlib.Path:
    "Compose path to the hash file."
    file_stem = pathlib.Path(original_file_instance.path).stem
    return dir_path / pathlib.Path(".".join([file_stem, hash_file_extension]))


def _save_hash_file(
    *,
    original_file_instance: DataFileListItem,
    hash_path: pathlib.Path,
) -> None:
    """Save the hash of the ``original_file_instance``."""
    if original_file_instance.chk is None:
        raise ValueError("Checksum is not provided.")

    hash_path.write_text(original_file_instance.chk)


def create_data_file_list(
    *,
    nexus_file: pathlib.Path,
    done_writing_message_file: pathlib.Path | None = None,
    nexus_structure_file: pathlib.Path | None = None,
    ingestor_directory: pathlib.Path,
    config: FileHandlingOptions,
    source_folder: pathlib.Path | str | None = None,
    logger: logging.Logger,
) -> list[DataFileListItem]:
    """
    Create a list of ``DataFileListItem`` instances for the files provided.

    Params
    ------
    nexus_file:
        Path to the NeXus file.
    done_writing_message_file:
        Path to the "done writing" message file.
    nexus_structure_file:
        Path to the NeXus structure file.
    ingestor_directory:
        Path to the directory where the files will be saved.
    config:
        Configuration related to the file handling.
    logger:
        Logger instance.

    """
    from functools import partial

    single_file_constructor = partial(
        _create_single_data_file_list_item,
        file_hash_algorithm=config.file_hash_algorithm,
        compute_file_stats=config.compute_file_stats,
        compute_file_hash=config.compute_file_hash,
    )

    # Collect the files that will be ingested
    file_list = [nexus_file]
    if done_writing_message_file is not None:
        file_list.append(done_writing_message_file)
    if nexus_structure_file is not None:
        file_list.append(nexus_structure_file)

    # Create the list of the files
    data_file_list = []
    for minimum_file_path in file_list:
        logger.info("Adding file %s to the datafiles list", minimum_file_path)
        new_file_item = single_file_constructor(
            file_path=minimum_file_path,
        )
        data_file_list.append(new_file_item)
        if config.save_file_hash:
            logger.info(
                "Computing hash of the file(%s) from disk...", minimum_file_path
            )
            hash_file_path = _build_hash_path(
                original_file_instance=new_file_item,
                dir_path=ingestor_directory,
                hash_file_extension=config.hash_file_extension,
            )
            logger.info("Saving hash into a file ... %s", hash_file_path)
            _save_hash_file(
                original_file_instance=new_file_item, hash_path=hash_file_path
            )
            data_file_list.append(
                single_file_constructor(
                    file_path=hash_file_path, compute_file_hash=False
                )
            )
        if source_folder:
            for data_file in data_file_list:
                data_file.path = str(
                    pathlib.Path(data_file.path).relative_to(source_folder)
                )

    return data_file_list


def _filter_by_field_type(
    schemas: Iterable[MetadataItem], field_type: str
) -> list[MetadataItem]:
    return [field for field in schemas if field.field_type == field_type]


def _render_variable_as_type(value: str, variable_map: dict, dtype: str) -> Any:
    return convert_to_type(render_variable_value(value, variable_map), dtype)


def _create_scientific_metadata(
    *,
    metadata_schema_id: str,
    sm_schemas: list[MetadataItem],
    variable_map: dict,
) -> dict:
    """Create scientific metadata from the metadata schema configuration.

    Params
    ------
    metadata_schema_id:
        The ID of the metadata schema configuration.
    sm_schemas:
        The scientific metadata schema configuration.
    variable_map:
        The variable map to render the scientific metadata values.

    """
    return {
        # Default field
        "ingestor_metadata_schema_id": {
            "value": metadata_schema_id,
            "unit": "",
            "human_name": "Ingestor metadata schema ID",
            "type": "string",
        },
        **{
            field.machine_name: {
                "value": _render_variable_as_type(
                    field.value, variable_map, field.type
                ),
                "unit": getattr(field, "unit", ""),
                "human_name": getattr(field, "human_name", field.machine_name),
                "type": field.type,
            }
            for field in sm_schemas
        },
    }


def _validate_metadata_schemas(
    metadata_schema: dict[str, MetadataItem],
) -> None:
    invalid_types = [
        field.field_type
        for field in metadata_schema.values()
        if field.field_type not in VALID_METADATA_TYPES
    ]

    if any(invalid_types):
        raise ValueError(
            "Invalid metadata schema types found. Valid types are: ",
            VALID_METADATA_TYPES,
            "Got: ",
            invalid_types,
        )


def create_scicat_dataset_instance(
    *,
    metadata_schema_id: str,  # metadata-schema["id"]
    metadata_schema: dict[str, MetadataItem],  # metadata-schema["schema"]
    variable_map: dict,
    data_file_list: list[DataFileListItem],
    config: DatasetOptions,
    logger: logging.Logger,
) -> ScicatDataset:
    """
    Prepare the ``ScicatDataset`` instance.

    Params
    ------
    metadata_schema:
        Metadata schema.
    variables_values:
        Variables values.
    data_file_list:
        List of the data files.
    config:
        Configuration related to scicat dataset instance.
    logger:
        Logger instance.

    """
    _validate_metadata_schemas(metadata_schema)
    # Create the dataset instance
    scicat_dataset = ScicatDataset(
        size=sum([file.size for file in data_file_list if file.size is not None]),
        numberOfFiles=len(data_file_list),
        isPublished=False,
        scientificMetadata=_create_scientific_metadata(
            metadata_schema_id=metadata_schema_id,
            sm_schemas=_filter_by_field_type(
                metadata_schema.values(), SCIENTIFIC_METADATA_TYPE
            ),  # Scientific metadata schemas
            variable_map=variable_map,
        ),
        **{
            field.machine_name: _render_variable_as_type(
                field.value, variable_map, field.type
            )
            for field in _filter_by_field_type(
                metadata_schema.values(), HIGH_LEVEL_METADATA_TYPE
            )
            # High level schemas
        },
    )

    # Auto generate or assign default values if needed
    if not config.allow_dataset_pid and scicat_dataset.pid:
        logger.info("PID is not allowed in the dataset by configuration.")
        scicat_dataset.pid = None
    elif config.generate_dataset_pid:
        logger.info("Auto generating PID for the dataset based on the configuration.")
        scicat_dataset.pid = uuid.uuid4().hex
    if scicat_dataset.instrumentId is None:
        scicat_dataset.instrumentId = config.default_instrument_id
        logger.info(
            "Instrument ID is not provided. Setting to default value. %s",
            scicat_dataset.instrumentId,
        )
    if scicat_dataset.proposalId is None:
        scicat_dataset.proposalId = config.default_proposal_id
        logger.info(
            "Proposal ID is not provided. Setting to default value. %s",
            scicat_dataset.proposalId,
        )
    if scicat_dataset.ownerGroup is None:
        scicat_dataset.ownerGroup = config.default_owner_group
        logger.info(
            "Owner group is not provided. Setting to default value. %s",
            scicat_dataset.ownerGroup,
        )
    if scicat_dataset.accessGroups is None:
        scicat_dataset.accessGroups = config.default_access_groups
        logger.info(
            "Access group is not provided. Setting to default value. %s",
            scicat_dataset.accessGroups,
        )

    logger.info("Dataset instance is created successfully. %s", scicat_dataset)
    return scicat_dataset


def scicat_dataset_to_dict(dataset: ScicatDataset) -> dict:
    """
    Convert the ``dataset`` to a dictionary.

    It removes the ``None`` values from the dictionary.
    You can add more handlings for specific fields here if needed.

    Params
    ------
    dataset:
        Scicat dataset instance.

    """
    return {k: v for k, v in asdict(dataset).items() if v is not None}


def _define_dataset_source_folder(datafilelist: list[DataFileListItem]) -> pathlib.Path:
    """
    Return the dataset source folder, which is the common path
    between all the data files associated with the dataset
    """
    import os

    return pathlib.Path(os.path.commonpath([item.path for item in datafilelist]))


def _path_to_relative(
    datafilelist_item: DataFileListItem, dataset_source_folder: pathlib.Path
) -> DataFileListItem:
    """
    Copy the datafiles item and transform the path to the relative path
    to the dataset source folder
    """
    from copy import copy

    origdatablock_datafilelist_item = copy(datafilelist_item)
    origdatablock_datafilelist_item.path = (
        pathlib.Path(datafilelist_item.path)
        .relative_to(dataset_source_folder)
        .as_posix()
    )
    return origdatablock_datafilelist_item


def _prepare_origdatablock_datafilelist(
    datafiles_list: list[DataFileListItem], dataset_source_folder: pathlib.Path
) -> list[DataFileListItem]:
    """
    Prepare the datafiles list for the origdatablock entry in scicat
    That means that the file paths needs to be relative to the dataset source folder
    """
    return [_path_to_relative(item, dataset_source_folder) for item in datafiles_list]


def create_origdatablock_instance(
    data_file_list: list[DataFileListItem],
    scicat_dataset: dict,
    config: FileHandlingOptions,
) -> OrigDataBlockInstance:
    dataset_source_folder = _define_dataset_source_folder(data_file_list)
    origdatablock_datafiles_list = _prepare_origdatablock_datafilelist(
        data_file_list, dataset_source_folder
    )
    return OrigDataBlockInstance(
        datasetId=scicat_dataset["pid"],
        size=sum([item.size for item in data_file_list if item.size is not None]),
        chkAlg=config.file_hash_algorithm,
        dataFileList=origdatablock_datafiles_list,
        ownerGroup=scicat_dataset["ownerGroup"],
        accessGroups=scicat_dataset["accessGroups"],
    )


def origdatablock_to_dict(origdatablock: OrigDataBlockInstance) -> dict:
    """
    Convert the ``origdatablock`` to a dictionary.

    It removes the ``None`` values from the dictionary.
    You can add more handlings for specific fields here if needed.

    Params
    ------
    origdatablock:
        Origdatablock instance to be sent to scicat backend.

    """
    return {k: v for k, v in asdict(origdatablock).items() if v is not None}
