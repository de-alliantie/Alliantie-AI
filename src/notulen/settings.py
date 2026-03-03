import os

OTAP = os.environ.get("OTAP", "local")
"""The list of files that are supported for transcribing."""
SUPPORTED_MEDIA_FILES = ["mp3", "wav", "mpeg", "m4a", "mp4", "webm", "mpga"]
"""The folder on the datalake where all files are stored."""
DATALAKE_BASE_FOLDER = "alliantie_notulen"
"""The name of the deployment on Azure Machine Learning."""
DEPLOYMENT_NAME = "gpt-4o-notulen"
