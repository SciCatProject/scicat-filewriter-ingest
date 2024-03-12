import json
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import TypedDict


class FileDescription(TypedDict):
    path: str | Path
    size: int


@dataclass
class FileOmittingConfig:
    ingestor_file_dir: Path
    file_name_prefix: str

    @classmethod
    def from_run_options_and_message(
        cls, run_options: dict, wrdn_msg: dict
    ) -> 'FileOmittingConfig':
        file_path = Path(wrdn_msg['file_name'])
        if run_options["hdf_structure_output"] == "SOURCE_FOLDER":
            ingestor_file_dir = file_path.parent / Path(
                run_options['ingestor_files_folder']
            )
        else:
            ingestor_file_dir = Path(run_options['files_output_folder']).absolute()

        file_name_prefix = file_path.name.removesuffix(file_path.suffix)
        return cls(ingestor_file_dir, file_name_prefix)


def omit_message_as_file(
    logger: Logger, wrdn_msg: dict, extension: str, fo_config: FileOmittingConfig
) -> FileDescription:
    """Omit the message as a file."""
    logger.info("message file will be saved in {}".format(fo_config.ingestor_file_dir))

    message_file_name = '.'.join([fo_config.file_name_prefix, extension])
    logger.info("message file name : " + message_file_name)
    message_full_file_path = fo_config.ingestor_file_dir / message_file_name
    logger.info("message full file path : " + message_full_file_path.as_posix())

    with open(message_full_file_path, 'w') as fh:
        json.dump(wrdn_msg, fh)

    logger.info("message saved to file")
    return FileDescription(
        path=message_full_file_path, size=message_full_file_path.stat().st_size
    )


def omit_hdf_structure(
    logger: Logger, hdf_structure: dict, extension: str, fo_config: FileOmittingConfig
) -> FileDescription:
    """Omit the HDF structure as a file."""
    logger.info(
        "hdf structure file will be saved in {}".format(fo_config.ingestor_file_dir)
    )

    hdf_structure_file_name = '.'.join([fo_config.file_name_prefix, extension])
    logger.info("hdf structure file name : " + hdf_structure_file_name)
    hdf_structure_file_path = fo_config.ingestor_file_dir / hdf_structure_file_name
    logger.info("hdf structure full file path : " + hdf_structure_file_path.as_posix())

    with open(hdf_structure_file_name, 'w') as fh:
        json.dump(hdf_structure, fh, indent=2)

    logger.info("hdf structure saved to file : " + hdf_structure_file_name)
    return FileDescription(
        path=hdf_structure_file_name, size=hdf_structure_file_path.stat().st_size
    )
