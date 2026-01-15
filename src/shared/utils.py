import base64
import json
import os
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)
from openai import OpenAI

from notulen.settings import DATALAKE_BASE_FOLDER
from shared.my_logging import logger


class AzureHelper:
    """A class to manage blobs in Azure."""

    def __init__(
        self,
        account_name=os.environ["DATALAKE_NAME"],
        container_name="ds-files",
        base_folder=DATALAKE_BASE_FOLDER,
    ):
        """Initialises the helper, logs in to Azure and creates the BlobServiceClient."""
        self.account_name = account_name
        self.account_url = f"https://{account_name}.blob.core.windows.net"
        self.container_name = container_name
        self.base_folder = base_folder

        # becomes the webapp slot system assigned managed identity:
        self.credential = DefaultAzureCredential(logging_enable=False)

        self.blob_service_client = BlobServiceClient(self.account_url, credential=self.credential)
        self.container_client = self.blob_service_client.get_container_client("ds-files")

    def upload_dict_to_blob_storage(self, folder_path: str, filename: str, my_dict: dict):
        """Uploads a dictionary to the blob storage as a JSON file."""
        # Convert the dictionary to a JSON string
        json_str = json.dumps(my_dict, ensure_ascii=False, indent=4)

        # Create the full file path
        full_filepath = os.path.join(self.base_folder, folder_path, filename)

        logger.info("\nUploading to Azure Storage as blob:\n\t" + full_filepath)

        # Create a blob client using the full file path
        blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=full_filepath)

        # Upload the JSON string as a blob
        blob_client.upload_blob(
            json_str,
            content_settings=ContentSettings(content_type="application/json"),
            overwrite=True,  # optional, if you want to overwrite existing blob
        )

    def upload_file_to_blob_storage(self, folder_path: str, filename: str, data: str) -> str:
        """Initiates a blob client, uploads the data to base_folder/folder_path/filename."""
        full_filepath = os.path.join(self.base_folder, folder_path, filename)

        logger.info("\nUploading to Azure Storage as blob:\n\t" + full_filepath)

        blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=full_filepath)
        blob_client.upload_blob(data)

        blob_folder = os.path.join(self.base_folder, folder_path)

        return blob_folder

    def delete_blob_folder(self, input_folder: str):
        """Delete the given folder on the datalake.

        Note that non empty folders first have to be emptied before deletion. Do this by first deleting all the blobs
        that are files inside the folder and its subfolders, then delete the subfolders starting with the deepest one,
        and move up the 'tree'.
        """
        client = self.container_client
        all_blobs_in_folder = client.list_blob_names(name_starts_with=input_folder)
        folderblobs_and_depth = []
        for blob in all_blobs_in_folder:
            path_elements = blob.split("/")
            depth = len(path_elements)
            if "." in path_elements[-1]:  # if it is a file
                client.delete_blob(blob)
            else:
                folderblobs_and_depth.append((blob, depth))
        max_depth = max([x[1] for x in folderblobs_and_depth])
        min_depth = len(input_folder.split("/"))
        for i in range(max_depth, min_depth - 1, -1):
            for path, depth in folderblobs_and_depth:
                if depth == i:
                    client.delete_blob(path)

    def generate_upload_url(self, blob_name: str) -> str:
        """Generates a SAS URL for uploading a blob to Azure Blob Storage."""
        expiry = datetime.now() + timedelta(hours=3)  # expiration of the URLs
        sas_token = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            account_key=os.environ["STORAGE_ACCOUNT_STDLSPLTFRM_ACCOUNT_KEY"],
            permission=BlobSasPermissions(write=True, create=True),
            expiry=expiry,
        )
        return f"{self.account_url}/{self.container_name}/{urllib.parse.quote(blob_name)}?{sas_token}"

    def generate_multiple_urls(self, filenames: list, timestamp: str) -> list[str]:
        """Generates multiple SAS URLs for uploading files to Azure Blob Storage."""
        sas_urls = []
        for filename in filenames:
            blob_path = f"{self.base_folder}/{timestamp}/input/opname/{filename}"
            sas_urls.append(self.generate_upload_url(blob_path))
        return sas_urls


def init_openai_client() -> OpenAI:
    """Initializes the OpenAI client with environment variables."""
    client = OpenAI(
        api_key=os.environ.get("OPENAI_SWEDEN"),
        base_url=f"{os.environ['OPENAI_SWEDEN_ENDPOINT']}/openai/v1/",
    )
    return client


def blob_name_to_datetime(blob_name: str) -> datetime:
    """Extracts the datetime from blob name.

    Args: blob_name (str): The name of the blob, expected to contain a timestamp in the format YYYYMMDDHHMMSS

    example: '20251113115003_4575337f-2fba-4d3e-8b68-408f56c8e5e2_115105.json'.
    """
    timestamp_str = blob_name.split("/")[-1].split("_")[0]
    return datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")


def retrieve_usage_statistics(starting_from: datetime | None) -> pd.DataFrame:
    """Reads the production usage statistics JSONs from the datalake and returns a DataFrame.

    If starting_from is provided, only blobs with a timestamp after starting_from, and before today, are included.
    """

    # Initialize a list to store the data
    data = []

    OTAP = "prd"
    DATALAKE_LOGGING_BASE_PATH = f"alliantie_ai/{OTAP}"

    # List all blobs in the specified folder
    container_name = "ds-files"
    DATALAKE_NAME_PRD = os.environ["DATALAKE_NAME_PRD"]
    blob_service_client = BlobServiceClient(
        f"https://{DATALAKE_NAME_PRD}.blob.core.windows.net", credential=DefaultAzureCredential(logging_enable=False)
    )
    container_client = blob_service_client.get_container_client(container_name)
    blob_list = container_client.list_blobs(name_starts_with=DATALAKE_LOGGING_BASE_PATH)

    for i, blob in enumerate(blob_list):
        if blob.name.endswith(".json"):

            blob_datetime = blob_name_to_datetime(blob.name)

            if starting_from is not None:

                # Check if the blob's datetime is after the starting_from date and excludes today.
                if (blob_datetime.date() >= starting_from.date()) and (blob_datetime.date() < datetime.now().date()):
                    logger.info(f"Trying to download blob {i}: {blob.name}...")
                    blob_client = container_client.get_blob_client(blob.name)
                    blob_data = blob_client.download_blob().readall()
                else:
                    continue

            else:

                # Download blobs up to yesterday
                if blob_datetime.date() < datetime.now().date():
                    logger.info(f"Trying to download blob {i}: {blob.name}...")
                    blob_client = container_client.get_blob_client(blob.name)
                    blob_data = blob_client.download_blob().readall()
                else:
                    continue

            try:
                json_data = json.loads(blob_data)
                row = {
                    "environment": json_data.get("environment", None),
                    "session_uuid": json_data.get("session_uuid", None),
                    "timestamp_last_chat": json_data.get("timestamp_last_chat", None),
                    "hashed_user": json_data.get("hashed_user", None),
                }
                data.append(row)
            except Exception as e:
                logger.warning(f"Failed to process blob {blob.name}: {e}")

    # Create a DataFrame from the data
    df = pd.DataFrame(data)

    if starting_from is not None:
        return df

    # Calculate statistics
    num_rows = len(df)
    num_unique_sessions = df["session_uuid"].nunique() if "session_uuid" in df.columns else 0
    num_unique_users = df["hashed_user"].nunique() if "hashed_user" in df.columns else 0

    print(f"Total questions asked: {num_rows}")
    print(f"Unique session_uuid's: {num_unique_sessions}")
    print(f"Unique hashed_user's: {num_unique_users}")

    # Save the DataFrame as a Parquet file
    df.to_parquet(
        f"data/usage_statistics/{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}_usage_statistics.parquet", index=False
    )

    return df


def update_usage_statistics():
    """Updates the usage_statistics file."""

    if os.path.exists("data/usage_statistics"):

        files = [
            f for f in os.listdir("data/usage_statistics/") if os.path.isfile(os.path.join("data/usage_statistics/", f))
        ]
        if len(files) >= 1:
            print("Existing usage statistics found, updating with new data...")
            for file in files:
                date_last_update = datetime.strptime(file.split("_")[0], "%Y%m%d")

                print("Retrieving usage statistics newer than ", date_last_update)

                # Extract usage statistics that are newer than date_last_update
                df_new = retrieve_usage_statistics(starting_from=date_last_update)
                print("Retrieved ", len(df_new), " new records.")

                # Get the old usage statistics
                df_old = pd.read_parquet(f"data/usage_statistics/{file}")

                # Merge old and new statistics
                df_merged = pd.concat([df_old, df_new], ignore_index=True)

                print("Saving updated usage statistics with ", len(df_merged), " total records.")
                df_merged.to_parquet(
                    f"data/usage_statistics/{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}_usage_statistics.parquet"
                )

                # Remove the old file
                os.remove(f"data/usage_statistics/{file}")
        else:
            # Case when a folder is present but there is no statistics file in it.
            print("No existing usage statistics found, retrieving all usage statistics up to this point...")
            _ = retrieve_usage_statistics(starting_from=None)

    else:
        # Case when no folder is present
        print("No existing usage statistics found, retrieving all usage statistics up to this point...")
        os.makedirs("data/usage_statistics", exist_ok=False)
        _ = retrieve_usage_statistics(starting_from=None)


def encode_file_b64(file_path: str) -> str:
    """Encode file as base64 bytes string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


if __name__ == "__main__":
    update_usage_statistics()
