# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
# import scippnexus as snx
import copy
import datetime
import hashlib
import json
import logging
import pathlib
import uuid
from urllib.parse import urljoin, quote
import os

import h5py
import pytz
import requests
from scicat_configuration import (
    OfflineIngestorConfig,
    build_offline_ingestor_arg_parser,
    build_scicat_offline_ingestor_config,
)
from scicat_dataset import (
    convert_to_type,
)
from scicat_logging import build_logger
from scicat_metadata import collect_schemas, select_applicable_schema
from src.scicat_path_helpers import compose_ingestor_directory, compose_ingestor_output_file_path
from system_helpers import offline_ingestor_exit_at_exceptions, exit


def replace_variables_values(url: str, values: dict) -> str:
    for key, value in values.items():
        url = url.replace("{" + key + "}", str(value))
    return url


def extract_variables_values(
    variables: dict, h5file, config: OfflineIngestorConfig
) -> dict:
    values = {}

    # loop on all the variables defined
    for variable in variables.keys():
        source = variables[variable]["source"]
        value = ""
        if source == "NXS":
            # extract value from nexus file
            # we need to address path entry/user_*/name
            value = h5file[variables[variable]["path"]][...]
        elif source == "SC":
            # build url
            url = replace_variables_values(
                config[""]["scicat_url"] + variables[variable]["url"], values
            )
            # retrieve value from SciCat
            response = requests.get(
                url,
                headers={"token": config[""]["token"]},
                timeout=10,  # TODO: decide timeout. Maybe from configuration?
            )
            # extract value
            value = response.json()[variables[variable]["field"]]
        elif source == "VALUE":
            # the value is the one indicated
            # there might be some substitution needed
            value = replace_variables_values(variables[variable]["value"], values)
            if (
                "operator" in variables[variable].keys()
                and variables[variable]["operator"]
            ):
                operator = variables[variable]["operator"]
                if operator == "join_with_space":
                    value = ", ".join(value)
        else:
            raise Exception("Invalid variable source configuration")

        values[variable] = convert_to_type(value, variables[variable]["value_type"])

    return values

def _new_hash(algorithm: str) -> Any:
    try:
        return hashlib.new(algorithm, usedforsecurity=False)
    except TypeError:
        # Fallback for Python < 3.9
        return hashlib.new(algorithm)


def _compute_file_checksum(file_full_path: pathlib.Path, algorithm: str) -> str:
    """
    Compute the checksum of a file using specified algorithm.
    :param file_full_path:
    :param algorithm:
    :return:
    """
    chk = _new_hash(algorithm)
    buffer = memoryview(bytearray(128 * 1024))
    with file_full_path.open("rb", buffering=0) as file:
        for n in iter(lambda: file.readinto(buffer), 0):
            chk.update(buffer[:n])
    return chk.hexdigest()  # type: ignore[no-any-return]


def _create_datafilelist_item(
        file_full_path: pathlib.Path,
        config,
        logger
):
    """
    Create the matching entry in the datafiles list for the file provided
    :param file_full_path:
    :param config:
    :param logger:
    :return:
    """
    logger.info("create_datafilelist_item: adding file {}".format(file_full_path))

    datafilelist_item = {
        "path": file_full_path,
        "size": 0,
        "time": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }

    if config.ingestion.compute_files_stats and file_full_path.exists():
        logger.info("create_datafilelist_item: reading file stats from disk")
        stats = file_full_path.stat()
        datafiles_item = {
            **datafilelist_item,
            **{
                "size": stats.st_size,
                "time": datetime.datetime.fromtimestamp(stats.st_ctime, tz=pytz.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "uid": stats.st_uid,
                "gid": stats.st_gid,
                "perm": stats.st_mode,
            }
        }

    return datafilelist_item

def _compute_file_checksum_if_needed(
        file_full_path: pathlib.Path,
        ingestor_directory: pathlib.Path,
        config,
        logger
):
    checksum = ""
    datafiles_item = {}

    if config.ingestion.compute_files_hash and os.path.exists(file_full_path):
        logger.info("create_datafiles_entry: computing hash of the file from disk")
        checksum = _compute_file_checksum(file_full_path, config.ingestion.file_hash_algorithm)

        if config.ingstion.save_hash_in_file:

            # file path for hash file
            hash_file_full_path = compose_ingestor_output_file_path(
                ingestor_directory,
                file_full_path.stem,
                config.ingestion.hash_file_extension)
            logger.info("create_datafiles_entry: saving hash in file {}".format(hash_file_full_path))

            # save hash in file
            with hash_file_full_path.open('w') as fh:
                fh.write(datafiles_item['chk'])

            datafiles_item = _create_datafilelist_item(hash_file_full_path,config,logger)

    return checksum, datafiles_item


def _create_datafiles_list(
        nexus_file_path: pathlib.Path,
        done_writing_message_file_path: pathlib.Path,
        ingestor_directory: pathlib.Path,
        config,
        logger
) -> list:
    """
    Update the file size and creation time according to the configuration
    :param nexus_file_path:
    :param done_writing_message_file_path,
    :param config,
    :param logger
    :return:
    """

    logger.info("create_datafiles_list: adding nexus file {}".format(nexus_file_path))
    datafiles_list = [
        _create_datafilelist_item(nexus_file_path, config, logger)
    ]
    checksum, datafiles_hash_item = _compute_file_checksum_if_needed(
        nexus_file_path,
        ingestor_directory,
        config,
        logger)
    if checksum:
        datafiles_list[0]['chk'] = checksum
    if datafiles_hash_item:
        datafiles_list.append(datafiles_hash_item)

    if config.ingestion.file_handling.message_to_file:
        logger.info("create_datafiles_list: adding done writing message file {}".format(done_writing_message_file_path))
        datafiles_list.append(
            _create_datafilelist_item(done_writing_message_file_path, config, logger)
        )
        checksum, datafiles_hash_item = _compute_file_checksum_if_needed(
            nexus_file_path,
            ingestor_directory,
            config,
            logger)
        if checksum:
            datafiles_list[-1]['chk'] = checksum
        if datafiles_hash_item:
            datafiles_list.append(datafiles_hash_item)

    return datafiles_list

def _prepare_scicat_dataset(
        metadata_schema: dict,
        values: dict,
        datafilelist: list[dict],
        config,
        logger
):
    """
    Prepare scicat dataset as dictionary ready to be ``POST``ed.
    """
    logger.info("_prepare_scicat_dataset: Preparing scicat dataset structure")
    schema: dict = metadata_schema["schema"]
    dataset: dict = {}

    scientific_metadata = {
        'ingestor_metadata_schema_id': {
            "value": metadata_schema["id"],
            "unit": "",
            "human_name": "Ingestor Metadata Schema Id",
            "type": "string",
        }
    }
    for field in schema.values():
        machine_name = field["machine_name"]
        field_type = field["type"]
        if field["field_type"] == "high_level":
            dataset[machine_name] = convert_to_type(
                replace_variables_values(field["value"], values), field_type
            )
        elif field["field_type"] == "scientific_metadata":
            scientific_metadata[machine_name] = {
                "value": convert_to_type(
                    replace_variables_values(field["value"], values), field_type
                ),
                "unit": "",
                "human_name": field["human_name"]
                if field.get("human_name", None)
                else machine_name,
                "type": field_type,
            }
        else:
            raise Exception("Metadata schema field type invalid")

    dataset["scientific_metadata"] = scientific_metadata

    # now check that the configuration setting shave been respected
    if not config.dataset.allow_dataset_pid and "pid" in dataset.keys():
        logger.info("_prepare_scicat_dataset: Pid not allowed by configuration")
        del dataset["pid"]
    if config.dataset.generate_dataset_pid:
        logger.info("_prepare_scicat_dataset: Auto generating pid by configuration")
        dataset["pid"] = str(uuid.uuid4())

    if "instrumentId" not in dataset.keys() or not dataset["instrumentId"]:
        logger.info("_prepare_scicat_dataset: Assigning default instrument id: {}".format(config.dataset.default_instrument_id))
        dataset["instrumentId"] = config.dataset.default_instrument_id

    if "proposalId" not in dataset.keys() or not dataset["proposalId"]:
        logger.info("_prepare_scicat_dataset: Assigning default proposal id: {}".format(config.dataset.default_proposal_id))
        dataset["proposalId"] = config.dataset.default_proposal_id

    if "ownerGroup" not in dataset.keys() or not dataset["ownerGroup"]:
        logger.info("_prepare_scicat_dataset: Assigning default ownerGroup: {}".format(config.dataset.default_owner_group))
        dataset["ownerGroup"] = config.dataset.default_owner_group

    if "accessGroups" not in dataset.keys() or not dataset["accessGroups"]:
        logger.info("_prepare_scicat_dataset: Assigning default accessGroups: {}".format(json.dumps(config.dataset.default_access_groups)))
        dataset["accessGroups"] = config.dataset.default_access_groups

    dataset["size"] = len(datafilelist)
    dataset["numberOfFiles"] = sum([item["size"] for item in datafilelist])
    dataset["isPublished"] = False

    logger.info("_prepare_scicat_dataset: Scicat dataset: {}".format(json.dumps(dataset)))
    return dataset


def _create_scicat_dataset(
        dataset: dict,
        config,
        logger: logging.Logger
) -> dict:
    """
    Execute a POST request to scicat to create a dataset
    """
    logger.info("_create_scicat_dataset: Sending POST request to create new dataset")
    response = requests.request(
        method="POST",
        url=urljoin(config.scicat.host, "datasets"),
        json=dataset,
        headers=config.scicat.headers,
        timeout=config.scicat.timeout,
        stream=False,
        verify=True,
    )

    result = response.json()
    if not response.ok:
        err = result.get("error", {})
        logger.info(f"_create_scicat_dataset: Failed to create new dataset. Error {err}")
        raise Exception(f"Error creating new dataset: {err}")

    logger.info("_create_scicat_dataset: Dataset created successfully. Dataset pid: %s", result['pid'])
    return result


def _prepare_scicat_origdatablock(
        scicat_dataset,
        datafilelist,
        config,
        logger
):
    """
    Create local copy of the orig datablock to send to scicat
    """
    logger.info("_prepare_scicat_origdatablock: Preparing scicat origdatablock structure")
    origdatablock = {
        "ownerGroup": scicat_dataset["ownerGroup"],
        "accessGroups": scicat_dataset["accessGroups"],
        "size": sum([item["size"] for item in datafilelist]),
        "chkAlg": config.ingestion.file_hash_algorithm,
        "dataFileList": datafilelist,
        "datasetId": scicat_dataset["pid"],
    }

    logger.info("_prepare_scicat_origdatablock: Scicat origdatablock: {}".format(json.dumps(origdatablock)))
    return origdatablock


def _create_scicat_origdatablock(
        origdatablock: dict,
        config,
        logger: logging.Logger
) -> dict:
    """
    Execute a POST request to scicat to create a new origdatablock
    """
    logger.info("_create_scicat_origdatablock: Sending POST request to create new origdatablock")
    response = requests.request(
        method="POST",
        url=urljoin(config.scicat.host, "origdatablocks"),
        json=origdatablock,
        headers=config.scicat.headers,
        timeout=config.scicat.timeout,
        stream=False,
        verify=True,
    )

    result = response.json()
    if not response.ok:
        err = result.get("error", {})
        logger.info(f"_create_scicat_origdatablock: Failed to create new origdatablock. Error {err}")
        raise Exception(f"Error creating new origdatablock: {err}")

    logger.info("_create_scicat_origdatablock: Origdatablock created successfully. Origdatablock pid: %s", result['_id'])
    return result


def _define_dataset_source_folder(
    datafilelist
) -> pathlib.Path:
    """
    Return the dataset source folder, which is the common path between all the data files associated with the dataset
    """
    return pathlib.Path( os.path.commonpath( [item["path"] for item in datafilelist]))


def _path_to_relative(
        datafilelist_item: dict,
        dataset_source_folder: pathlib.Path
) -> dict:
    """
    Copy the datafiles item and transform the path to the relative path to the dataset source folder
    """
    origdatablock_datafilelist_item = copy.deepcopy(datafilelist_item)
    origdatablock_datafilelist_item["path"] = str(datafilelist_item["path"].to_relative(dataset_source_folder))
    return origdatablock_datafilelist_item


def _prepare_origdatablock_datafilelist(
        datafiles_list: list,
        dataset_source_folder: pathlib.Path
) -> list:
    """
    Prepare the datafiles list for the origdatablock entry in scicat
    That means that the file paths needs to be relative to the dataset source folder
    """
    return [_path_to_relative(item,dataset_source_folder) for item in datafiles_list]


def _check_if_dataset_exists_by_pid(
        local_dataset,
        config,
        logger
) -> bool :
    """
    Check if a dataset with the same pid exists already in SciCat.
    """
    dataset_exists = False
    if config.ingestion.check_if_dataset_exists_by_pid:
        if "pid" in local_dataset.keys() and local_dataset["pid"]:
            logger.info("_check_if_dataset_exists: Checking if dataset with pid {} already exists.".format(local_dataset["pid"]))

            response = requests.request(
                method="GET",
                url=urljoin(config.scicat.host, "datasets/{}".format(quote(local_dataset["pid"]))),
                headers=config.scicat.headers,
                timeout=config.scicat.timeout,
                stream=config.scicat.stream,
                verify=config.scicatverify,
            )

            if not response.ok:
                logger.info("Dataset by job id error. status : {} {}".format(response.status_code, response.reason))
            else:
                result = response.json()
                if result:
                    logger.info("Retrieved Dataset with pid {} from SciCat".format(result["pid"]))
                    dataset_exists = True
        else:
            logger.info("_check_if_dataset_exists: Dataset has no pid associated. Assuming new dataset")

    return dataset_exists


def _check_if_dataset_exists_by_metadata(local_dataset, config, logger):
    """
    Check if a dataset already exists in SciCat where
    the metadata key specified has the same value as the dataset that we want to create
    """
    dataset_exists = False
    if config.ingestion.check_if_dataset_exists_by_metadata:
        metadata_key = config.ingestion.check_if_dataset_exists_by_metadata_key

        if metadata_key in local_dataset["scientificMetadata"].keys() and local_dataset["scientificMetadata"][metadata_key]["value"]:
            metadata_value = local_dataset["scientificMetadata"][metadata_key]["value"]
            logger.info("_check_if_dataset_exists_by_metadata: Checking if dataset with scientific metadata key {} "
                        "set to value {} already exists.".format(metadata_key, metadata_value))

            url = "{}?filter={{\"where\":{}}}".format(
                urljoin(config.scicat.host, "datasets"),
                json.dumps({"scientificMetadata.{}.value".format(metadata_key): metadata_value})
            )
            logger.info("_check_if_dataset_exists_by_metadata: Url : {}".format(url))

            response = requests.request(
                method="GET",
                url=url,
                headers=config.scicat.headers,
                timeout=config.scicat.timeout,
                stream=config.scicat.stream,
                verify=config.scicatverify,
            )

            if not response.ok:
                logger.info("_check_if_dataset_exists_by_metadata: Error. status : {} {}".format(response.status_code, response.reason))
            else:
                results = response.json()
                if results:
                    logger.info("_check_if_dataset_exists_by_metadata: Retrieved {} Dataset from SciCat".format(len(results)))
                    dataset_exists = True
        else:
            logger.info("_check_if_dataset_exists: Dataset has no pid associated. Assuming new dataset")

    return dataset_exists


def main() -> None:
    """Main entry point of the app."""
    arg_parser = build_offline_ingestor_arg_parser()
    arg_namespace = arg_parser.parse_args()
    config = build_scicat_offline_ingestor_config(arg_namespace)
    ingestion_options = config.ingestion
    file_handling_options = ingestion_options.file_handling
    logger = build_logger(config)

    # Log the configuration as dictionary so that it is easier to read from the logs
    logger.info(
        'Starting the Scicat background Ingestor with the following configuration:'
    )
    logger.info(config.to_dict())

    # Collect all metadata schema configurations
    schemas = collect_schemas(ingestion_options.schemas_directory)

    with offline_ingestor_exit_at_exceptions(logger):
        nexus_file_path = pathlib.Path(config.offline_run.nexus_file)
        logger.info(
            "Nexus file to be ingested : %s",
            nexus_file_path,
        )
        done_writing_message_file_path = pathlib.Path()
        if config.ingestion.file_handling.message_to_file:
            done_writing_message_file_path = pathlib.Path(
                config.offline_run.done_writing_message_file)
            logger.info(
                "Done writing message file linked to nexus file : %s",
                done_writing_message_file_path
            )

            # log done writing message input file
            logger.info(json.load(done_writing_message_file_path.open()))

        # define which is the directory where the ingestor should save the files it creates, if any is created
        ingestor_directory = compose_ingestor_directory(
            config.ingestion.file_handling,
            nexus_file_path
        )

        # open nexus file with h5py
        with h5py.File(nexus_file_path) as h5file:
            # load instrument metadata configuration
            metadata_schema = select_applicable_schema(nexus_file_path, h5file, schemas)

            # define variables values
            variables_values = extract_variables_values(
                metadata_schema['variables'], h5file, config
            )

        # =============================================
        # I'm not sure that using jinja templates is the right thing to do
        # =============================================
        # # Collect data-file descriptions
        # data_file_list = [
        #     build_single_data_file_desc(nexus_file_path, file_handling_options),
        #     build_single_data_file_desc(
        #         done_writing_message_file, file_handling_options
        #     ),
        #     # TODO: Add nexus structure file
        # ]
        # # Create hash of all the files if needed
        # if file_handling_options.save_file_hash:
        #     data_file_list += [
        #         save_and_build_single_hash_file_desc(
        #             data_file_dict, file_handling_options
        #         )
        #         for data_file_dict in data_file_list
        #     ]
        # # Collect all data-files and hash-files descriptions
        # _ = [json.dumps(file_dict, indent=2) for file_dict in data_file_list]

        # create datafilelist
        datafilelist = _create_datafiles_list(
            nexus_file_path,
            done_writing_message_file_path,
            ingestor_directory,
            config,
            logger
        )

        dataset_source_folder = _define_dataset_source_folder(
            datafilelist
        )

        origdatablock_datafiles_list = _prepare_origdatablock_datafilelist(
            datafilelist,
            dataset_source_folder
        )

        # create and populate scicat dataset entry
        local_dataset = _prepare_scicat_dataset(
            metadata_schema,
            variables_values,
            datafilelist,
            config,
            logger
        )

        dataset_already_present = (
            _check_if_dataset_exists_by_pid(local_dataset, config, logger) or
            _check_if_dataset_exists_by_metadata(local_dataset, config, logger)
        )

        if (dataset_already_present):
            logger.info("Dataset with pid {} already present in SciCat. Skipping it!!!".format(local_dataset["pid"]))
        else:
            if (not config.ingestion.dry_run):
                # create dataset in scicat
                scicat_dataset = _create_scicat_dataset(
                    local_dataset,
                    config,
                    logger
                )
            else:
                logger.info("This is a dry run. No request is sent to SciCat and no dataset is created in SciCat")

            # create and populate scicat origdatablock entry
            # with files and hashes previously computed
            local_origdatablock = _prepare_scicat_origdatablock(
                scicat_dataset,
                origdatablock_datafiles_list,
                config,
                logger
            )

            if (not config.ingestion.dry_run):
                # create origdatablock in scicat
                scicat_origdatablock = _create_scicat_origdatablock(
                    local_origdatablock,
                    config,
                    logger
                )
            else:
                logger.info("This is a dry run. No request is sent to SciCat and no origdatablock is created in SciCat")


        # check one more time if we successfully created the entries in scicat
        exit(logger, unexpected=not(bool(scicat_dataset) and bool(scicat_origdatablock)))
