# WORKFLOW

As mentioned in the introduction this current version of the ingestor has being designed to separate the funtionalities in two different programs.
The two groups of functionalities are:
- discovery and notification of a new dataset with relative files
- individual dataset ingestion

The reason behind such decision is that a single program ,as it was initially, proved to be hard to test and also to maintain. With the splitted functionalities, we are able to test separately and also be able to run ingestion multiple time in case of error, completely independently form the discovery process.
This decision has improved considerably the time to release of the software, the configuration of the ingestion process.

A bird eye view of the general workflow can be summarize with the following diagram:
![SciCat ingestor workflow bird eye view](./scicat_ingestor_workflow_1.png)

A more detailed diagram explaining the steps involved in both components of the ingestor is as follow:

![SciCat ingestor workflow detailed view](./scicat_ingestor_workflow_2.png)


