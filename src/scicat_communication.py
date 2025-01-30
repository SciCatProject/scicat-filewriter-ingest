# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import json
import logging
from dataclasses import asdict
from typing import Any
from urllib.parse import quote_plus, urljoin

import requests
from scicat_configuration import SciCatOptions


def retrieve_value_from_scicat(
    *,
    config: SciCatOptions,
    scicat_endpoint_url: str,  # It should be already rendered
    # from variable_recipe["url"]
    field_name: str,  # variable_recipe["field"]
) -> str:
    response: dict = requests.get(
        scicat_endpoint_url, headers=config.headers, timeout=config.timeout
    ).json()
    return response[field_name] if field_name else response


class ScicatDatasetAPIError(Exception):
    pass


def _get_from_scicat(
    *, url: str, headers: dict, timeout: int, stream: bool, verify: bool
) -> requests.Response:
    return requests.get(url, headers=headers, timeout=timeout)


def _post_to_scicat(*, url: str, posting_obj: dict, headers: dict, timeout: int):
    return requests.request(
        method="POST",
        url=url,
        json=posting_obj,
        headers=headers,
        timeout=timeout,
        stream=False,
        verify=True,
    )


def create_scicat_dataset(
    *, dataset: dict, config: SciCatOptions, logger: logging.Logger
) -> dict:
    """
    Execute a POST request to scicat to create a dataset
    """
    logger.info("Sending POST request to create new dataset")
    response = _post_to_scicat(
        url=config.urls.datasets,
        posting_obj=dataset,
        headers=config.headers,
        timeout=config.timeout,
    )
    result: dict = response.json()
    if not response.ok:
        logger.error(
            "Failed to create new dataset. \nError message from scicat backend: \n%s",
            result.get("error", {}),
        )
        raise ScicatDatasetAPIError(f"Error creating new dataset: \n{dataset}")

    logger.info(
        "Dataset created successfully. Dataset pid: %s",
        result.get("pid"),
    )
    return result


class ScicatOrigDatablockAPIError(Exception):
    pass


def create_scicat_origdatablock(
    *, origdatablock: dict, config: SciCatOptions, logger: logging.Logger
) -> dict:
    """
    Execute a POST request to scicat to create a new origdatablock
    """
    logger.info("Sending POST request to create new origdatablock")
    response = _post_to_scicat(
        url=config.urls.origdatablocks,
        posting_obj=origdatablock,
        headers=config.headers,
        timeout=config.timeout,
    )
    result: dict = response.json()
    if not response.ok:
        logger.error(
            "Failed to create new origdatablock. "
            "Error message from scicat backend: \n%s",
            result.get("error", {}),
        )
        raise ScicatOrigDatablockAPIError(
            f"Error creating new origdatablock: \n{origdatablock}"
        )

    logger.info(
        "Origdatablock created successfully. Origdatablock pid: %s",
        result['_id'],
    )
    return result


def render_full_url(url: str, config: SciCatOptions) -> str:
    urls = asdict(config.urls)
    if not url.startswith("http://") and not url.startswith("https://"):
        for endpoint in urls.keys():
            if url.startswith(endpoint):
                return url.replace(endpoint, urls[endpoint])
    return url


def check_dataset_by_pid(
    pid: str, config: SciCatOptions, logger: logging.Logger
) -> bool:
    response = _get_from_scicat(
        url=urljoin(config.host_address, f"datasets/{quote_plus(pid)}"),
        headers=config.headers,
        timeout=config.timeout,
        stream=config.stream,
        verify=config.verify,
    )
    dataset_exists = response.ok
    # Log the result
    if response.ok:
        logger.info("Retrieved %s dataset(s) from SciCat", len(response.json()))
        logger.info("Dataset with pid %s exists.", pid)
    # Filter 404 error code.
    # Scicat returns 404 error code when the file does not exist.
    # This function is trying to check the existence of the dataset,
    # therefore 404 error code should not be considered as an error.
    elif response.status_code == 404:
        logger.info("Dataset with pid %s does not exist.", pid)
    else:
        logger.error(
            "Failed to check dataset existence by pid %s\n"
            "with status code: %s. \n"
            "Error message from scicat backend: \n%s\n"
            "Assuming the dataset does not exist.",
            pid,
            response.status_code,
            response.reason,
        )

    return dataset_exists


def check_dataset_by_metadata(
    metadata_key: str,
    metadata_value: Any,
    config: SciCatOptions,
    logger: logging.Logger,
) -> bool:
    metadata_dict = {f"scientificMetadata.{metadata_key}.value": metadata_value}
    filter_string = '?filter={"where":' + json.dumps(metadata_dict) + "}"
    url = urljoin(config.host_address, "datasets") + filter_string
    logger.info("Checking if dataset exists by metadata key: %s", metadata_key)
    response = _get_from_scicat(
        url=url,
        headers=config.headers,
        timeout=config.timeout,
        stream=config.stream,
        verify=config.verify,
    )
    dataset_exists = response.ok

    # Log the response
    if response.ok:
        logger.info("Retrieved %s dataset(s) from SciCat", len(response.json()))
        logger.info("Dataset with metadata %s exists.", metadata_dict)
    # Filter 404 error code.
    # Scicat returns 404 error code when the file does not exist.
    # This function is trying to check the existence of the dataset,
    # therefore 404 error code should not be considered as an error.
    elif response.status_code == 404:
        logger.info("Dataset with metadata %s does not exist.", metadata_dict)
    else:
        logger.error(
            "Failed to check dataset existence by metadata key %s \n"
            "with status code: %s \n"
            "Error message from scicat backend: \n%s\n"
            "Assuming the dataset does not exist.",
            metadata_key,
            response.status_code,
            response.reason,
        )

    return dataset_exists
