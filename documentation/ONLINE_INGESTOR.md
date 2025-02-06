# ONLINE INGESTOR

The online ingestor is designed to implement the functionalities to connect to the delivery system, listen for the notification that a new dataset is available, and start a background process where the offline ingestor runs to ingest the specified file.
It spins up only a limited numbers of offline ingestor than, if needed, it stops and wait until the number of the offline ingestors drops below the threshold specified to continue ingesting. The number of offline ingestors and the wait time when checking are configurable throught the options _max_offline_ingestors_ and _offline_ingestors_wait_time_.
In the current versions, the online ingestor is ESS specific and only support connecting to a kafka cluster and listen to a message of type WRDN.
Generalization and adoption of different delivery and messaging system will be considered on a per-request base.

Currently to run the ingestor, the following command should be run at command line:
```
> <path_to_the_selected_python_executable>  <full_path_to_the_ingestor_executable_folder>/scicat_online_ingestor.py -c <full_path_to_the_configuration_file>
```

In the case of the ESS test environment, the command looks like this:
```
> /root/micromamba/envs/scicat-ingestor/bin/python 
    /ess/services/scicat-ingestor/software/src/scicat_online_ingestor.py 
        -c /ess/services/scicat-ingestor/config/scicat_ingestor_config.json
```

Regarding the configuration file, the online ingestor uses only the following sections:
- ingestion
- kafka
- logging
