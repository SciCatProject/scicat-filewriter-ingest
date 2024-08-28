# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import pathlib

import h5py
from scicat_communication import create_scicat_dataset, create_scicat_origdatablock
from scicat_configuration import (
    build_offline_ingestor_arg_parser,
    build_scicat_offline_ingestor_config,
)
from scicat_dataset import (
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
from system_helpers import handle_exceptions


def main() -> None:
    """Main entry point of the app."""
    arg_parser = build_offline_ingestor_arg_parser()
    arg_namespace = arg_parser.parse_args()
    config = build_scicat_offline_ingestor_config(arg_namespace)
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
        nexus_file_path = pathlib.Path(config.offline_run.nexus_file)
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
        local_dataset = scicat_dataset_to_dict(
            create_scicat_dataset_instance(
                metadata_schema_id=metadata_schema["id"],
                metadata_schemas=metadata_schema["schemas"],
                variable_map=variable_map,
                data_file_list=data_file_list,
                config=config.dataset,
                logger=logger,
            )
        )
        logger.debug("Scicat dataset: %s", local_dataset)
        # Create dataset in scicat
        scicat_dataset = create_scicat_dataset(
            dataset=local_dataset, config=config.scicat, logger=logger
        )

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
