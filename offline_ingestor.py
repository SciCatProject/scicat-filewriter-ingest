#!/usr/bin/env python3
#
# 

import copy
from datetime import datetime
import json
import sys
from typing import Any
import uuid
import re
import os
import argparse
import logging
import logging.handlers
import ingestor_lib

from streaming_data_types import deserialise_wrdn

def main(config, logger):

    logger.info('SciCat FileWriter Offline Ingestor')

    uoClient = ingestor_lib.instantiate_user_office_client(config, logger)
    scClient = ingestor_lib.instantiate_scicat_client(config, logger)

    (
        defaultOwnerGroup,
        defaultAccessGroups,
        defaultInstrumentId,
        defaultInstrumentName,
        defaultInstrument,
        defaultProposal
    ) = ingestor_lib.get_defaults(
        config,
        scClient,
        uoClient,
        logger
    )

    # read in input the file with the message binary dump
    file = config['run_options']['input_file']
    logger.info(f"Loading message from file {file}")
    with open(file, 'rb') as f:
        raw_message_value = f.read()

    logger.info("Ingesting message")
    try:
        ingestor_lib.ingest_message(
            raw_message_value,
            defaultAccessGroups,
            defaultProposal,
            defaultInstrument,
            scClient,
            uoClient,
            config,
            logger
        )

    except Exception as error:
        logger.warning("Error ingesting the message: {}".format(error))


#
# ======================================
# define arguments
parser = argparse.ArgumentParser()

parser.add_argument(
    '-c','--cf','--config','--config-file',
    default='config.20230125.json',
    dest='config_file',
    help='Configuration file name. Default": config.20230125.json',
    type=str
)
parser.add_argument(
    '-v','--verbose',
    dest='verbose',
    help='Provide logging on stdout',
    action='store_true'
)
parser.add_argument(
    '--file-log',
    dest='file_log',
    help='Provide logging on file',
    action='store_true'
)
parser.add_argument(
    '--sys-log',
    dest='system_log',
    help='Provide logging on the system log',
    action='store_true'
)
parser.add_argument(
    '--log-prefix',
    dest='log_prefix',
    help='Prefix for log messages',
    default=' SFI: '
)
parser.add_argument(
    '--debug',
    dest='logging_level',
    help='Adjust the debug level',
    default='INFO',
    type=str
)
parser.add_argument(
    '-f','--file','--bin-file',
    dest='input_file',
    help='Input file containing the binary dump of the done writing kafka message',
    type=str
)
parser.add_argument(
    '-d','--dry-run',
    dest='dry_run',
    help='Execute a dry run. Does not create any entry in SciCat',
    action='store_true'
)
parser.set_defaults(verbose=False)
parser.set_defaults(file_log=False)

if __name__ == "__main__":

    # get input argumengts
    args = parser.parse_args()

    # get configuration from file and updates with command line options
    config = ingestor_lib.get_config(args)
    run_options = config['run_options']
    
    # instantiate logger
    logger = logging.getLogger('esd extract parameters')
    logger.setLevel(run_options['logging_level'])
    formatter = logging.Formatter(run_options['log_prefix'] + '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    print("Configuration : {}".format(json.dumps(config)))

    if run_options['file_log']:

        fh = logging.FileHandler(
            config['file_log_base_name'] \
                + ( 
                    '_' + datetime.now().strptime('%Y%m%d%H%M%S%f') 
                    if config['file_log_timestamp'] 
                    else ""
                )+ ".log",
            mode='w', 
            encoding='utf-8'
        )
        fh.setLevel(run_options['logging_level'])
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    if run_options['verbose']:
        ch = logging.StreamHandler()
        ch.setLevel(run_options['logging_level'])
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    if run_options['system_log']:
        sh = logging.handlers.SysLogHandler(address='/dev/log')
        sh.setLevel(run_options['logging_level'])
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    logger.info("Configuration : {}".format(json.dumps(config)))

    main(config,logger)
