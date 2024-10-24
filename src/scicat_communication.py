# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import logging

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
        url=config.urls["datasets"],
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
        url=config.urls["origdatablocks"],
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


def render_full_url(
    url: str,
    config: SciCatOptions,
) -> str:
    if not url.startswith("http://") and not url.startswith("https://"):
        for endpoint in config.urls.keys():
            if url.startswith(endpoint):
                url = url.replace(endpoint, config.urls[endpoint])
                break
    return url
