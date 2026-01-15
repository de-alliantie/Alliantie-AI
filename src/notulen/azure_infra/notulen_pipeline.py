import os
import sys
from pathlib import Path
from typing import Any

from azure.ai.ml import Input, MLClient, Output
from azure.ai.ml.dsl import pipeline
from azure.ai.ml.entities import (
    Job,
    ManagedIdentityConfiguration,
    ResourceConfiguration,
)
from azure.identity import DefaultAzureCredential

# dir_path should lead to src so that you can do imports from your other files
dir_path = Path(os.path.abspath(__file__)).parent.parent.parent
sys.path.append(str(dir_path))

from notulen.azure_infra.post_transcribe_job.post_transcribe_component_file import (  # noqa: E402
    post_transcribe_component,
)
from notulen.azure_infra.transcribe_job.transcribe_component_file import (  # noqa: E402
    transcribe_component,
)
from notulen.settings import DATALAKE_BASE_FOLDER  # noqa: E402

# from webapp.check_credential import check_credential

# try UserIdentityConfiguration when the AZML pipeline gives authentication error, but
# ManagedIdentityConfiguration should also work when you just run only this file locally.
identity_configuration = ManagedIdentityConfiguration()


@pipeline(default_compute="serverless")
def my_pipeline(
    input_folder: Input,
    output_folder_path: str,
    timestamp: str,
    type_notulen: str,
    OTAP: str,
    email: str,
    vve_number="",
    for_vve=False,
) -> Any:
    """Generate meeting notes."""

    output_folder = Output(path=output_folder_path, type="uri_folder", mode="rw_mount")

    gpu_node = transcribe_component(input_folder=input_folder)
    # use either gpu_node.compute or gpu_node.resources to set the compute, depending on if you
    # want to use the compute cluster or serverless compute. Note that for serverless compute,
    # the NCv3 series will deprecate!
    gpu_node.compute = "ml-ci-gpu-cluster-prd"
    # gpu_node.resources = ResourceConfiguration(instance_type="Standard_NC6s_v3", instance_count=1)
    gpu_node.outputs.output_folder = output_folder
    gpu_node.environment_variables = {
        "vve_number": vve_number,
        "for_vve": for_vve,
        "OTAP": OTAP,
        "email": email,
        "timestamp": timestamp,
        "in_which_node": "gpu",
        "APPLICATION_INSIGHTS_CONNECTION_STRING": os.environ["APPLICATION_INSIGHTS_CONNECTION_STRING"],
        "APPLICATION_INSIGHTS_NAMESPACE": os.environ["APPLICATION_INSIGHTS_NAMESPACE"],
    }

    cpu_node = post_transcribe_component(input_folder=gpu_node.outputs.output_folder)
    # use this instead if you want to comment out the gpu node:
    # cpu_node = post_transcribe_component(input_folder=input_folder)
    cpu_node.resources = ResourceConfiguration(instance_type="Standard_DS1_v2", instance_count=1)
    cpu_node.outputs.output_folder = output_folder
    cpu_node.environment_variables = {
        "vve_number": vve_number,
        "for_vve": for_vve,
        "timestamp": timestamp,
        "type_notulen": type_notulen,
        "OTAP": OTAP,
        "email": email,
        "in_which_node": "cpu",
        "DATALAKE_NAME": os.environ["DATALAKE_NAME"],
        "APPLICATION_INSIGHTS_CONNECTION_STRING": os.environ["APPLICATION_INSIGHTS_CONNECTION_STRING"],
        "APPLICATION_INSIGHTS_NAMESPACE": os.environ["APPLICATION_INSIGHTS_NAMESPACE"],
        "OPENAI_SWEDEN": os.environ["OPENAI_SWEDEN"],
        "OPENAI_SWEDEN_ENDPOINT": os.environ["OPENAI_SWEDEN_ENDPOINT"],
        "POWER_AUTOMATE_SEND_EMAIL_FLOW_URL": os.environ["POWER_AUTOMATE_SEND_EMAIL_FLOW_URL"],
        "ID_UAMI_MLW_ML_PLTFRM_PRD_CI_CLIENT_ID": os.environ["ID_UAMI_MLW_ML_PLTFRM_PRD_CI_CLIENT_ID"],
    }


def run_pipeline(
    timestamp: str, type_notulen: str, OTAP: str, email: str, vve_number="", for_vve=False
) -> tuple[MLClient, Job]:
    """Runs the pipeline."""
    if for_vve:
        folder = f"{vve_number}/{timestamp}"
    else:
        folder = timestamp

    if OTAP in ["prd", "acc"]:
        if for_vve:
            datastore_name = "vve_notulen_prd"
        else:
            datastore_name = f"{DATALAKE_BASE_FOLDER}_prd"
    else:
        if for_vve:
            datastore_name = "vve_notulen_dev"
        else:
            datastore_name = f"{DATALAKE_BASE_FOLDER}_dev"

    input_folder = Input(
        path=os.path.join(f"azureml://datastores/{datastore_name}/paths/{DATALAKE_BASE_FOLDER}/", folder),
        type="uri_folder",
        mode="ro_mount",
    )
    output_folder_path = os.path.join(f"azureml://datastores/{datastore_name}/paths/{DATALAKE_BASE_FOLDER}/", folder)

    # create a pipeline
    pipeline_job = my_pipeline(
        input_folder=input_folder,
        output_folder_path=output_folder_path,
        timestamp=timestamp,
        type_notulen=type_notulen,
        OTAP=OTAP,
        email=email,
        vve_number=vve_number,
        for_vve=for_vve,
    )
    if for_vve:
        pipeline_job.display_name = f"VvE-{vve_number}"
    else:
        pipeline_job.display_name = f"Notulen-{timestamp}"
    pipeline_job.identity = identity_configuration

    credential = DefaultAzureCredential()  # becomes the webapp slot system assigned managed identity
    # Get a handle to workspace
    ml_client = MLClient(
        subscription_id=os.environ.get("AML_SUBSCRIPTION_ID"),
        resource_group_name=os.environ["RESOURCE_GROUP_PRD"],
        workspace_name=os.environ["WORKSPACE_NAME_PRD"],
        credential=credential,
    )

    # need "AzureML Data Scientist" permissions on AML workspace.
    # This is a role assignment in the Identity Access Control (IAM) of the Azure ML workspace.
    pipeline_job = ml_client.jobs.create_or_update(pipeline_job, experiment_name=f"notulen-{OTAP}")
    return ml_client, pipeline_job


if __name__ == "__main__":
    timestamp = "some_timestamp"
    run_pipeline(
        timestamp=timestamp,
        type_notulen="Kort en bondig",
        OTAP="local",
        email="YOU_CAN_PLACE_A_TESTING_EMAIL_HERE@DOESNOTEXIST.COM",
    )
