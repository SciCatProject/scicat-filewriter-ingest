#!/usr/bin/env python3
#
# 

import copy
from datetime import datetime
import json
from typing import Any
import uuid
import re
import os
import argparse
import logging.handlers
from urllib.parse import urljoin,urlencode

import requests

from user_office_lib import UserOffice

from streaming_data_types import deserialise_wrdn
import pyscicat.client as pyScClient
import pyscicat.model as pyScModel

METADATA_PROPOSAL_PATH = [
    "children",
    ("children", "name", "entry"),
    ("config", "module", "dataset"),
    (None, "name", "experiment_identifier", "values")
]

METADATA_TITLE_PATH = [
    "children",
    ("children", "name", "entry"),
    ("config", "module", "dataset"),
    (None, "name", "title", "values")
]


def get_instrument(scClient, iid, name):
    # load instrument by id or by name
    instrument = scClient.instruments_get_one(iid, name)
    if not instrument:
        instrument = {'id': None, "name": "unknown"}

    return instrument


def get_nested_value(structure: dict, path: list, logger: logging.Logger):
    #logger.debug("get_nested_value ======================")
    # get key
    key = path[0]
    remaining_path = path[1:]
    #logger.debug("get_nested_value key : {}".format(key))
    #logger.debug("get_nested_value structure : {}".format(structure))
    if not isinstance(structure, dict):
        #logger.debug("get_nested_value structure is not a dictionary")
        return None
    elif isinstance(key, str):
        #logger.debug("get_nested_value key is a string")
        if key in structure.keys():
            substructure = structure[key]
            #logger.debug("get_nested_value substructure : {}".format(substructure))
            if isinstance(substructure, list):
                for i in substructure:
                    #logger.debug("get_nested_value structure[key] : {}".format(i))
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
                if isinstance(substructure,list):
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
        raise(Exception("Invalid path"))
    return None


def get_nested_value_with_default(structure: dict, path: list, default: Any, logger: logging.Logger):
    try:
        output = get_nested_value(structure, path, logger)
        #logger.debug("get_nested_value_with_default output : {}".format(output))
        return output if output and output is not None else default
    except Exception as e:
        return default


def get_nested_value_with_union(structure: dict, path: list, union: list, logger: logging.Logger):
    try:
        output = get_nested_value(structure,path, logger)
        output = output if isinstance(output, list) else [output]
        return [i for i in list({*output, *union}) if i is not None]
    except:
        return union


def get_proposal_id(
    logger,
    hdf_structure_dict: dict,
    default: str = "", 
    proposal_path: list = None
) -> str:
    # extract proposal id from hdf_structure field
    # if such field does not exist, it uses the default

    try:

        # check if we are using the default path or the user has provided an alternative one
        if proposal_path is None:
            proposal_path = METADATA_PROPOSAL_PATH
#            proposal_path = [
#                "children",
#                ("children", "name", "entry"),
#                ("config", "module","dataset"),
#                (None,"name","experiment_identifier","values")
#            ]
        logger.debug("Proposal path : " + json.dumps(proposal_path))

        # now it finds the proposal id which is saved under the key experiment_identifier
        proposal_id = get_nested_value(
            hdf_structure_dict,
            proposal_path,
            logger
        )
        logger.debug("Result : " + proposal_id)

        return proposal_id

    except:
        return default


def instantiate_user_office_client(config,logger):
    # instantiate connector to user office
    # retrieve relevant configuration
    user_office_config = config["user_office"]
    uoClient = UserOffice(user_office_config["host"])
    uoClient.set_access_token(user_office_config["token"])
    return uoClient

def instantiate_scicat_client(config,logger):
    # instantiate connector to scicat
    # retrieve relevant configuration
    scicat_config = config["scicat"]
    # instantiate a pySciCat client
    logger.info('Instantiating SciCat client')
    logger.info('SciCat instance : {}'.format(scicat_config['host']))
    logger.info('Login as user : {}'.format(scicat_config['username']))
    scClient = pyScClient.ScicatClient(
        base_url=scicat_config['host'],
        username=scicat_config["username"],
        password=scicat_config["password"],
    )
    return scClient

def get_defaults(config, scClient, uoClient, logger):

    defaultOwnerGroup = config['dataset']['ownable']['ownerGroup']
    logger.info('Default owner group : {}'.format(defaultOwnerGroup))

    defaultAccessGroups = config['dataset']['ownable']['accessGroups']
    logger.info('Default access groups : {}'.format(defaultAccessGroups))

    defaultInstrumentId = get_nested_value_with_default(
        config,
        ["dataset","instrument_id"],
        None,
        logger
    )
    logger.info('Default instrument id : {}'.format(defaultInstrumentId))
    defaultInstrumentName = get_nested_value_with_default(
        config,
        ["dataset","instrument_name"],
        None,
        logger
    )
    logger.info('Default instrument name: {}'.format(defaultInstrumentName))
    
    defaultInstrument = get_instrument(
        scClient,
        defaultInstrumentId,
        defaultInstrumentName
    )
    logger.info('Default instrument : {}'.format(defaultInstrument))

    defaultProposal = uoClient.proposals_get_one(config['dataset']['default_proposal_id'])
    defaultProposal['proposer']['email'] = uoClient.users_get_one_email(defaultProposal['proposer']['id'])
    logger.info("Default proposal : {}".format(defaultProposal))

    return \
        defaultOwnerGroup, \
        defaultAccessGroups, \
        defaultInstrumentId, \
        defaultInstrumentName, \
        defaultInstrument, \
        defaultProposal


def ingest_message(
    message_value,
    defaultAccessGroups,
    defaultProposal,
    defaultInstrument,
    scClient,
    ouClient,
    config,
    logger
):
    logger.info("Starting message ingestion")
    entry = deserialise_wrdn(message_value)
    if entry.error_encountered:
        logger.error("Unable to de-serialize message")
        return

    logger.info(entry)
    if entry.metadata is not None:
        metadata = json.loads(entry.metadata)
        logger.info("Extracted metadata. Extracted {} keys".format(len(metadata.keys())))

        # check if dataset has already been created using job id
        logger.info("Run options")
        logger.info(config["run_options"])
        if config["run_options"]["check_by_job_id"] and not config["run_options"]["dry_run"]:
            logger.info("Checking job id")
            job_id = get_nested_value_with_default(metadata, ['job_id'], None, logger)
            logger.info("Job id : {}".format(job_id))
            logger.info("scClient base url : {}".format(scClient._base_url))
            if job_id:
                dataset = get_dataset_by_job_id(scClient,job_id,config,logger)
                if dataset:
                    logger.info("Dataset with job id {} already present in catalogue".format(job_id))
                    logger.info("Dataset id : {}".format(dataset[0]['pid']))
                    return

        # find run number
        file_name = get_nested_value_with_default(metadata,["file_being_written"],"unknown",logger)
        run_number = file_name.split(".")[0].split("_")[1]
        metadata["run_number"] = int(run_number)

        # convert json string to dictionary
        hdf_structure_dict = json.loads(
            metadata["hdf_structure"].replace("\n", "")
        )
        if not config['run_options']['hdf_structure_in_metadata']:
            del metadata["hdf_structure"]
            logger.info("Removed hdf structure dict from metadata")
        else:
            logger.debug("hdf structure dict : " + json.dumps(hdf_structure_dict))

        # retrieve proposal id, if present
        proposal_id = None
        if "proposal_id" in metadata.keys() and metadata['proposal_id'] is not None:
            logger.info("Extracting proposal id from metadata")
            proposal_id = metadata['proposal_id']
        if not proposal_id or proposal_id is None:
            logger.info("Extracting proposal id from hdf structure")
            proposal_id = get_proposal_id(
                logger,
                hdf_structure_dict,
                None
            )
        proposal_id = str(proposal_id) if not isinstance(proposal_id,str) and proposal_id is not None else proposal_id
        logger.info("Proposal id found: {}".format(proposal_id))
        if not proposal_id or proposal_id is None:
            logger.info("Using default proposal")
            proposal = defaultProposal
        else:
            try:
                proposal = ouClient.proposals_get_one(proposal_id)
            except Exception as e:
                logger.error("Error retrieving proposal")
                logger.error("Error : ", e)
                proposal = defaultProposal

        logger.info("Proposal id : {}".format(proposal_id))
        logger.info("Proposal : {}".format(proposal))
        if proposal_id != get_prop(proposal,'proposalId','unknown'):
            logger.error("Error: Proposal retrieved from UserOffice does not match Proposal indicated in message")

        # if instrument is not assigned by config, tries to find it from the message
        logger.info('Defining Instrument')
        instrument = None
        # currently extract instrument name from file name
        # waiting for ECDC to see if it is possible to include it in the hdf structure
        instrument_id = None
        instrument_name = file_name.split('/')[3]
        #
        # the following two lines should be delete, but for the time been we keep them
        #instrument_id = get_nested_value_with_default(metadata, ['instrument_id'], None, logger)
        #instrument_name = get_nested_value_with_default(metadata, ['instrument_name'], None, logger)
        if instrument_id or instrument_name:
            instrument = get_instrument(
                scClient,
                instrument_id,
                instrument_name
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
            logger
        )
        logger.info('Access groups : {}'.format(accessGroups))

        ownable = pyScModel.Ownable(
            ownerGroup=ownerGroup,
            accessGroups=accessGroups
        )

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
            metadata,
            ['extra',":approx_file_size_mb"],
            0,
            logger
        )
        logger.info('Estimated file size : {}'.format(file_size))

        # extract file information from message
        file_name = os.path.basename(entry.file_name)
        path_name = os.path.dirname(entry.file_name)
        logger.info('Dataset folder : {}'.format(path_name))
        logger.info('Dataset raw data file : {}'.format(file_name))

        # dataset title
        dataset_title = get_nested_value_with_default(
            hdf_structure_dict,
            METADATA_TITLE_PATH,
            None,
            logger
        )
        logger.info('Dataset name from message : {}'.format(dataset_title))

        # create dataset object from the pyscicat model
        # includes ownable from previous step
        logger.info('Instantiating dataset model')
        dataset = create_dataset(
            logger,
            metadata,
            proposal,
            instrument,
            sample,
            ownable,
            proposal_id,
            path_name,
            dataset_title
        )
        logger.info('Dataset : {}'.format(dataset))
        logger.info('Creating dataset on SciCat')
        if ( not config['run_options']['dry_run'] ):
            created_dataset = scClient.datasets_create(dataset)
            logger.info('Dataset created with pid {}'.format(created_dataset['pid']))
        else:
            created_dataset = copy.deepcopy(dict(dataset))
            logger.info('Dry Run. Dataset not created. Arbitrary pid {} assigned'.format(created_dataset['pid']))
            logger.info('Dry Run. Dataset in json format => {}'.format(created_dataset))

        # create origdatablock object from pyscicat model
        logger.info('Instantiating original datablock')
        origDatablock = create_orig_datablock(
            created_dataset["pid"],
            file_size,
            file_name,
            ownable
        )
        logger.info('Original datablock : {}'.format(origDatablock))
        # create origDatablock associated with dataset in SciCat
        # it returns the full object including SciCat id assigned when created
        logger.info('Creating original datablock in SciCat')
        if (not config['run_options']['dry_run']):
            created_orig_datablock = scClient.datasets_origdatablock_create(origDatablock)
            logger.info('Original datablock created with internal id {}'.format(created_orig_datablock['id']))
        else:
            logger.info('Dry Run. Original datablock not created')
            logger.info('Dry Run. Original datablock in json format => {}'.format(dict(origDatablock)))


    else:
         logger.info("No metadata in this message")
         logger.info("Ignoring message")



def get_config(input_args: argparse.Namespace) -> dict:

    config_file = input_args.config_file if input_args.config_file else "config.20230125.json"

    with open(config_file, "r") as fh:
        data = fh.read()
        config = json.loads(data)

    # copy options into run options
    config['run_options'] = copy.deepcopy(config['options'])

    for k,v in vars(input_args).items():
        if v is not None:
            config['run_options'][k] = v

    ## define log level
    #config['logging_level'] = getattr(logging,config['run_options']['debug_level'])

    return config


def get_prop(
    input_object: dict,
    field: str,
    default: any = ""
) -> any:
    try:
       output = input_object.get(field,default)
    except:
       output = default
    return output


def create_dataset(
    logger,
    metadata: dict, 
    proposal: dict, 
    instrument: dict, 
    sample: dict,
    ownable: pyScModel.Ownable,
    proposal_id: str = None,
    source_folder: str = "",
    dataset_name: str = None
) -> dict:
    # prepare info for datasets
    dataset_pid = str(uuid.uuid4())
    proposal_id = proposal_id if proposal_id else get_prop(proposal,'proposalId','unknown')
    run_number = get_nested_value_with_default(metadata,['run_number'],'unknown',logger)
    if not dataset_name or dataset_name is None:
        dataset_name = metadata["run_name"] \
            if "run_name" in metadata.keys() \
            else "Dataset {} for proposal {} run {}".format(dataset_pid,proposal_id,run_number)
    dataset_description = metadata["run_description"] \
        if "run_description" in metadata.keys() \
        else "Dataset: {}. Proposal: {}. Sample: {}. Instrument: {}. File: {}".format(
            dataset_pid,
            proposal_id,
            get_prop(instrument,'pid','unknown'),
            get_prop(sample,'sampleId','unknown'),
            get_nested_value_with_default(metadata,['file_being_written'],'unknown',logger))
    principal_investigator = " ".join([
        get_nested_value_with_default(proposal,["proposer", "firstname"],"unknown",logger),
        get_nested_value_with_default(proposal,["proposer", "lastname"],"",logger)
    ]).strip()
    email = get_nested_value_with_default(proposal,["proposer", "email"],"unknown",logger)
    instrument_name = get_prop(instrument,"name","unknown")
    source_folder = instrument_name + "/" + proposal_id if not source_folder else source_folder
    
    # create dictionary with all requested info
    return pyScModel.RawDataset(
        **{
            "pid" : dataset_pid,
            "datasetName": dataset_name,
            "description": dataset_description,
            "principalInvestigator": principal_investigator,
            "creationLocation": get_prop(instrument,"name",""),
            "scientificMetadata": prepare_metadata(flatten_metadata(metadata)),
            "owner": principal_investigator,
            "ownerEmail": email,
            "contactEmail": email,
            "sourceFolder": source_folder,
            "creationTime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "type": "raw",
            "techniques": get_prop(metadata,'techniques',[]),
            "instrumentId": get_prop(instrument,"pid",""),
            "sampleId" : get_prop(sample,'sampleId',''),
            "proposalId": proposal_id,
        },
        **dict(ownable)
    )


def flatten_metadata(inMetadata,prefix=""):
    outMetadata={}

    for k,v in inMetadata.items():
        nk = '_'.join([i for i in [prefix,k] if i])
        nk = re.sub('_/|/:|/|:',"_",nk)
        if isinstance(v,dict):
            outMetadata = {**outMetadata,**flatten_metadata(v,nk)}
        else:
            outMetadata[nk] = v

    return outMetadata



def prepare_metadata(inMetadata):
    outMetadata = {}

    for k,v in inMetadata.items():
        outMetadata[k] = {
            'value' : v if isinstance(v,str) or isinstance(v,int) or isinstance(v,float) else str(v),
            'unit' : ''
        }
    return outMetadata


def create_orig_datablock(
    dataset_pid: str, 
    file_size: int, 
    file_name: str,
    ownable: pyScModel.Ownable
) -> dict:
    return pyScModel.OrigDatablock(
        **{
            "id" : str(uuid.uuid4()),
            "size": file_size,
            "datasetId": dataset_pid,
            "dataFileList": [
                {
                    "path": file_name,
                    "size": file_size,
                    "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                }
            ],
        },
        **dict(ownable)
    )


def get_dataset_by_job_id(
    scClient,
    job_id,
    config,
    logger
) -> list:
    logger.info("scClient base url : {}".format(scClient._base_url))
    url = "{}?filter={{\"where\":{}}}&access_token={}".format(
        urljoin(scClient._base_url,'Datasets'),
        json.dumps({"scientificMetadata.job_id.value" : job_id}),
        scClient._token
    )
    logger.info("Dataset by job id. url : {}".format(url))

    # https://staging.scicat.ess.eu/api/v3/Datasets?filter=%7B%22where%22%3A+%7B%22scientificMetadata.job_id.value%22%3A+%2212aac4ec-92ba-11ed-81fb-fa163e943f63%22%7D%7D
    # https://staging.scicat.ess.eu/api/v3/Datasets?filter=%7B%22where%22%3A%7B%22scientificMetadata.job_id.value%22%3A%2212aac4ec-92ba-11ed-81fb-fa163e943f63%22%7D%7D&access_token=AMOSyF2K3Iev7xu6eJe62RDAOMvnt3IQ6r2Z7SYMJtJlO7wqwvAI6DsM9xvf9UNA
 
    response = requests.request(
        method="get",
        url=url,
        headers={'Accept':'application/json'},
        timeout=scClient._timeout_seconds,
        stream=False,
        verify=True
    )
    logger.info(response)
    logger.info(response.url)
    if not response.ok:
        logger.info("Dataset by job id error. status : {} {}".format(response.status_code,response.reason))
        return []

    logger.info(response.text)
    results = response.json()
    logger.info("Retrieved {} Datasets with job id {}".format(len(results),job_id))
    return results
