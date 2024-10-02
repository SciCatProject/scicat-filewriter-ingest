# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)

import logging
from pathlib import Path

import h5py
from scicat_communication import (
    check_dataset_by_metadata,
    check_dataset_by_pid,
    create_scicat_dataset,
    create_scicat_origdatablock,
)
from scicat_configuration import (
    IngestionOptions,
    OfflineIngestorConfig,
    SciCatOptions,
    build_arg_parser,
    build_dataclass,
    merge_config_and_input_args,
)
from scicat_dataset import (
    ScicatDataset,
    create_data_file_list,
    create_origdatablock_instance,
    create_scicat_dataset_instance,
    extract_variables_values,
    origdatablock_to_dict,
    scicat_dataset_to_dict,
)
from scicat_logging import build_logger
from scicat_metadata import collect_schemas, select_applicable_schema
from scicat_path_helpers import compose_ingestor_directory
from system_helpers import exit, handle_exceptions


def build_offline_config() -> OfflineIngestorConfig:
    arg_parser = build_arg_parser(
        OfflineIngestorConfig, mandatory_args=('--config-file',)
    )
    arg_namespace = arg_parser.parse_args()
    merged_configuration = merge_config_and_input_args(
        Path(arg_namespace.config_file), arg_namespace
    )
    # Remove unused fields
    # It is because ``OfflineIngestorConfig`` shares the template config file
    # with ``OnlineIngestorConfig``.
    del merged_configuration["kafka"]

    return build_dataclass(OfflineIngestorConfig, merged_configuration)


def _check_if_dataset_exists_by_pid(
    local_dataset: ScicatDataset,
    ingest_config: IngestionOptions,
    scicat_config: SciCatOptions,
    logger: logging.Logger,
) -> bool:
    """
    Check if a dataset with the same pid exists already in SciCat.
    """
    if ingest_config.check_if_dataset_exists_by_pid and (local_dataset.pid is not None):
        logger.info(
            "Checking if dataset with pid %s already exists.", local_dataset.pid
        )
        return check_dataset_by_pid(
            pid=local_dataset.pid, config=scicat_config, logger=logger
        )

    # Other cases, assuming dataset does not exist
    return False


def _check_if_dataset_exists_by_metadata(
    local_dataset: ScicatDataset,
    ingest_config: IngestionOptions,
    scicat_config: SciCatOptions,
    logger: logging.Logger,
):
    """
    Check if a dataset already exists in SciCat where
    the metadata key specified has the same value as the dataset that we want to create
    """
    if ingest_config.check_if_dataset_exists_by_metadata:
        metadata_key = ingest_config.check_if_dataset_exists_by_metadata_key
        target_metadata: dict = local_dataset.scientificMetadata.get(metadata_key, {})
        metadata_value = target_metadata.get("value")

        if metadata_value is not None:
            logger.info(
                "Checking if dataset with scientific metadata key %s "
                "set to value %s already exists.",
                metadata_key,
                metadata_value,
            )
            return check_dataset_by_metadata(
                metadata_key=metadata_key,
                metadata_value=metadata_value,
                config=scicat_config,
                logger=logger,
            )
        else:
            logger.info(
                "No value found for metadata key %s specified for checking dataset.",
                metadata_key,
            )
    else:
        logger.info("No metadata key specified for checking dataset existence.")

    # Other cases, assuming dataset does not exist
    return False


def main() -> None:
    """Main entry point of the app."""
    config = build_offline_config()
    fh_options = config.ingestion.file_handling
    logger = build_logger(config)

    # Log the configuration as dictionary so that it is easier to read from the logs
    logger.info(
        'Starting the Scicat background Ingestor with the following configuration: %s',
        config.to_dict(),
    )

    # Collect all metadata schema configurations
    schemas = collect_schemas(config.ingestion.schemas_directory)

    with handle_exceptions(logger):
        nexus_file_path = Path(config.nexus_file)
        logger.info("Nexus file to be ingested: %s", nexus_file_path)

        # Path to the directory where the ingestor saves the files it creates
        ingestor_directory = compose_ingestor_directory(fh_options, nexus_file_path)

        # open nexus file with h5py
        with h5py.File(nexus_file_path) as h5file:
            # load instrument metadata configuration
            metadata_schema = select_applicable_schema(nexus_file_path, h5file, schemas)

            # define variables values
            variable_map = extract_variables_values(
                metadata_schema['variables'], h5file, config.scicat
            )

        # Collect data-file descriptions
        data_file_list = create_data_file_list(
            nexus_file=nexus_file_path,
            ingestor_directory=ingestor_directory,
            config=fh_options,
            logger=logger,
            # TODO: add done_writing_message_file and nexus_structure_file
        )

        # Prepare scicat dataset instance(entry)
        logger.info("Preparing scicat dataset instance ...")
        local_dataset_instance = create_scicat_dataset_instance(
            metadata_schema_id=metadata_schema["id"],
            metadata_schemas=metadata_schema["schemas"],
            variable_map=variable_map,
            data_file_list=data_file_list,
            config=config.dataset,
            logger=logger,
        )
        # Check if dataset already exists in SciCat
        if _check_if_dataset_exists_by_pid(
            local_dataset_instance, config.ingestion, config.scicat, logger
        ) or _check_if_dataset_exists_by_metadata(
            local_dataset_instance, config.ingestion, config.scicat, logger
        ):
            logger.warning(
                "Dataset with pid %s already present in SciCat. Skipping it!!!",
                local_dataset_instance.pid,
            )
            exit(logger, unexpected=False)

        # If dataset does not exist, continue with the creation of the dataset
        local_dataset = scicat_dataset_to_dict(local_dataset_instance)
        logger.debug("Scicat dataset: %s", local_dataset)

        # Prepare origdatablock
        logger.info("Preparing scicat origdatablock instance ...")
        local_origdatablock = origdatablock_to_dict(
            create_origdatablock_instance(
                data_file_list=data_file_list,
                scicat_dataset=local_dataset,
                config=fh_options,
            )
        )
        logger.debug("Scicat origdatablock: %s", local_origdatablock)

        # Create dataset in scicat
        if config.ingestion.dry_run:
            logger.info(
                "Dry run mode. Skipping Scicat API calls for creating dataset ..."
            )
            exit(logger, unexpected=False)
        else:
            scicat_dataset = create_scicat_dataset(
                dataset=local_dataset, config=config.scicat, logger=logger
            )

            # create origdatablock in scicat
            scicat_origdatablock = create_scicat_origdatablock(
                origdatablock=local_origdatablock, config=config.scicat, logger=logger
            )

            # check one more time if we successfully created the entries in scicat
            if not ((len(scicat_dataset) > 0) and (len(scicat_origdatablock) > 0)):
                logger.error(
                    "Failed to create dataset or origdatablock in scicat.\n"
                    "SciCat dataset: %s\nSciCat origdatablock: %s",
                    scicat_dataset,
                    scicat_origdatablock,
                )
                raise RuntimeError("Failed to create dataset or origdatablock.")

            # check one more time if we successfully created the entries in scicat
            exit(
                logger,
                unexpected=not (bool(scicat_dataset) and bool(scicat_origdatablock)),
            )
