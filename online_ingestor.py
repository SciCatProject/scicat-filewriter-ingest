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
import traceback

#from kafka import KafkaConsumer, TopicPartition
from confluent_kafka import Consumer

def main(config, logger):

    logger.info('SciCat FileWriter Online Ingestor')
    # instantiate kafka consumer
    kafka_config = config["kafka"]
    # update topics if needed
    kafka_topics = kafka_config["topics"].split(',') if isinstance(kafka_config["topics"],str) else kafka_config["topics"]
    kafka_config["enable_auto_commit"] = (not kafka_config["individual_message_commit"]) and kafka_config["enable_auto_commit"]

    logger.info("Connecting to Kafka with the following parameters")
    kafka_config_run_time = {}
    for k1,v in kafka_config.items():
        if k1 in ["topics", "individual_message_commit"]:
            continue
        k2 = k1.replace("_",".")
        kafka_config_run_time[k2] = v
        logger.info(f" - {k2:<30}: {v}")

    consumer = Consumer(kafka_config_run_time)
    logger.info("Kafka consumer successfully instantiated... apparently!!!")

    uoClient = ingestor_lib.instantiate_user_office_client(config, logger)
    logger.info("User Office Client successfully instantiated ... apparently!!!")

    scClient = ingestor_lib.instantiate_scicat_client(config, logger)
    logger.info("SciCat Client successfully instantiated... base url : {}".format(scClient._base_url))

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

    logger.info("Subscribing to following kafka topics : {}".format(kafka_topics))
    consumer.subscribe(kafka_topics)
    # main loop, waiting for messages
    logger.info("Starting main loop ...")
    while True:
        try:
            message = consumer.poll(1.0)

            if message is None:
                logger.info("Received empty message")
                continue

            if message.error():
                logger.info("Consumer error: {}".format(message.error()))
                continue

            message_value = message.value()

            data_type = message_value[4:8]
            logger.info("Received message. Data type : {}".format(data_type))
            if data_type == b"wrdn":
                logger.info("Received writing done message from file writer")

                logger.info("scClient base url : {}".format(scClient._base_url))
                ingestor_lib.ingest_message(
                    message_value,
                    defaultAccessGroups,
                    defaultProposal,
                    defaultInstrument,
                    scClient,
                    uoClient,
                    config,
                    logger
                )
                #sys.exit()

            if kafka_config["individual_message_commit"]:
                consumer.commit(message=message)

        except KeyboardInterrupt:
            logger.info("Exiting ingestor")
            consumer.close()
            sys.exit()

        except Exception as error:
            logger.error("Error ingesting the message: {}".format(error))
            t, val, tb = sys.exc_info()   
            logger.error(traceback.print_tb(tb))
            #sys.exit()

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
    '--pyscicat',
    dest='pyscicat',
    help='Location where a specific version of pyscicat is available',
    default=None,
    type=str
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

    main(config, logger)
