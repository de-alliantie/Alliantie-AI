"""Zie transcribe_component_file.py voor meer uitleg over dit bestand, want het is bijna hetzelfde."""
import os
import sys
from pathlib import Path

from mldesigner import Input, Output, command_component

# dir_path should lead to src so that you can do imports from your other files
dir_path = Path(os.path.abspath(__file__)).parent.parent.parent.parent
sys.path.append(str(dir_path))

from notulen.genereer_notulen import full_pipeline  # noqa: E402


@command_component(
    name="post_transcribe",
    version="1",
    display_name="Post transcribe",
    description="Process agenda + transcript into notes",
    environment=dict(
        conda_file=Path(__file__).parent / "conda-post-transcribe.yaml",
        image="crmlpltfrmprd.azurecr.io/aml-pandoc-dev:latest",
    ),
    code="../../..",
)
def post_transcribe_component(
    input_folder: Input(type="uri_folder"), output_folder: Output(type="uri_folder")  # noqa:F821
):
    """Prepare the component."""

    # Set the AZURE_CLIENT_ID in the environment to the required user-assigned managed identity,
    # this makes sure the DefaultAzureCredential uses the managed identity.
    os.environ["AZURE_CLIENT_ID"] = os.environ["ID_UAMI_MLW_ML_PLTFRM_PRD_CI_CLIENT_ID"]

    full_pipeline(input_folder=input_folder, output_folder=output_folder)
