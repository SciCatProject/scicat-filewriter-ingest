# CONFIGURATION

Both online and offline ingestor share the same configuration file which can be passed in with `-c` options.

The configuration file is organized in multiple sections. This is an overview of each sections:
- general
  This section contains few fields that are used to configure the input parameters of the ingestor programs. Most of the time they are left empty as they are specified on the command line.  
  It also include the id of the configuration which is an arbitrary string, but for easy tracking and maintenance we suggest to be unique within your system.
  We also suggest to use uuids and change everytime the configuration is updated.
- dataset
  This section pertains to the offline ingestor and contains all the options related to creating the dataset in scicat. 
  It still contains some legacy options that are not in use anymore. They will be marked as obsolete and remove in the near future.
- ingestion
  This section is specific for the offline ingestor and contains all the options to configure the ingestion process, such as path to the offline ingestor, where are the schema files, whhich tests to do before creation and which files to create.
- kafka
  This section is used by the online ingestor and it configures how to connect to the kafka server and which topics to listen to, It also specify the parameters related to how to retrieve the messages. Please ask your kafka admin for more informations.
- logging
  This section is used by both programs and it specify how and where to send the logs. Logs can be sent to a file, the OS system and to a separate graylog. At the moment there are no integration with other log server, but they can be addedd as the need arise.
- scicat
  This section is used by the offline ingestor and it contains the info about url where the relevant scicat instance is reacheable and also the token that needs to be used for authentication purposes.

Following are the options one by one organized by the sections they belong to.

## General 
- nexus_file 
  This is the data file that the ingestor needs to ingest and should be contained in the dataset to be created.
  At the moment, the ingestor can handle only nexus files. If there is the need, additional formats can be added.
  The file to be ingested can be specified here, but in most cases, this option is left empty and the data file is passed as an argument at the command line.
- done_writing_message_file
  This is the message received by the online ingestor, if it is configure to save the message content to a file.
  At the moment, the naming is specific to ESS. It will be changed if the tool is adopted by other facilities.
  This option is also left empty most of the time as the file name is passed as command line option, if present.
- config_file
  This is the location of the configuraition file where all this options are saved.
  It is always empty as such file is provided as an argument with the option `-c`.
- id
  This is a string which should be set to a unique value for the admin convenience.
  We suggest to use uuids but there are no restrictions applied to it. We also suggest to change the id everytime the config is changed, so it is easy to debug and troubleshoot where automatic deployement system are in use.    
  Example: "c1eef5a0-9b8b-11ef-a991-0bfe16577c30",

## Dataset
- allow_dataset_pid: _boolean_
  This option instruct the ingestor if can specify the dataset pid or it should rely on SciCat to assign it the newly created dataset.
  Options:
  - False: SciCat will assign the PID
  - True: The ingestor assigns the PID
- generate_dataset_pid: _boolean_
  This option instruct the ingestor to generate a random pid for the dataset. The generate pid will be a uuid4 string.
  Options:
  - False: the ingestor will not generate a random PID
  - True: the ingestor will generate a random PID
- dataset_pid_prefix: _string_
  This option provides the facility specific prefix for the dataset uuids.
  Example: "20.500.12269",
- default_instrument_id: _string_
  This option specify which is the default instrument that the dataset will be associated if the instrument is not provided or is invalid. 
  Example: "20.500.12269/00fe23a2-f276-4e2e-9005-a89a9c6ae9fe"
- default_proposal_id: _string_
  This option speficy which is the default proposal id to be used if not provided or the one provided is invalid.  
  Example: "070910"
- default_owner_group: _string_
  This option specify which is the owner group of the dataset if it is not provided.
  Example: "070910"
- default_access_groups: _string[]_
  This options provides a list of string that should be used as access groups if not provided.  
  Example: [ "group_1", "group_2" ]


## Ingestion
- dry_run: _boolean_
  This option instruct the ingestor to run in dry run mode. It performs all the required actions with the associated logs, except the ones that modify the data catalog.   
  Options:
  - false: perform the ingestions
  - true: does all the preparation, but it does not attempt to run offline ingestor (if running th eonline ingestor), or create a dataset entry in SciCat (if running the offline ingestor).
- offline_ingestor_executable: _string[]_
  This option provides the online ingestor with the command line needed to run the offline ingestor. It is an array of strings as the ingestor is a python scripts and the admin might want to specify a specific version of python that is not the default one. 
  Example: [ "/root/micromamba/envs/scicat-ingestor/bin/python", /ess/services/scicat-ingestor/software/src/scicat_offline_ingestor.py" ]
- schemas_directory: _string_
  This option define the full path of the folder where all the imsc files are located in this installation. It is used in the offline ingestor only. Please visit the section relative tpo the schema for more information about the imsc files.
  Example: "/ess/services/scicat-ingestor/schemas",
- check_if_dataset_exists_by_pid:_boolean_
  This option instruct the offline ingestor to check if a dataset with the same pid already exists in the scicat instance of reference.
  Options: 
  - false: do no check and attempt directly creating the dataset
  - true: check if a dataset with the same pid already exists and do not create the dataset if already present
- check_if_dataset_exists_by_metadata: _boolean_
  this option instruct the offline ingestor to check if a dataset with a specific metadata value is already present in the scicat instance of reference.
  Options:
  - false: do not check and attempt directly creating the dataset
  - true: check on the specified metadata key if a dataset already exists and do not create the dataset if already present
- check_if_dataset_exists_by_metadata_key: _string_
  Name of the metadata field that we need to check for dataset exists if option _check_if_dataset_exists_by_metadata_
  Example: "job_id"

### File Handling (file_handling)
- compute_file_stats: _boolean_
  This option instruct the offline ingestor to include in the scicat dataset file list the os statistics (aka ownership, permissions and size).
  Options:
  - false: no stats are added in the SciCat record for this file
  - true: stats are added in the SciCat record for this file
  Example:

- compute_file_hash: _boolean_
  This option instruct the offline ingestor to include in the scicat dataset file list the hash of the file content computed with the algorithm specified in option _file_hash_algorithm_.
  Options:
  - false: do not compute the hash
  - true: compute the hash and insert it in the scicat record for the file
- file_hash_algorithm: _string_
  Selected algorithm used to compute the file hash.
  Available options: blake2b
  Example: "blake2b"
- save_file_hash: _boolen_
  This options instruct the offline ingestor to save the computed hash also in a file located in the folder specified _ingestor_files_directory_ in a file that is named with the original data file name with the suffix defined in option _hash_file_extension_
  Options:
  - false: do not save the hash file
  - true: save the hash file in addition to store it in scicat
- hash_file_extension: _string_
  Extension appended to the data file name to define the hash file name.
  Example: "b2b"
- ingestor_files_directory: _string_
  This option provides the full path of the folder where all the files produced by the ingestor process should saved. It needs to be a valid full path.
  Example: "/ess/services/scicat-ingestor/output"
- message_to_file: _boolean_
  This option instruct the online ingestor to save the notification message received through the selected medium in a file with name compose by the original file name and the suffix specified in option _message_file_extension_.
  Options:
  - false: do not save original notification message in a file 
  - true: save original notification message in a json file
- message_file_extension: _string_
  Extension used for the message file if saved.
  Example: "message.json"
- file_path_type: _string_
  This option instruct the ingestor to use the specified type of path.
  Available options:
  - absolute: use absolute paths
  - ...
  
## Kafka (kafka)
- topics: _string[]_
  This option provide to the online ingestor the list of the topics to listen on the kafka cluster for the message informing the availability of a new data file.
  Example: [ "ymir_filewriter", "coda_filewriter" ]
- group_id: _string_
  This option instruct the online ingestor to connect to the kafka cluster with the specified id. Multiple instances of the ingestor can use the same id. In this case the kafka cluster will distribute the messages across the instances running under the same group.  
  Example: "scicat_filewriter_ingestor_05"
- bootstrap_servers: _string_
  This option provides the online ingestor with the comma separate list of the ip addresses of the kafka server that accept a connection including the port.
  Example: "10.100.4.15:8093,10.100.5.17:8093,10.100.5.29:8093"
- security_protocol: _string_
  This option specify the security protocol that the online ingestor should use to connect to the kafka cluster.
  Example: "sasl_ssl"
- sasl_mechanism: _string_
  This option provides to the online ingestor which sasl mechanism should be used to connect to the kafka cluster.
  Example: "SCRAM-SHA-256",
- sasl_username: _string_
  This options provides the user name use in the sasl protocol when connecting to the kafka cluster
  Example: "scicat_ingestor" 
- sasl_password: _string_
  This field provides the password associated with the user name for the sasl protocol when connecting to the kafka cluster
- ssl_ca_location: _string_
  This the full path to the file containing the ssl certificate needed to connect to the kafka cluster.
  Example: "/ess/services/scicat-ingestor/ssl/ecdc-kafka-ca.crt"
- auto_offset_reset: _string_
  This option specify the strategy on how to retrieve the messages from the kafka topic. Please consult kafka documentation for all the available options.
  Example: "earliest",
- enable_auto_commit: _boolean_
  This option instruct the online ingestor to auto commit all the messages.
  Options:
  - false: do not auto commit 
  - true: auto commit all the messages
- individual_message_commit: _boolean_
  This option configure the online ingestor to commit each message individually. At the moment this option is unstable and its use is not recommended. 
  Options:
  - false: do not auto commit each individual message
  - true: commit each individual message searately.

## Logging (logging)
- verbose: _boolean_
  Enable verbose logging for all the ingestor applications
- file_log: _boolean_
  Enable logging to files. Each run is logged in a separate file with a name composed by the path specified in option *file_log_base_name* followed by the timestamp (if enabled) and the .log extension.
- file_log_base_name: _string_
  This option provide the common full path for the log file name.
  Example: "/ess/services/scicat-ingestor/logs/scicat_ingestor_log",
- file_log_timestamp: _boolean_
  Enables the timestamp to be added in the log file name.
- logging_level: _string_
  Level of the logging. Any logs that matches the level specified or higher is sent to the logging facility.
  for more information about logging levels, please visit the following page: https://docs.python.org/3/library/logging.html#levels
  Example: "INFO",
- log_message_prefix: _string_
  Set the string that is affixed to every message logged.
  Example: "SCI" or "SciCat Ingestor"
- system_log: _boolean
  Enable logging to the system log. Please consult your OS logging documentation for more information where to find such logs.
  The system logs have been tested on *nix systems only. On different OS, mileage may vary.
- system_log_facility: _string_
  If running on *nix system, under which log system the messages are logged.
  Example: "mail",
- graylog: _boolean_
  Enable logging to a graylog system through the SciCat graylog integration. 
- graylog_host: _string_
  Ip address or valid hostname of the graylog server where the ingestor should send the logs
  Examples: "graylog.ess.eu"
- graylog_port: _integer as a string_
  Port on which the graylog service is listening and accepting remote logs on the graylog server
  Example: "12321",
- graylog_facility: _string_
  Arbitrary string used in the facility field for the graylog messages.
  It is suggested to pick a meaningful string that can be used when selecting entries in graylog inteface and queries
  Example: "scicat_ingestor"

## SciCat (scicat)
- host: _valid url as string_
  URL of the SciCat instance of reference where we want to create the dataset records.
  Example: "https://scicat.ess.eu/api/v3",
- token: _string_
  Valid JWT token used to connect to SciCat with the proper permissions to query and create datasets.
- timeout: _integer_ or _null_
  Value in ms for the timeout when placing requests to SciCat.
- stream: _boolean_
  Obscure option for the request library when connecting to a URL and send requests.
  Usually set to true.
  Please refer to the python requests library documentation for more information.
- verify: _boolean_
  Obscure option for the request library when connecting to a URL and send requests.
  Usually set to false.
  Please refer to the python requests library documentation for more information.

  
