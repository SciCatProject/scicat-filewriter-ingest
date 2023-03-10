#!/usr/bin/env python3

from datetime import datetime
import json
import sys
import uuid
import re

from user_office import UserOffice
from scicat import SciCat

from kafka import KafkaConsumer
from streaming_data_types import deserialise_wrdn


def main():
    # get configuration
    print("Loading configuration")
    config = get_config()
    # instantiate kafka consumer
    kafka_config = config["kafka"]
    consumer = KafkaConsumer(
        kafka_config["topic"],
        group_id=kafka_config["group_id"],
        bootstrap_servers=kafka_config["bootstrap_servers"],
        auto_offset_reset=kafka_config["auto_offset_reset"],
    )

    # instantiate connector to user office
    # retrieve relevant configuration
    print("Connecting to user office")
    user_office_config = config["user_office"]
    user_office = UserOffice(user_office_config["host"])
    user_office.login(user_office_config["username"],user_office_config["password"])

    # instantiate connector to scicat
    # retrieve relevant configuration
    print("Connecting to scicat")
    scicat_config = config["scicat"]
    scicat = SciCat(scicat_config["host"])
    scicat.login(scicat_config["username"],scicat_config["password"])


    # main loop, waiting for messages
    print("Starting main loop")
    try:
        for message in consumer:
            data_type = message.value[4:8]
            if data_type == b"wrdn":
                print("----------------")
                print("Write Done")
                entry = deserialise_wrdn(message.value)
                if entry.error_encountered:
                    continue
                print(entry)
                if entry.metadata is not None:
                    metadata = json.loads(entry.metadata)
                    print(metadata)
                    if "proposal_id" in metadata:
                        proposal_id = str(metadata["proposal_id"])
                        # proposalId = 169
                        #uo_proposal = user_office.get_proposal_by_id(proposal_id)
                        #print(uo_proposal)

                        #instrument = scicat.get_instrument_by_name(
                        #    uo_proposal["instrument"]["name"]
                        #)
                        #print(instrument)
                        # load proposal from scicat. 
                        # We assume that all the relevant information are already in scicat
                        proposal = scicat.get_proposal_by_pid(proposal_id)
                        print(proposal)

                        # load instrument by id or by name
                        instrument = {}
                        if "instrument_id" in metadata and metadata["instrument_id"]:
                            instrument = scicat.get_instrument_by_pid(metadata['instrument_id'])
                        if not instrument and "instrument_name" in metadata and metadata["instrument_name"]:
                            instrument = scicat.get_instrument_by_name(metadata["instrument_name"])


                        # find sample information
                        sample_id = metadata["sample_id"] \
                            if "sample_id" in metadata \
                            else ''
                        sample = scicat.get_sample_by_pid(sample_id) \
                            if sample_id \
                            else {}


                        dataset = create_dataset(
                            metadata, 
                            proposal, 
                            instrument,
                            sample
                        )
                        print(dataset)
                        created_dataset = scicat.post_dataset(dataset)
                        print(created_dataset)
                        
                        orig_datablock = create_orig_datablock(
                            created_dataset["pid"], 
                            entry.file_size if "file_size" in entry else 0,
                            entry.file_name,
                        )
                        print(orig_datablock)
                        created_orig_datablock = scicat.post_dataset_orig_datablock(
                            created_dataset["pid"], 
                            orig_datablock
                        )
                        print(created_orig_datablock)
    except KeyboardInterrupt:
        sys.exit()


def get_config() -> dict:
    with open("config.json", "r") as config_file:
        data = config_file.read()
        return json.loads(data)


def create_dataset(metadata: dict, proposal: dict, instrument: dict, sample: dict) -> dict:
    # prepare info for datasets
    dataset_pid = str(uuid.uuid4())
    dataset_name = metadata["run_name"] \
        if "run_name" in metadata \
        else "Dataset {} for proposal {}".format(dataset_pid,proposal.get('pid','unknown'))
    dataset_description = metadata["run_description"] \
        if "run_description" in metadata \
        else "Dataset: {}. Proposal: {}. Sample: {}. Instrument: {}".format(
            dataset_pid,
            proposal.get('proposalId','unknown'),
            instrument.get('pid','unknown'),
            sample.get('sampleId','unknown'))
    principal_investigator = proposal["pi_firstname"] + " " + proposal["pi_lastname"]
    email = proposal["pi_email"]
    instrument_name = instrument.get("name","")
    source_folder = (
        "/nfs/groups/beamlines/" + instrument_name if instrument_name else "unknown" + "/" + proposal["proposalId"]
    ) 
    
    # create dictionary with all requested info
    dataset = {
        "pid" : dataset_pid,
        "datasetName": dataset_name,
        "description": dataset_description,
        "principalInvestigator": email,
        "creationLocation": instrument.get("name",""),
        "scientificMetadata": prepare_metadata(flatten_metadata(metadata)),
        "owner": principal_investigator,
        "ownerEmail": email,
        "contactEmail": email,
        "sourceFolder": source_folder,
        "creationTime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "type": "raw",
        "ownerGroup": "ess",
        "accessGroups": ["loki", "odin"],
        "techniques": metadata.get('techniques',[]),
        "instrumentId": instrument.get("pid",""),
        "sampleId" : sample.get('sampleId',''),
        "proposalId": proposal.get("proposalId",''),
    }
    return dataset


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



def create_orig_datablock(dataset_pid: str, file_size: int, file_name: str) -> dict:
    orig_datablock = {
        "id" : str(uuid.uuid4()),
        "size": file_size,
        "ownerGroup": "ess",
        "accessGroups": ["loki", "odin"],
        "datasetId": dataset_pid,
        "dataFileList": [
            {
                "path": file_name,
                "size": file_size,
                "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }
        ],
    }

    return orig_datablock



if __name__ == "__main__":
    main()
