# Dit script maakt éénmalig Azure blob datastores aan voor dev/prd.
# De datastores worden gebruikt in src/notulen/notulen_pipeline.py

import os

from azure.ai.ml import MLClient
from azure.ai.ml.entities import AzureBlobDatastore
from azure.identity import DefaultAzureCredential, InteractiveBrowserCredential

from notulen.settings import DATALAKE_BASE_FOLDER

# Authenticate
try:
    credential = DefaultAzureCredential(logging_enable=False)
    # Check if given credential can get token successfully.
    credential.get_token("https://management.azure.com/.default")
except Exception:
    # Fall back to InteractiveBrowserCredential in case DefaultAzureCredential not work
    credential = InteractiveBrowserCredential()

ml_client = MLClient(
    subscription_id=os.environ.get("AML_SUBSCRIPTION_ID"),
    resource_group_name=os.environ["RESOURCE_GROUP_PRD"],
    workspace_name=os.environ["WORKSPACE_NAME_PRD"],
    credential=credential,
)

# Create prd Datastore
prd_store = AzureBlobDatastore(
    name=f"{DATALAKE_BASE_FOLDER}_prd",
    description="Datastore for notulen generator",
    account_name=os.environ["DATALAKE_NAME_PRD"],
    container_name="ds-files",
)

ml_client.create_or_update(prd_store)

# Create dev Datastore
dev_store = AzureBlobDatastore(
    name=f"{DATALAKE_BASE_FOLDER}_dev",
    description="Datastore for notulen generator",
    account_name=os.environ["DATALAKE_NAME_DEV"],
    container_name="ds-files",
)

ml_client.create_or_update(dev_store)
