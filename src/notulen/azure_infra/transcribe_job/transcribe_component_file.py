"""Dit bestand is het beginpunt van de code die wordt uitgevoerd in de GPU node van de Azure ML pipeline.

Daarom is het nodig om de src folder toe te voegen aan de sys.path, zodat de imports werken. Dit is een alternatief voor
'pip install -e .' dat niet werkt. Het bestand notulen_pipeline.py wordt nog gedraaid in de webapp container (het
laatste bestand dat daar draait). Met de @command_component decorator wordt dit bestand een "component" in de Azure ML
pipeline.
"""
import os
import sys
from pathlib import Path

from mldesigner import Input, Output, command_component

# dir_path should lead to src so that you can do imports from your other files
dir_path = Path(os.path.abspath(__file__)).parent.parent.parent.parent
sys.path.append(str(dir_path))

from notulen.transcribe import transcribe  # noqa: E402


@command_component(
    name="transcribe_job",
    version="1",
    display_name="Transcribe the audio file",
    description="",
    environment=dict(
        conda_file=Path(__file__).parent / "conda-transcribe.yaml",
        image="mcr.microsoft.com/azureml/curated/acpt-pytorch-2.1-cuda12.1:6",
    ),
    code="../../..",  # this should lead to the src folder
)
def transcribe_component(input_folder: Input(type="uri_folder"), output_folder: Output(type="uri_folder")):  # noqa:F821
    transcribe(folder_path=input_folder, output_folder=output_folder)
