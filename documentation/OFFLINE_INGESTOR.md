# OFFLINE INGESTOR

The offline ingestor is designed to ingest one data file according to a specific schema file (.imsc.json).
When invoked the offline ingestor perform the following steps:
- read the configuration
- load the schema files
- select the schema file that matches the data file
- retrieve all the required values and assign them to internally defined variables according to the _variables_ section of the schema file
- prepare local representation of the dataset assigning fields values according to the _schema_ section of the schema file
- prepare local representation of the file list according to the configuration provided
- send a POST request to the SciCat instance of reference to create the dataset
- send a POST requets to the SciCat instance of reference to create the origdatablock containing the list of files

Currently the offline ingestor can accept only data files in hdf5 nexus format. Other formats maybe be considered to be supported on a per-request and per-need base.  

For more information about the schema files, the variables and schema sections of such files, please consult the [schemas documentation](./SCHEMAS.md)

In a production deployment, the offline ingestor should be run as a background process by the online ingestor using the following command:
```
> <full_path_to_the_python_executable> 
  <full_path_to_the_ingestor_executables>/scicat_offline_ingestor.py 
    -c <full_path_to_the_configuration_file> 
    --nexus-file <full_path_to_the_nexus_data_file>
```
Such command can also be run manually in a terminal in case of need (aka automatic ingestion failed) or when troubleshooting.

In the ESS infrastructure, the command to run the offline ingestor on data file with full path `/ess/data/coda/2025/123321/raw/123321_000123456.hdf` is the following:
```
> /root/micromamba/envs/scicat-ingestor/bin/python 
  /ess/services/scicat-ingestor/software/src/scicat_offline_ingestor.py 
    -c /ess/services/scicat-ingestor/config/scicat_ingestor_config.json
    --nexus-file /ess/data/coda/2025/123321/raw/123321_000123456.hdf
```
