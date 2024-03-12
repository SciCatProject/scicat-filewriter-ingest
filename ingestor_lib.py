#!/usr/bin/env python3
#
#

import argparse
import copy
import hashlib
import json
import logging.handlers
import os
import re
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import pyscicat.client as pyScClient
import pyscicat.model as pyScModel
import pytz
import requests
from streaming_data_types import deserialise_wrdn

from user_office_lib import UserOffice

METADATA_PROPOSAL_PATH = [
    "children",
    ("children", "name", "entry"),
    ("config", "module", "dataset"),
    (None, "name", "experiment_identifier", "values"),
]

METADATA_TITLE_PATH = [
    "children",
    ("children", "name", "entry"),
    ("config", "module", "dataset"),
    (None, "name", "title", "values"),
]


def get_instrument(scClient, iid, name, logger):
    # load instrument by id or by name
    logger.info("ingestor_lib.get_instrument Id: {}, Name: {}".format(iid, name))
    instrument = scClient.instruments_get_one(iid, name)
    if not instrument:
        instrument = {'id': None, "name": "unknown"}

    return instrument


def get_nested_value(structure: dict, path: list, logger: logging.Logger):
    # logger.debug("get_nested_value ======================")
    # get key
    key = path[0]
    remaining_path = path[1:]
    # logger.debug("get_nested_value key : {}".format(key))
    # logger.debug("get_nested_value structure : {}".format(structure))
    if not isinstance(structure, dict):
        # logger.debug("get_nested_value structure is not a dictionary")
        return None
    elif isinstance(key, str):
        # logger.debug("get_nested_value key is a string")
        if key in structure.keys():
            substructure = structure[key]
            # logger.debug("get_nested_value substructure : {}".format(substructure))
            if isinstance(substructure, list):
                for i in substructure:
                    # logger.debug("get_nested_value structure[key] : {}".format(i))
                    temp = get_nested_value(i, remaining_path, logger)
                    if temp is not None:
                        return temp
            elif isinstance(substructure, dict):
                return get_nested_value(substructure, remaining_path, logger)
            else:
                return substructure
    elif isinstance(key, tuple):
        logger.debug("get_nested_value key is a tuple")
        # check the condition
        if key[0] is not None:
            if (key[1] in structure.keys()) and (structure[key[1]] == key[2]):
                substructure = structure[key[0]]
                if isinstance(substructure, list):
                    for i in substructure:
                        temp = get_nested_value(i, remaining_path, logger)
                        if temp is not None:
                            return temp
                else:
                    return get_nested_value(substructure, remaining_path, logger)
        else:
            if (key[1] in structure.keys()) and (structure[key[1]] == key[2]):
                return structure[key[3]]
    else:
        raise (Exception("Invalid path"))
    return None


def get_nested_value_with_default(
    structure: dict, path: list, default: Any, logger: logging.Logger
):
    try:
        output = get_nested_value(structure, path, logger)
        # logger.debug("get_nested_value_with_default output : {}".format(output))
        return output if output and output is not None else default
    except Exception:
        return default


def get_nested_value_with_union(
    structure: dict, path: list, union: list, logger: logging.Logger
):
    try:
        output = get_nested_value(structure, path, logger)
        output = output if isinstance(output, list) else [output]
        return [i for i in list({*output, *union}) if i is not None]
    except Exception:
        return union


def get_proposal_id(
    logger, hdf_structure_dict: dict, default: str = "", proposal_path: list = None
) -> str:
    # extract proposal id from hdf_structure field
    # if such field does not exist, it uses the default

    try:
        # check if we are using the default path or
        # the user has provided an alternative one
        if proposal_path is None:
            proposal_path = METADATA_PROPOSAL_PATH
        #            proposal_path = [
        #                "children",
        #                ("children", "name", "entry"),
        #                ("config", "module","dataset"),
        #                (None,"name","experiment_identifier","values")
        #            ]
        logger.debug("Proposal path : " + json.dumps(proposal_path))

        # Finds the proposal id which is saved under the key experiment_identifier
        proposal_id = get_nested_value(hdf_structure_dict, proposal_path, logger)
        logger.debug("Result : " + proposal_id)

        return proposal_id

    except Exception:
        return default


def instantiate_user_office_client(config, logger):
    # instantiate connector to user office
    # retrieve relevant configuration
    user_office_config = config["user_office"]
    logger.info('Instantiating User Office client')
    logger.info('User Office instance : {}'.format(user_office_config['host']))
    logger.info('User Office token : {}'.format(user_office_config['token']))
    uoClient = UserOffice(user_office_config["host"])
    uoClient.set_access_token(user_office_config["token"])
    return uoClient


def instantiate_scicat_client(config, logger):
    # instantiate connector to scicat
    # retrieve relevant configuration
    scicat_config = config["scicat"]
    # instantiate a pySciCat client
    logger.info('Instantiating SciCat client')
    logger.info('SciCat instance : {}'.format(scicat_config['host']))
    logger.info('SciCat token : {}'.format(scicat_config['token']))
    scClient = pyScClient.ScicatClient(
        base_url=scicat_config['host'],
        token=scicat_config["token"],
    )
    return scClient


def get_defaults(config, scClient, uoClient, logger):
    defaultOwnerGroup = config['dataset']['ownable']['ownerGroup']
    logger.info('Default owner group : {}'.format(defaultOwnerGroup))

    defaultAccessGroups = config['dataset']['ownable']['accessGroups']
    logger.info('Default access groups : {}'.format(defaultAccessGroups))

    defaultInstrumentId = get_nested_value_with_default(
        config, ["dataset", "instrument_id"], None, logger
    )
    logger.info('Default instrument id : {}'.format(defaultInstrumentId))
    defaultInstrumentName = get_nested_value_with_default(
        config, ["dataset", "instrument_name"], None, logger
    )
    logger.info('Default instrument name: {}'.format(defaultInstrumentName))

    defaultInstrument = get_instrument(
        scClient, defaultInstrumentId, defaultInstrumentName, logger
    )
    logger.info('Default instrument : {}'.format(defaultInstrument))

    defaultProposal = uoClient.proposals_get_one(
        config['dataset']['default_proposal_id'], logger
    )
    # defaultProposal['proposer']['email'] = uoClient.users_get_one_email(
    #     defaultProposal['proposer']['id']
    # )
    logger.info("Default proposal : {}".format(defaultProposal))

    return (
        defaultOwnerGroup,
        defaultAccessGroups,
        defaultInstrumentId,
        defaultInstrumentName,
        defaultInstrument,
        defaultProposal,
    )


def ingest_message(
    message_value,
    defaultAccessGroups,
    defaultProposal,
    defaultInstrument,
    scClient,
    ouClient,
    config,
    logger,
):
    logger.info("Starting message ingestion")
    entry = deserialise_wrdn(message_value)
    if entry.error_encountered:
        logger.error("Unable to de-serialize message")
        return

    logger.info(str(entry)[0:5000])

    # extract file name information from message
    # full_file_name = get_nested_value_with_default(
    #     metadata,["file_being_written"],"unknown",logger
    # )
    full_file_name = entry.file_name
    logger.info("Full file name : {}".format(full_file_name))
    file_name = os.path.basename(full_file_name)
    path_name = os.path.dirname(full_file_name)
    logger.info('Dataset folder : {}'.format(path_name))
    logger.info('Dataset raw data file : {}'.format(file_name))
    # create path for files saved by the ingestor
    ingestor_files_path = (
        os.path.join(
            os.path.dirname(path_name), config["run_options"]["ingestor_files_folder"]
        )
        if config["run_options"]["hdf_structure_output"] == "SOURCE_FOLDER"
        else os.path.abspath(config["run_options"]["files_output_folder"])
    )
    logger.info("Ingestor files folder: {}".format(ingestor_files_path))
    fix_dataset_source_folder = False

    # list of files to be added to the dataset
    files_list = []
    if config["run_options"]["message_to_file"]:
        message_file_path = ingestor_files_path
        logger.info("message file will be saved in {}".format(message_file_path))
        if os.path.exists(message_file_path):
            message_file_name = (
                os.path.splitext(file_name)[0]
                + config["run_options"]["message_file_extension"]
            )
            logger.info("message file name : " + message_file_name)
            message_full_file_path = os.path.join(message_file_path, message_file_name)
            logger.info("message full file path : " + message_full_file_path)
            with open(message_full_file_path, 'w') as fh:
                json.dump(entry, fh)
            logger.info("message saved to file")
            if config["run_options"]["message_output"] == "SOURCE_FOLDER":
                files_list += [
                    {
                        "path": message_full_file_path,
                        "size": len(json.dumps(entry)),
                    }
                ]
            fix_dataset_source_folder = True
        else:
            logger.info("Message file path not accessible")

    if entry.metadata is not None:
        metadata = json.loads(entry.metadata)
        logger.info(
            "Extracted metadata. Extracted {} keys".format(len(metadata.keys()))
        )

        # check if dataset has already been created using job id
        logger.info("Run options")
        logger.info(config["run_options"])
        if (
            config["run_options"]["check_by_job_id"]
            and not config["run_options"]["dry_run"]
        ):
            logger.info("Checking job id")
            job_id = get_nested_value_with_default(metadata, ['job_id'], None, logger)
            logger.info("Job id : {}".format(job_id))
            logger.info("scClient base url : {}".format(scClient._base_url))
            if job_id:
                dataset = get_dataset_by_job_id(scClient, job_id, config, logger)
                if dataset:
                    logger.info(
                        "Dataset with job id {} already present in catalogue".format(
                            job_id
                        )
                    )
                    logger.info("Dataset id : {}".format(dataset[0]['pid']))
                    return

        # find run number
        run_number = file_name.split(".")[0].split("_")[1]
        metadata["run_number"] = int(run_number)
        logger.info("Run number : {}".format(run_number))

        # convert json string to dictionary
        hdf_structure_string = metadata["hdf_structure"].replace("\n", "")
        logger.info("hdf_structure : {}".format(hdf_structure_string[:500]))
        hdf_structure_dict = json.loads(hdf_structure_string)
        if not config['run_options']['hdf_structure_in_metadata']:
            del metadata["hdf_structure"]
            logger.info("Removed hdf structure dict from metadata")
        else:
            logger.debug("hdf structure dict : " + json.dumps(hdf_structure_dict))
        if config["run_options"]["hdf_structure_to_file"]:
            hdf_structure_file_path = ingestor_files_path
            logger.info(
                "hdf structure file will be saved in {}".format(hdf_structure_file_path)
            )
            if os.path.exists(hdf_structure_file_path):
                hdf_structure_file_name = os.path.join(
                    hdf_structure_file_path,
                    os.path.splitext(file_name)[0]
                    + config["run_options"]["hdf_structure_file_extension"],
                )
                logger.info("hdf structure file name : " + hdf_structure_file_name)
                with open(hdf_structure_file_name, 'w') as fh:
                    json.dump(hdf_structure_dict, fh)
                logger.info("hdf structure saved to file : " + hdf_structure_file_name)
                if config["run_options"]["hdf_structure_output"] == "SOURCE_FOLDER":
                    files_list += [
                        {
                            "path": hdf_structure_file_name,
                            "size": len(json.dumps(hdf_structure_dict)),
                        }
                    ]
                fix_dataset_source_folder = True
            else:
                logger.info("hdf structure file path not accessible")

        # set dataset source folder and fix source folder if needed
        dataset_source_folder = (
            os.path.dirname(path_name) if fix_dataset_source_folder else path_name
        )

        # retrieve proposal id, if present
        proposal_id = None
        if "proposal_id" in metadata.keys() and metadata['proposal_id'] is not None:
            logger.info("Extracting proposal id from metadata")
            proposal_id = metadata['proposal_id']
        if not proposal_id or proposal_id is None:
            logger.info("Extracting proposal id from hdf structure")
            proposal_id = get_proposal_id(logger, hdf_structure_dict)
        proposal_id = (
            str(proposal_id)
            if not isinstance(proposal_id, str) and proposal_id is not None
            else proposal_id
        )
        logger.info("Proposal id found: {}".format(proposal_id))
        if not proposal_id or proposal_id is None:
            logger.info("Using default proposal")
            proposal = defaultProposal
        else:
            try:
                proposal = ouClient.proposals_get_one(proposal_id, logger)
            except Exception as e:
                logger.error("Error retrieving proposal")
                logger.error("Error : " + e)
                proposal = defaultProposal

        logger.info("Proposal id : {}".format(proposal_id))
        logger.info("Proposal : {}".format(proposal))
        if proposal_id != get_prop(proposal, 'proposalId', 'unknown'):
            logger.error(
                "Error: Proposal retrieved from UserOffice "
                "does not match Proposal indicated in message"
            )

        # if instrument is not assigned by config, tries to find it from the message
        logger.info('Defining Instrument')
        instrument = None
        # currently extract instrument name from file name
        # waiting for ECDC to see if it is possible to include it in the hdf structure
        instrument_id = None
        instrument_name = None
        if config['run_options']['retrieve_instrument_from'].lower() == 'path':
            instrument_name = file_name.split('/')[
                config['run_options']['instrument_position_in_file_path']
            ]
        elif (
            config['run_options']['retrieve_instrument_from'].lower() == 'proposal'
            and proposal['instrument']
            and proposal['instrument']['name']
        ):
            instrument_name = proposal['instrument']['name'].lower()
        logger.info("Instrument id : {}".format(instrument_id))
        logger.info("Instrument name : {}".format(instrument_name))
        #
        # the following two lines should be delete, but for the time been we keep them
        # instrument_id = get_nested_value_with_default(
        #     metadata, ['instrument_id'], None, logger
        # )
        # instrument_name = get_nested_value_with_default(
        #     metadata, ['instrument_name'], None, logger
        # )
        if instrument_id or instrument_name:
            instrument = get_instrument(
                scClient, instrument_id, instrument_name.lower(), logger
            )
        if instrument is None:
            instrument = defaultInstrument
        logger.info('Instrument : {}'.format(instrument))

        # create an ownable object to be used with all the other models
        # all the fields are retrieved directly from the simulation information
        logger.info('Instantiate ownable model')
        # we set the owner group to the proposal id
        ownerGroup = proposal_id
        logger.info('Owner group : {}'.format(ownerGroup))
        accessGroups = get_nested_value_with_union(
            proposal,
            ['accessGroups'],
            defaultAccessGroups + [instrument['name']] if instrument else [],
            logger,
        )
        logger.info('Access groups : {}'.format(accessGroups))

        ownable = pyScModel.Ownable(ownerGroup=ownerGroup, accessGroups=accessGroups)

        # find sample information
        sample_id = None
        if "sample_id" in metadata.keys() and metadata["sample_id"]:
            sample_id = metadata['sample_id']
        elif 'simple_id' in config['dataset'].keys() and config['dataset']['sample_id']:
            sample_id = config['dataset']['sample_id']
        sample = scClient.samples_get_one(sample_id) if sample_id else None
        logger.info('Sample : {}'.format(sample))

        # extract estimated file size from message
        file_size = 10**6 * get_nested_value_with_default(
            metadata, ['extra', ":approx_file_size_mb"], 0, logger
        )
        logger.info('Estimated file size : {}'.format(file_size))
        # add data file
        files_list += [
            {
                "path": full_file_name,
                "size": file_size,
            }
        ]

        # dataset title
        dataset_title = get_nested_value_with_default(
            hdf_structure_dict, METADATA_TITLE_PATH, None, logger
        )
        logger.info('Dataset name from message : {}'.format(dataset_title))

        # create dataset object from the pyscicat model
        # includes ownable from previous step
        logger.info('Instantiating dataset model')
        dataset = create_dataset(
            logger,
            config,
            metadata,
            proposal,
            instrument,
            sample,
            ownable,
            proposal_id,
            dataset_source_folder,
            dataset_title,
            job_id,
        )
        # logger.info('Dataset : {}'.format(dataset))
        logger.info(
            'Dataset : {}'.format(
                json.dumps(dataset.dict(exclude_unset=True, exclude_none=True))
            )
        )
        logger.info('Creating dataset on SciCat')
        if not config['run_options']['dry_run']:
            created_dataset = scClient.datasets_create(dataset)
            logger.info('Dataset created with pid {}'.format(created_dataset['pid']))
        else:
            created_dataset = copy.deepcopy(dict(dataset))
            logger.info(
                'Dry Run. Dataset not created. Arbitrary pid {} assigned'.format(
                    created_dataset['pid']
                )
            )
            logger.info('Dry Run. Dataset in json format => {}'.format(created_dataset))

        # create origdatablock object from pyscicat model
        logger.info('Instantiating original datablock')
        origDatablock = create_orig_datablock(
            logger,
            created_dataset["pid"],
            files_list,
            ownable,
            config,
            dataset_source_folder,
            ingestor_files_path,
        )
        # logger.info('Original datablock : {}'.format(origDatablock))
        logger.info(
            'Original datablock : {}'.format(
                json.dumps(origDatablock.dict(exclude_unset=True, exclude_none=True))
            )
        )
        # create origDatablock associated with dataset in SciCat
        # it returns the full object including SciCat id assigned when created
        logger.info('Creating original datablock in SciCat')
        if not config['run_options']['dry_run']:
            created_orig_datablock = scClient.datasets_origdatablock_create(
                origDatablock
            )
            logger.info(
                'Original datablock created with internal id {}'.format(
                    created_orig_datablock['id']
                )
            )
        else:
            logger.info('Dry Run. Original datablock not created')
            logger.info(
                'Dry Run. Original datablock in json format => {}'.format(
                    dict(origDatablock)
                )
            )

    else:
        logger.info("No metadata in this message")
        logger.info("Ignoring message")


def get_config(input_args: argparse.Namespace) -> dict:
    config_file = (
        input_args.config_file if input_args.config_file else "config.20230125.json"
    )

    with open(config_file, "r") as fh:
        data = fh.read()
        config = json.loads(data)

    # copy options into run options
    config['run_options'] = copy.deepcopy(config['options'])

    for k, v in vars(input_args).items():
        if v is not None:
            config['run_options'][k] = v

    # define log level
    # config['logging_level'] = getattr(logging,config['run_options']['debug_level'])

    return config


def get_prop(input_object: dict, field: str, default: any = "") -> any:
    try:
        output = input_object.get(field, default)
    except Exception:
        output = default
    return output


def create_dataset(
    logger,
    config,
    metadata: dict,
    proposal: dict,
    instrument: dict,
    sample: dict,
    ownable: pyScModel.Ownable,
    proposal_id: str = None,
    source_folder: str = "",
    dataset_name: str = None,
    job_id: str = "unknown",
) -> dict:
    # extract settings from configuration
    dataset_pid_prefix = config['run_options']['dataset_pid_prefix']
    force_dataset_pid = config['run_options']['force_dataset_pid']
    use_job_id_as_dataset = config['run_options']['use_job_id_as_dataset']
    # prepare info for datasets
    dataset_pid = job_id if use_job_id_as_dataset else str(uuid.uuid4())
    if dataset_pid_prefix:
        dataset_pid = dataset_pid_prefix + "/" + dataset_pid
    proposal_id = (
        proposal_id if proposal_id else get_prop(proposal, 'proposalId', 'unknown')
    )
    run_number = get_nested_value_with_default(
        metadata, ['run_number'], 'unknown', logger
    )
    if not dataset_name or dataset_name is None:
        dataset_name = (
            metadata["run_name"]
            if "run_name" in metadata.keys()
            else "Dataset {} for proposal {} run {}".format(
                dataset_pid, proposal_id, run_number
            )
        )
    dataset_description = (
        metadata["run_description"]
        if "run_description" in metadata.keys()
        else "Dataset: {}. Proposal: {}. Sample: {}. "
        "Instrument: {}. File: {}. Job: {}".format(
            dataset_pid,
            proposal_id,
            get_prop(instrument, 'name', 'unknown'),
            get_prop(sample, 'sampleId', 'unknown'),
            get_nested_value_with_default(
                metadata, ['file_being_written'], 'unknown', logger
            ),
            job_id,
        )
    )
    principal_investigator = " ".join(
        [
            get_nested_value_with_default(
                proposal, ["proposer", "firstname"], "unknown", logger
            ),
            get_nested_value_with_default(
                proposal, ["proposer", "lastname"], "", logger
            ),
        ]
    ).strip()
    email = get_nested_value_with_default(
        proposal, ["proposer", "email"], "unknown", logger
    )
    instrument_name = get_prop(instrument, "name", "unknown")
    source_folder = (
        instrument_name + "/" + proposal_id if not source_folder else source_folder
    )

    dataset = {
        "datasetName": dataset_name,
        "description": dataset_description,
        "principalInvestigator": principal_investigator,
        "creationLocation": get_prop(instrument, "name", ""),
        "scientificMetadata": prepare_flatten_metadata(config, metadata),
        "owner": principal_investigator,
        "ownerEmail": email,
        "contactEmail": email,
        "sourceFolder": source_folder,
        "creationTime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "type": "raw",
        "techniques": get_prop(metadata, 'techniques', []),
        "instrumentId": get_prop(instrument, "pid", ""),
        "sampleId": get_prop(sample, 'sampleId', ''),
        "proposalId": proposal_id,
    }

    if force_dataset_pid:
        dataset["pid"] = dataset_pid

    # create dictionary with all requested info
    return pyScModel.RawDataset(**dataset, **dict(ownable))


#
# def flatten_metadata(inMetadata,inPrefix=""):
#     outMetadata={}
#
#     for k,v in inMetadata.items():
#         outPrefix = ' '.join([i for i in [inPrefix, k] if i])
#         nk = re.sub('_/|/:|/|:',"_",outPrefix)
#         if isinstance(v,dict):
#             outMetadata = {**outMetadata,**flatten_metadata(v,outPrefix)}
#         else:
#             outMetadata[nk] = v
#
#     return outMetadata
#
#
#
# def prepare_metadata(inMetadata):
#     outMetadata = {}
#
#     for k,v in inMetadata.items():
#         outMetadata[k] = {
#             'value' : v if isinstance(v,str) or isinstance(v,int) \
#                            or isinstance(v,float) else str(v),
#             'unit' : ''
#         }
#     return outMetadata


#
# add option to substitute characters in paths or not
# HERE
def prepare_flatten_metadata(config, inMetadata, inPrefix=""):
    outMetadata = {}

    for k, v in inMetadata.items():
        key_path = config['run_options']['metadata_levels_separator'].join(
            [i for i in [inPrefix, k] if i]
        )
        nk = (
            nk  # noqa: F821 TODO: investigate this line
            if config['run_options']['beautify_metadata_keys']
            else re.sub(' /|_/|/:|/|:', "_", key_path)
        )
        if isinstance(v, dict):
            outMetadata = {
                **outMetadata,
                **prepare_flatten_metadata(config, v, key_path),
            }
        else:
            outMetadata[nk] = {
                'value': v
                if isinstance(v, str) or isinstance(v, int) or isinstance(v, float)
                else str(v),
                'path': key_path,
                'unit': '',
            }

    return outMetadata


def _new_hash(algorithm: str) -> Any:
    try:
        return hashlib.new(algorithm, usedforsecurity=False)
    except TypeError:
        # Fallback for Python < 3.9
        return hashlib.new(algorithm)


def checksum_of_file(path: str, algorithm: str) -> str:
    """Compute the checksum of a local file.

    Parameters
    ----------
    path:
        Path of the file on the local filesystem.
    algorithm:
        Hash algorithm to use. Can be any algorithm supported by :func:`hashlib.new`.

    Returns
    -------
    :
        The hex digest of the hash.
    """
    chk = _new_hash(algorithm)
    buffer = memoryview(bytearray(128 * 1024))
    with open(path, "rb", buffering=0) as file:
        for n in iter(lambda: file.readinto(buffer), 0):
            chk.update(buffer[:n])
    return chk.hexdigest()  # type: ignore[no-any-return]


def update_file_info(logger, config: dict, source_folder: str, file_item: dict):
    """
    Update the file size and creation time according to the configuration
    :param file_item:
    :param check_file_stats:
    :return:
    """
    logger.info("update_file_info: info for file {}".format(file_item["path"]))
    file_path = file_item["path"].replace(source_folder, "")
    if file_path.startswith("/"):
        file_path = file_path[1:]
    logger.info("update_file_info: file path for scicat : {}".format(file_path))

    output_item = {"path": file_path}

    if config['run_options']['compute_files_stats'] and os.path.exists(
        file_item["path"]
    ):
        stats = os.stat(file_item["path"])
        output_item = {
            **output_item,
            **{
                "size": stats.st_size,
                "time": datetime.fromtimestamp(stats.st_ctime, tz=pytz.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z"
                ),
                "uid": stats.st_uid,
                "gid": stats.st_gid,
                "perm": stats.st_mode,
            },
        }
    else:
        output_item = {
            **output_item,
            **{
                "size": file_item["size"],
                "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            },
        }

    if config['run_options']['compute_files_hash'] and os.path.exists(
        file_item["path"]
    ):
        output_item["chk"] = checksum_of_file(
            file_item["path"], config['run_options']['file_hash_algorithm']
        )

    logger.info("Output item : {}".format(json.dumps(output_item)))
    return output_item


def save_hash_in_file(
    logger, config: dict, source_folder: str, files_list: list, ingestor_files_path: str
) -> list:
    """
    Save the hashes computed for the files in files along with the data files
    :param config:
    :param files_list:
    :return:
    """
    logger.info(
        "save_hash_in_file: Ingestor files path: {}".format(ingestor_files_path)
    )
    hash_files = []
    if (
        config['run_options']['compute_files_hash']
        and config['run_options']['save_hash_in_file']
    ):
        logger.info("save_hash_in_file: source folder: {}".format(source_folder))
        for data_file in files_list:
            # file path for hash file
            hash_file_full_path = os.path.join(
                ingestor_files_path,
                os.path.basename(data_file["path"])
                + "."
                + config['run_options']['hash_file_extension'],
            )
            hash_file_name = hash_file_full_path.replace(source_folder, "")[1:]
            logger.info(
                "save_hash_in_file: Hash file full path : {}".format(
                    hash_file_full_path
                )
            )
            logger.info(
                "save_hash_in_file: Hash file name in scicat : {}".format(
                    hash_file_name
                )
            )

            # save hash in file
            with open(hash_file_full_path, 'w') as fh:
                fh.write(data_file['chk'])

            # stats on the file
            stats = os.stat(hash_file_full_path)

            # add hash file in dataset files
            hash_files.append(
                {
                    "path": hash_file_name,
                    "size": stats.st_size,
                    "time": datetime.fromtimestamp(
                        stats.st_ctime, tz=pytz.utc
                    ).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "uid": stats.st_uid,
                    "gid": stats.st_gid,
                    "perm": stats.st_mode,
                }
            )
            logger.info(
                "hash_file_in_file: Hash file entry : {}".format(
                    json.dumps(hash_files[-1])
                )
            )

    return [*files_list, *hash_files]


def create_orig_datablock(
    logger,
    dataset_pid: str,
    input_files: list,
    ownable: pyScModel.Ownable,
    config: dict,
    source_folder: str,
    ingestor_files_path: str,
) -> dict:
    #
    # TO-DO:
    # check file size and creation time
    # update info
    logger.info("create_orig_datablock: Checking file size and creation")
    ready_files = [
        update_file_info(logger, config, source_folder, i) for i in input_files
    ]

    # add hash files
    logger.info("create_orig_datablock: Saving hash in file")
    logger.info(
        "create_orig_datablock: Ingestor files path: {}".format(ingestor_files_path)
    )
    ready_files = save_hash_in_file(
        logger, config, source_folder, ready_files, ingestor_files_path
    )

    return pyScModel.OrigDatablock(
        **{
            "id": str(uuid.uuid4()),
            "size": sum([i["size"] for i in ready_files]),
            "chkAlg": config['run_options']['file_hash_algorithm'],
            "datasetId": dataset_pid,
            "dataFileList": ready_files,
        },
        **dict(ownable),
    )


def get_dataset_by_job_id(scClient, job_id, config, logger) -> list:
    logger.info("scClient base url : {}".format(scClient._base_url))
    url = "{}?filter={{\"where\":{}}}&access_token={}".format(
        urljoin(scClient._base_url, 'Datasets'),
        json.dumps({"scientificMetadata.job_id.value": job_id}),
        scClient._token,
    )
    logger.info("Dataset by job id. url : {}".format(url))

    # https://staging.scicat.ess.eu/api/v3/Datasets?filter=%7B%22where%22%3A+%7B%22scientificMetadata.job_id.value%22%3A+%2212aac4ec-92ba-11ed-81fb-fa163e943f63%22%7D%7D
    # https://staging.scicat.ess.eu/api/v3/Datasets?filter=%7B%22where%22%3A%7B%22scientificMetadata.job_id.value%22%3A%2212aac4ec-92ba-11ed-81fb-fa163e943f63%22%7D%7D&access_token=AMOSyF2K3Iev7xu6eJe62RDAOMvnt3IQ6r2Z7SYMJtJlO7wqwvAI6DsM9xvf9UNA

    response = requests.request(
        method="get",
        url=url,
        headers={
            'Accept': 'application/json',
            'Authorization': 'Bearer {}'.format(scClient._token),
        },
        timeout=scClient._timeout_seconds,
        stream=False,
        verify=True,
    )
    logger.info(response)
    logger.info(response.url)
    if not response.ok:
        logger.info(
            "Dataset by job id error. status : {} {}".format(
                response.status_code, response.reason
            )
        )
        return []

    logger.info(response.text)
    results = response.json()
    logger.info("Retrieved {} Datasets with job id {}".format(len(results), job_id))
    return results
