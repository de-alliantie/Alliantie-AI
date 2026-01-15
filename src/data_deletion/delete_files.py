import os
from datetime import datetime, timedelta

from notulen.settings import DATALAKE_BASE_FOLDER
from shared.msteams import log_result_to_MS_teams
from shared.my_logging import logger
from shared.utils import AzureHelper, init_openai_client


def delete_data_from_datalake(az: AzureHelper):
    """Delete all files used to generate notulen that are older than 7 days."""
    successfully_deleted = 0
    not_deleted = 0

    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    client = az.container_client
    all_blobs = list(client.list_blob_names(name_starts_with=f"{DATALAKE_BASE_FOLDER}/"))
    timestamps = [x.split("/")[1] for x in all_blobs]
    timestamps = sorted(set(timestamps))
    for timestamp in timestamps:
        datetimestamp = timestamp[:10]
        if datetimestamp < seven_days_ago:
            az.delete_blob_folder(f"{DATALAKE_BASE_FOLDER}/{timestamp}")
            successfully_deleted += 1
        else:
            not_deleted += 1

    logger.info(f"Deleted {successfully_deleted} blobs from the datalake, {not_deleted} blobs were not deleted.")


def delete_old_notulen_files() -> None:
    """Removes all uploaded and created files in the process of generating notulen.

    That is: agenda, opname, transcript, notulen, and any intermediate files.
    Files are considered 'old' if they are older than 7 days and then removed from datalake.
    """
    logger.info("Deleting notulen from datalake prd")
    az = AzureHelper(account_name=os.environ["DATALAKE_NAME_PRD"])
    delete_data_from_datalake(az)

    logger.info("Deleting notulen from datalake dev")
    az2 = AzureHelper(account_name=os.environ["DATALAKE_NAME_DEV"])
    delete_data_from_datalake(az2)

    return None


def remove_files_uploaded_to_veiligchatgpt() -> None:
    """Remove all uploaded files to the Veilig ChatGPT functionality of the web app.

    This was uploaded to the Azure OpenAI Client. All uploaded files are considered 'old' every night and thus removed.
    """
    logger.info("Removing all uploaded files from the Azure OpenAI Client...")
    client = init_openai_client()

    # Remove files one by one
    files_before_removing = client.files.list()
    original_number_of_files = len(files_before_removing.data)
    for f in files_before_removing.data:
        try:
            client.files.delete(f.id)
        except Exception as e:
            logger.error(f"Failed to delete id {f.id}: {e}")
            continue

    files_after_removing = client.files.list()
    new_number_of_files = len(files_after_removing.data)
    logger.info(
        f"Removed {original_number_of_files - new_number_of_files} files from Azure OpenAI. {new_number_of_files} files remaining."  # noqa: E501
    )

    if new_number_of_files > 0:
        message = (
            f"There are still {new_number_of_files} files remaining in the Azure OpenAI client. This is unexpected!"
        )
        logger.error(message)
        log_result_to_MS_teams(f"VEILIG CHATGPT: {message}")
    else:
        logger.info("All files have been successfully removed from the Azure OpenAI client.")

    return None


if __name__ == "__main__":
    delete_old_notulen_files()
    remove_files_uploaded_to_veiligchatgpt()
