# Introduction

SciCat Ingestor is a versatile application with the primary focus to automate the ingestion of new dataset in to SciCat. 

The project is composed of two main components:
- online ingestor  
  THis program is responsible to connect to a kafka cluster and listen to selected topics for a specific message and trigger the data ingestion by running the offline ingestor as a background proccess. At the moment, this is specific to ESS IT infrastructure, but it is already planned to generalize it as soon as other facilities express interest in adopting it. 
- offline ingestor
  THis program can be run from the online ingestor or by an operator. It is responsible to collect all the necessary metadata and create a dataset entry in SciCat.

This documentation is organized as follows:
- Introduction (this document)
- [Workflow](WORKFLOW.md)
- [Online ingestor](ONLINE_INGESTOR.md)
- [Offline ingestor](OFFLINE_INGESTOR.md)
- [Configuration](CONFIGURATION.md)
- [Schemas](SCHEMAS.md)
  - [General section](GENERAL_SECTION.md)
  - [Variables section](VARIABLES_SECTION.md)
  - [Schema section](SCHEMA_SECTION.md)