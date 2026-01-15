# flake8: noqa: E501
import os
import re
import time
from datetime import datetime
from typing import Any

import jwt
import streamlit as st
from azure.ai.ml import MLClient
from azure.ai.ml.entities import Job
from helpers_webapp import check_audio_files, set_styling
from streamlit.delta_generator import DeltaGenerator
from upload_component import blob_storage_upload_component

from notulen.azure_infra.notulen_pipeline import run_pipeline
from shared.my_logging import logger
from shared.utils import AzureHelper

set_styling()

# @st.cache_resource()
def get_azure_helper() -> AzureHelper:
    """."""
    az = AzureHelper(account_name=os.environ["DATALAKE_NAME"])
    return az


def getUserDetails(code: str | bytes) -> Any:
    """Decode the JWT token to get user details."""
    decoded = jwt.decode(
        code,
        algorithms=[
            "RS256",
        ],
        options={"verify_signature": False},
    )

    return decoded


if "user" not in st.session_state:
    st.session_state.user = {}

if "UserPrincipalName" not in st.session_state.user or st.session_state.user["UserPrincipalName"] == "":
    headers = st.context.headers
    user_email = headers.get("X-Ms-Client-Principal-Name")

    if user_email:
        st.session_state.user["userPrincipalName"] = user_email
    else:
        st.session_state.user["userPrincipalName"] = "YOU_CAN_PLACE_A_TESTING_EMAIL_HERE@DOESNOTEXIST.COM"


def start_pipeline(timestamp: str):
    """Starts the Azure ML Pipeline."""

    OTAP = os.environ.get("OTAP", "local")

    with status_placeholder.container():
        st.markdown("### Je ontvangt de notulen per e-mail zodra het proces klaar is.")
        st.markdown(
            "###### We raden je aan om deze pagina open te houden om de voortgang te bekijken. Maar ook als je de pagina sluit, gaat het genereren van notulen gewoon door."
        )
        with st.spinner("**Status:** "):

            progress_bar = st.progress(0, text="We halen je bestanden op...")

            progress_text = "Onze machine starten (straks kan je evt. nog annuleren)..."
            progress_percentage = 10

            progress_bar.progress(progress_percentage, text=progress_text)

            logger.info(f"Starting pipeline for: {timestamp}-{st.session_state.vve_number}")
            email = st.session_state.user["userPrincipalName"]
            ml_client, pipeline_job = run_pipeline(
                timestamp=timestamp,
                type_notulen=st.session_state.type_notulen,
                OTAP=OTAP,
                email=email,
                vve_number=st.session_state.vve_number,
                for_vve=False,
            )
            run_id = pipeline_job.name

            # Poll the pipeline status
            full_pipeline = ml_client.jobs.get(run_id)
            pipeline_status = full_pipeline.status
            suffix = ""
            cancel_placeholder.button(
                "Annuleer", on_click=cancel_run, args=[ml_client, run_id, progress_bar, progress_percentage]
            )

            # Keep polling until pipeline completes
            while pipeline_status not in ["Completed", "Failed", "CancelRequested", "Canceled"]:
                child_jobs = []

                child_jobs_iterator = ml_client.jobs.list(parent_job_name=run_id)
                for child_job in child_jobs_iterator:
                    child_jobs.append(
                        {
                            "name": child_job.name,
                            "id": child_job.id,
                        }
                    )

                if len(child_jobs) == 1:
                    progress_text = "Transcriberen... dit kan meer dan een half uur duren..."
                    progress_percentage = 33
                    suffix = (
                        " bij het transcriberen. Check of er iets mis is met je audio/video bestand (speel het af)."
                    )
                elif len(child_jobs) == 2:
                    progress_text = "Notulen genereren... dit kan een paar minuten duren..."
                    progress_percentage = 75
                    suffix = " bij het genereren van notulen (transcriberen ging wel goed)."

                progress_bar.progress(progress_percentage, text=progress_text)
                pipeline_status = ml_client.jobs.get(run_id).status
                time.sleep(2)

            completed = False
            if pipeline_status == "Completed":
                progress_bar.progress(100, text=":green[Klaar met genereren.]")
                completed = True
            elif pipeline_status == "Failed":
                progress_bar.progress(progress_percentage, text=f":red[Gefaald{suffix}]")
            elif pipeline_status in ["CancelRequested", "Canceled"]:  # so this doesn't work yet
                progress_bar.progress(progress_percentage, text=":red[Geannuleerd. Ververs pagina.]")

    if completed:
        status_placeholder.empty()
        cancel_placeholder.empty()
        info_placeholder.info(
            f"**Klaar!** De conceptnotulen zijn per e-mail naar je verstuurd. Niet ontvangen? Controleer ook je spamfolder."
        )


def cancel_run(ml_client: MLClient, run_id: str, progress_bar: DeltaGenerator, progress_percentage: int):
    """Cancel the Azure ML pipeline and stop the app."""
    ml_client.jobs.begin_cancel(run_id)  # this cancels the job.
    progress_bar.progress(progress_percentage, text=":red[Geannuleerd. Ververs pagina.]")
    st.stop()


def change_state_and_disable_button():
    """Wanneer de "Start genereren" button wordt ingedrukt, wordt eerst deze functie uitgevoerd en daarna wordt het
    script gererund. Als je if st.button(..) gebruikt dan doet hij eerst een script rerun voordat hij de code na de if
    statement uitvoert. Als je "on_click" gebruikt, zoals nu, dan is er geen onmiddelijke script rerun, maar pas na het
    uitvoeren van de functie.

    In deze functie wordt de session state aangepast, zodat de "start genereren" knop disabled wordt bij het rerunnen
    van het script, en het proces (process_files) gestart wordt.

    Update: dit is niet echt relevant meer, nu gooien we de knop weg als die is ingedrukt.
    """
    st.session_state.start_button_pressed = True


def create_agenda_dict(points: list[tuple[str, str]]) -> dict[str, dict[str, str]]:
    """Create a dictionary from the parsed agenda points."""
    agenda_dict = {}
    for header, body in points:
        nummer_indicator = header.split(".")[0]
        agenda_dict[nummer_indicator] = {
            "body": body.strip() if body else "",
            "titel": header.strip(),
        }

    return agenda_dict


def parse_agenda(text: str | None) -> list[tuple[str, str]]:
    """Find all agenda headers and their positions."""
    if text is None:
        return []
    matches = list(re.finditer(r"^(?P<header>\d+[a-zA-Z]?\. .+)", text, re.MULTILINE))
    results = []
    for i, match in enumerate(matches):
        header = match.group("header").strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        # Description is the text between this header and the next header
        description = text[start:end].strip()
        results.append((header, description))

    return results


def check_upload(audio_files: list):
    """Check of de geselecteerde audio/videobestanden voldoen aan de eisen.

    De bestanden zijn geselecteerd in de custom Streamlit component en nog niet geupload. Toon het resultaat in
    streamlit
    """
    time.sleep(2)  # to prevent glitches
    audio_files_approved = False
    if len(audio_files) >= 1:
        succesful, message = check_audio_files(audio_files)
        if succesful:
            audio_files_approved = True

    else:
        message = "Geen opnamebestand gevonden."

    if audio_files_approved:
        st.session_state.enable_upload = True
        az = get_azure_helper()
        st.session_state.sas_urls = az.generate_multiple_urls(
            filenames=audio_files, timestamp=st.session_state.timestamp
        )

    st.session_state.check_upload_message = message


if "check_upload_message" not in st.session_state:
    st.session_state.check_upload_message = ""
if "start_button_pressed" not in st.session_state:
    st.session_state.start_button_pressed = False
if "timestamp" not in st.session_state:
    st.session_state.timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
if "process_files_started" not in st.session_state:
    st.session_state.process_files_started = False
if "agenda_text" not in st.session_state:
    st.session_state.agenda_text = None
if "agenda_valid" not in st.session_state:
    st.session_state.agenda_valid = False
if "aantal_agendapunten" not in st.session_state:
    st.session_state.aantal_agendapunten = 0
if "agendapunten" not in st.session_state:
    st.session_state.agendapunten = []
if "type_notulen" not in st.session_state:
    st.session_state.type_notulen = None
if "agenda_checked" not in st.session_state:
    st.session_state.agenda_checked = False
if "for_vve" not in st.session_state:
    st.session_state.for_vve = False
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "enable_upload" not in st.session_state:
    st.session_state.enable_upload = False
if "upload_pressed" not in st.session_state:
    st.session_state.upload_pressed = False
if "upload_completed" not in st.session_state:
    st.session_state.upload_completed = False
if "sas_urls" not in st.session_state:
    st.session_state.sas_urls = []
if "vve_number" not in st.session_state:
    st.session_state.vve_number = ""
if "checkbox_informed" not in st.session_state:
    st.session_state.checkbox_informed = False
if "checkbox_proportional" not in st.session_state:
    st.session_state.checkbox_proportional = False
if "upload_component_loaded" not in st.session_state:  # whether the upload component has been loaded at least once
    st.session_state.upload_component_loaded = False

st.markdown("# 🖋️ Notulen Generator")

agenda_aanleveren_placeholder = st.empty()
agenda_recognized_placeholder = st.empty()
notulen_type_placeholder = st.empty()
upload_component_placeholder = st.empty()
checkbox_placeholder = st.empty()
start_button_placeholder = st.empty()
status_placeholder = st.empty()
cancel_placeholder = st.empty()
info_placeholder = st.empty()


with agenda_aanleveren_placeholder.container():
    st.markdown(
        """
        **Instructies:**

        Lever hieronder de agendapunten aan. 
        
        Een agendapunt bestaat uit een **nummeraanduiding**, **titel** en daaronder een (optionele) **beschrijving**. Zie het voorbeeld hieronder.

        Druk na het invoeren van de agendapunten op `Controleren` om te zien of de agendapunten juist zijn ingevoerd. Zie je alle agendapunten terug, ga dan verder.
        """
    )
    st.markdown("###### Voorbeeld:")
    st.markdown(
        """
        ```
        1. Eerste agendapunt
        Beschrijving van het agendapunt.
        De beschrijving mag uit meerdere regels bestaan.

        2. Volgende agendapunt
        Beschrijving van het volgende agendapunt.

        3a. Agendapunt met een letter
        Beschrijving van het agendapunt met een letter.

        3b. Volgend agendapunt met een letter, zonder beschrijving.
        ```
        """
    )

    st.text_area(
        "Voer de agendapunten in zoals het format hierboven:",
        value=st.session_state.agenda_text,
        key="agenda_text",
        placeholder="",
        height=300,
    )

    # Step 1: Agenda controleren
    if st.button("Controleren", type="secondary"):
        agendapunten = parse_agenda(st.session_state.agenda_text)
        st.session_state.agenda_valid = len(agendapunten) > 0
        st.session_state.aantal_agendapunten = len(agendapunten)
        st.session_state.agendapunten = agendapunten
        st.session_state.agenda_checked = True
        if not st.session_state.agenda_valid:
            st.error("Geen geldige agendapunten gevonden. Controleer je invoer.")
        else:
            st.success(f"{len(agendapunten)} agendapunten gevonden.")

with agenda_recognized_placeholder.container():
    # Show found agendapunten only after checking
    if st.session_state.agenda_checked and st.session_state.agenda_valid:
        st.subheader("Gevonden agendapunten:")
        for idx, (header, body) in enumerate(st.session_state.agendapunten):
            st.markdown(
                f"<div style='background-color: hsl({idx*60%360},70%,90%);"
                f"padding:10px; margin-bottom:5px; border-radius:5px;'>"
                f"<h5>{header}</h5> {body.replace(chr(10), '<br>')}</div>",
                unsafe_allow_html=True,
            )
        st.markdown(f"Er zijn in totaal **{st.session_state.aantal_agendapunten}** agendapunten gevonden.")

with notulen_type_placeholder.container():
    # Step 2: Type notulen kiezen
    if st.session_state.agenda_checked and st.session_state.agenda_valid:
        st.markdown("### Hoe wil je dat de notulen worden opgesteld?")
        st.radio(
            "Kies het type notulen:",
            options=["Kort en bondig", "Meer uitgebreid"],
            key="type_notulen",
            horizontal=True,
        )
        if st.session_state.type_notulen == "Kort en bondig":
            st.markdown("*We genereren korte, bondige notulen.*")
        elif st.session_state.type_notulen == "Meer uitgebreid":
            st.markdown("*We genereren notulen met meer details en context.*")

with upload_component_placeholder.container():
    if st.session_state.agenda_checked and st.session_state.agenda_valid and st.session_state.type_notulen is not None:
        if not st.session_state.upload_component_loaded:
            with st.spinner("Even geduld..."):
                time.sleep(6)  # wait a bit for the component to load properly to prevent glitches

        agenda_aanleveren_placeholder.empty()
        st.markdown("### Upload nu je opname-bestanden.")
        st.markdown(
            "De opname mag zowel audio als video zijn. Hierbij is het mogelijk dat de opname uit meerdere bestanden bestaat. "  # noqa:E501
            "Als de opname uit meerdere bestanden bestaat, dan moeten deze oplopend genummerd zijn. "
            "Toegestane bestandstypes: `mp3`, `wav`, `mpeg`, `m4a`, `mp4`, `webm`, `mpga`"
        )
        st.markdown("Voorbeeld: `1.wav, 2.wav, 3.wav`")

        # NB: when running locally, you should run on port 8501 because that is added as a
        # CORS rule in Azure Storage (see the Confluence page).
        component_output = blob_storage_upload_component(
            sas_urls=st.session_state.sas_urls,
            enable_upload=st.session_state.enable_upload and not st.session_state.upload_pressed,
            key="my_upload_component",  # Je kan met de key differentieren tussen meerdere componenten in de app.
        )

        # Extract filenames and uploadPressed from the returned value
        uploaded_filenames = []
        upload_pressed = False
        if isinstance(component_output, dict):
            st.session_state.uploaded_files = component_output.get("filenames", [])
            # Only set upload_pressed to True, never back to False
            if component_output.get("uploadPressed", False):
                st.session_state.upload_pressed = True
            if component_output.get("uploadCompleted", False):
                st.session_state.upload_completed = True
        else:
            pass  # component is not filled with a file yet.

        check_upload_button = st.empty()
        with check_upload_button.container():
            if st.session_state.uploaded_files != []:
                st.button(
                    "Check geselecteerde bestanden",
                    type="secondary",  # kleur van de knop
                    on_click=check_upload,
                    args=[st.session_state.uploaded_files],
                    help="Check of je geselecteerde bestanden geschikt zijn.",
                )

            if st.session_state.check_upload_message != "" and not st.session_state.upload_pressed:
                if st.session_state.enable_upload:
                    st.success(st.session_state.check_upload_message)
                else:
                    st.error(st.session_state.check_upload_message)

        if st.session_state.upload_pressed:
            check_upload_button.empty()

# Step 3: Start genereren knop

# --- Verplichte checkboxes ---
with checkbox_placeholder.container():
    if st.session_state.upload_completed:
        st.checkbox(
            "Ik verklaar dat ik alle deelnemers heb geïnformeerd over het gebruik van de notulen generator.",
            value=False,
            key="checkbox_informed",
        )
        st.checkbox(
            "Per uur aan geluidsopname zijn de kosten voor de Alliantie ongeveer €1,20. Hierbij verklaar ik dat dat proportioneel is.",
            value=False,
            key="checkbox_proportional",
        )

disable_start_genereren_notulen = (
    st.session_state.start_button_pressed
    or not st.session_state.agenda_checked
    or not st.session_state.agenda_valid
    or st.session_state.type_notulen is None
    or not st.session_state.upload_completed
    or not st.session_state.checkbox_informed
    or not st.session_state.checkbox_proportional
)

with start_button_placeholder.container():
    st.button(
        "Start genereren notulen",
        type="primary",
        disabled=(disable_start_genereren_notulen),
        on_click=change_state_and_disable_button,
        help="Je hebt nog niet alle informatie aangeleverd." if disable_start_genereren_notulen else "",
    )


# ---------------------- Start -------------------------------------------------------

timestamp = st.session_state.timestamp

if st.session_state.start_button_pressed and not st.session_state.process_files_started:

    agenda_recognized_placeholder.empty()
    notulen_type_placeholder.empty()
    upload_component_placeholder.empty()
    checkbox_placeholder.empty()
    start_button_placeholder.empty()
    st.session_state.process_files_started = True
    agenda_dict = create_agenda_dict(st.session_state.agendapunten)
    az = get_azure_helper()
    az.upload_dict_to_blob_storage(folder_path=f"{timestamp}/input", filename="agendapunten.json", my_dict=agenda_dict)
    az.upload_file_to_blob_storage(
        folder_path=f"{timestamp}/processed_input_docs", filename="agenda.md", data=st.session_state.agenda_text
    )
    start_pipeline(timestamp)
