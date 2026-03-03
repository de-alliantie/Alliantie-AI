import json
import os
import re
from pathlib import Path

import streamlit as st
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient

from notulen.settings import SUPPORTED_MEDIA_FILES
from veilig_chatgpt.settings import DATALAKE_LOGGING_BASE_PATH


def set_styling():
    """Sets all the styling for the app, including CSS styling and de Alliantie logo in sidebar."""
    st.set_page_config(page_title="Alliantie AI", page_icon="webapp_src/img/alliantie_logo.png")
    st.logo("webapp_src/img/logo_wit.png")
    with open("webapp_src/styles.css") as css:
        st.markdown(f"<style>{css.read()}</style>", unsafe_allow_html=True)


def check_audio_files(uploaded_audio: list) -> tuple[bool, str]:
    """Checks if:
    1. the audio filenames are a single a number
    2. file extensions are valid
    3. there are no duplicate names."""
    multiple_files = True if len(uploaded_audio) > 1 else False
    for file in uploaded_audio:
        if multiple_files:
            # Remove the extensions, as it can contain a number (eg .mp3)
            name = file.split(".")[0]
            # Check if there is a single digit in the name (and nothing else)
            if not re.search(r"^[0-9]$", name):
                return False, "Opnamebestanden hebben geen goede naam (niet genummerd)."

        # check extension:
        if file.split(".")[-1] not in SUPPORTED_MEDIA_FILES:
            return False, "Bestandstype van een opname-bestand ongeldig."

    return True, "Je kan nu op Upload klikken."


def check_vve_number(vve_number: str) -> bool:
    """Checks if the vve_number a single, 4-digit number."""
    if not re.search(r"^[0-9]{4}$", vve_number):
        return False

    return True


class FailSavingChat(Exception):
    """Raised when there is a failure in saving & writing chat to the datalake."""

    def __init__(self, message: str, source_document=None):
        """Initialize the class."""
        self.message = message
        self.source_document = source_document
        super().__init__(self.message)


def save_metadata(client: ContainerClient, chat: dict):
    """Save chat metadata."""
    Path("data/chats_json").mkdir(parents=True, exist_ok=True)
    timestamp_no_date = chat["timestamp_last_chat"][11:].replace(":", "")
    filename = f"{chat['session_uuid']}_{timestamp_no_date}.json"
    filepath = f"data/chats_json/{filename}"
    with open(filepath, "w") as chatfile:
        json.dump(chat, chatfile)
    with open(filepath, "rb") as chatfile:
        client.upload_blob(name=f"{DATALAKE_LOGGING_BASE_PATH}/chat/{filename}", data=chatfile.read())


@st.cache_resource(ttl="4h")
def container_client() -> ContainerClient:
    """Initialize container client."""
    return ContainerClient(
        account_url=f"https://{os.environ['DATALAKE_NAME']}.blob.core.windows.net",
        container_name="ds-files",
        credential=DefaultAzureCredential(),
    )


if __name__ == "__main__":
    pass
