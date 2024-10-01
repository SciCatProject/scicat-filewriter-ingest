import logging

from scicat_communication import create_scicat_dataset
from scicat_configuration import SciCatOptions
from scicat_dataset import ScicatDataset, scicat_dataset_to_dict

SAMPLE_OPTION = SciCatOptions(
    host="localhost",
    token="",
    headers={},
    timeout=1,
    stream=False,
    verify=False,
)


def test_create_scicat_dataset(require_scicat_backend: bool):
    assert require_scicat_backend
    dummy_dataset = ScicatDataset(
        pid='abc',
        size=0,
        numberOfFiles=0,
        isPublished=False,
        datasetName='datasetName',
        description='description',
        principalInvestigator='principalInvestigator',
        creationLocation="here",
        scientificMetadata={},
        owner="me",
        ownerEmail="",
        sourceFolder="",
        contactEmail="",
        creationTime="now",
        sampleId="",
    )
    create_scicat_dataset(
        dataset=scicat_dataset_to_dict(dummy_dataset),
        config=SAMPLE_OPTION,
        logger=logging.getLogger(__name__),
    )
