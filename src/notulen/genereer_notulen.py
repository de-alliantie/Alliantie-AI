import base64
import json
import os
from datetime import datetime
from pathlib import Path
from time import time
from typing import Dict, List, Optional

import requests

# from msal import ConfidentialClientApplication
from azure.identity import DefaultAzureCredential
from mldesigner import Input, Output

from notulen.utils.splits_utils import (
    apply_gpt_split,
    create_agenda_groups,
    extract_agendapunten,
)
from notulen.utils.utilities import (
    convert_from_pdf_to_markdown,
    convert_stuff_to_docx_for_stakeholders,
    convert_to_docx,
    get_splitsing_prompt,
    load_transcript,
    make_llm_call,
    new_trial_nr,
    process_llm_output,
)
from shared.my_logging import logger
from shared.utils import init_openai_client

# For local development, we can use "trials" of specific parts of the process
# so that we don't need to do a full run every time. For example, if you tried the part of splitting the transcript
# and it worked, you can set the trial to that number and it will use the existing splits.
SPLITS_TRIAL = None
NOTUL_TRIAL = None


def full_pipeline(input_folder: Input(type="uri_folder"), output_folder: Output(type="uri_folder")):  # noqa:F821
    """Doe alles na het transcriberen.

    Dus let op: het agendabestand, de opname en het transcript moeten klaar staan.
    De opname staat dan in data/foldernaam/input en de agenda in data/foldernaam/input/opname.
    Als je een custom agenda gebruikt, zet het in data/foldernaam/input/agenda.txt
    """
    logger.info("\n\n\n\n Notulen pipeline entered \n\n\n\n")
    input_folder = Path(output_folder)  # for local development, don't do this
    logger.info(input_folder.stem)
    start = time()
    if os.environ["for_vve"] == "True":
        for_vve = True
        convert_from_pdf_to_markdown(input_folder)
        agenda_splitsing = extract_agendapunten(input_folder)
    else:
        for_vve = False
        with open(input_folder / "input/agendapunten.json", "r") as f:
            agenda_splitsing = json.load(f)

    if SPLITS_TRIAL is None:
        gpt_dict, splits_path = get_gpt_split(input_folder, agenda_splitsing, for_vve)
    else:
        splits_path = input_folder / "splitsing" / str(SPLITS_TRIAL)
        with open(splits_path / "interval_split_llm_output.json", "r") as json_file:
            gpt_dict = json.load(json_file)

    transcript_lines = load_transcript(input_folder, numbered=False)
    transcript_lines_numbered = load_transcript(input_folder, numbered=True)
    transcript_gesplitst_dict = apply_gpt_split(transcript_lines, gpt_dict, splits_path)
    transcript_gesplitst_numbered_dict = apply_gpt_split(transcript_lines_numbered, gpt_dict, splits_path)

    with open(splits_path / "resultaat splitsing.md", "w") as f:
        for key, value in transcript_gesplitst_numbered_dict.items():
            agendapunt_titel = agenda_splitsing[key]["titel"]
            f.write(f"# {agendapunt_titel}\n\n\n\n{value}\n\n\n\n")

    type_notulen = os.environ["type_notulen"]

    notulen_output_path = genereer_notulen(
        input_folder, transcript_gesplitst_dict, agenda_splitsing, type_notulen, for_vve
    )
    logger.info(f"Total time full_pipeline: {round((time()-start)/60,1)} min")
    convert_stuff_to_docx_for_stakeholders(input_folder, splits_path, notulen_output_path)

    email = os.environ["email"]

    send_notulen_to_email(output_folder=input_folder, email=email)


def send_notulen_to_email(output_folder: Path, email: str):
    """Sends the notulen.docx to the specified email address."""

    token = get_token()
    timestamp = os.environ.get("timestamp")
    timestamp_formatted = datetime.strptime(timestamp, "%Y-%m-%d_%H%M%S").strftime("%d-%m-%Y %H:%M:%S")

    filepath = output_folder / "result" / "notulen.docx"

    send_mail(
        to_email=email,
        email_subject=f"Alliantie AI - Gegenereerde notulen - {timestamp_formatted}",
        email_body=f"Hierbij ontvang je de conceptnotulen van de vergadering die je op {timestamp_formatted} instuurde via Alliantie AI. Vragen of opmerkingen? Stuur ons een berichtje via dcc@de-alliantie.nl.",  # noqa: E501
        token=token,
        attachments=[{"Name": f"notulen_{timestamp}.docx", "file_path": str(filepath)}],
    )


def get_token() -> str:
    """Acquire token for Power Automate (same audience as Microsoft Flow)"""
    scope = "https://service.flow.microsoft.com//.default"
    credential = DefaultAzureCredential()
    token = credential.get_token(scope).token

    logger.info("Token acquired successfully!")

    return token


def send_mail(
    to_email: str, email_subject: str, email_body: str, token: str, attachments: Optional[List[Dict[str, str]]] = None
) -> Dict:
    """Sends an email using Power Automate flow via HTTP trigger.

    Args:
        to_email (str): Email address of the recipient
        email_subject (str): Subject line of the email
        email_body (str): Content of the email
        attachments (List[Dict[str, str]], optional): List of attachment dictionaries.
            Each dict should have 'Name' and either 'file_path' OR 'ContentBytes'.
            If 'file_path' is provided, function will read and encode the file.
            If 'ContentBytes' is provided, it should already be base64 encoded.

    Returns:
        Dict: Response from the Power Automate flow

    Example:
        attachments = [
            {'Name': 'report.pdf', 'file_path': '/path/to/report.pdf'},
            {'Name': 'data.csv', 'ContentBytes': 'already_encoded_base64_string'}
        ]
        response = send_mail('recipient@example.com', 'Your Report', 'Please see attached.', attachments)
    """
    # Power Automate flow trigger URL
    flow_url = os.environ["POWER_AUTOMATE_SEND_EMAIL_FLOW_URL"]
    logger.info(f"Flow URL: {flow_url}")

    # Process attachments if provided
    processed_attachments = []
    if attachments:
        for attachment in attachments:
            attachment_data = {}
            attachment_data["Name"] = attachment["Name"]

            # If file_path is provided, read and encode the file
            if "file_path" in attachment:
                try:
                    with open(attachment["file_path"], "rb") as file:
                        file_content = file.read()
                        attachment_data["ContentBytes"] = base64.b64encode(file_content).decode("utf-8")
                except Exception as e:
                    logger.info(f"Error processing attachment {attachment['Name']}: {str(e)}")
                    continue
            # If ContentBytes is already provided, use it directly
            elif "ContentBytes" in attachment:
                attachment_data["ContentBytes"] = attachment["ContentBytes"]
            else:
                logger.info(f"Skipping attachment {attachment['Name']} - no file_path or ContentBytes provided")
                continue

            processed_attachments.append(attachment_data)

    # # Prepare the payload
    payload = {"email_subject": email_subject, "email_body": email_body, "to_email": to_email}

    # Add attachments if any were processed successfully
    if processed_attachments:
        payload["attachments"] = processed_attachments

    # Set headers
    # Add the token to your request
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        # Send the request to Power Automate flow
        response = requests.post(flow_url, headers=headers, data=json.dumps(payload))

        # Check if the request was successful
        response.raise_for_status()
        resp = {
            "status_code": response.status_code,
            "response": response.json() if response.text else "No response content",
            "success": True,
        }
        logger.info(resp)

        # Return the response
        return {
            "status_code": response.status_code,
            "response": response.json() if response.text else "No response content",
            "success": True,
        }

    except requests.exceptions.RequestException as e:
        error_message = str(e)
        response_text = getattr(e.response, "text", "No response text") if hasattr(e, "response") else "No response"

        logger.info(response_text)
        return {
            "status_code": getattr(e.response, "status_code", None) if hasattr(e, "response") else None,
            "error": error_message,
            "response": response_text,
            "success": False,
        }


def get_gpt_split(folder_path: Path, agenda_splitsing: dict, for_vve: bool) -> tuple[dict, Path]:
    """Splits het transcript en verbind stukjes van het transcript met agendapuntnummers."""
    # splits agendapuntnummers in groepjes, want in 1x prompten gaat niet goed
    agendapuntnummers = list(agenda_splitsing.keys())
    trial = new_trial_nr(folder_path / "splitsing")
    logger.info(f"Trial {trial} voor splitsing.")
    splits_path = folder_path / "splitsing" / trial
    splits_path.mkdir(exist_ok=True, parents=True)
    openai_client = init_openai_client()
    agendapuntnummers_groups = create_agenda_groups(agendapuntnummers, groupsize=4)
    gpt_dict = {}  # dit wordt de dict van de splitsing
    subsplits = []
    for agendapuntnummers_group in agendapuntnummers_groups:
        prompt, _ = get_splitsing_prompt(folder_path, agendapuntnummers_group, for_vve)
        split_by_llm = make_llm_call(
            openai_client, prompt, reason="splitsen " + str(agendapuntnummers_group), notulen=False
        )
        subsplits.append(split_by_llm)
        (splits_path / "splitsing output LLM.txt").write_text(
            "\n\n".join("\n".join(f"{k}: {v}" for k, v in split_by_llm.items()) for split_by_llm in subsplits)
        )

        update = {k: v for k, v in split_by_llm.items() if k in agendapuntnummers_group and k not in gpt_dict}
        gpt_dict.update(update)

        with open(splits_path / "interval_split_llm_output.json", "w") as json_file:
            json.dump(gpt_dict, json_file, indent=4)

    return gpt_dict, splits_path


def genereer_notulen(
    folder_path: Path, transcript_gesplitst_dict: dict, agenda_splitsing: dict, type_notulen: str, for_vve: bool
) -> Path:
    """Generate the meeting notes # TODO: als transcript en agendasplitsing niet dezelfe keys hebben, dan raise
    error."""
    trial = new_trial_nr(folder_path / "output_notulen") if NOTUL_TRIAL is None else str(NOTUL_TRIAL)
    logger.info(f"Trial {trial} voor notulen genereren.")
    output_path = folder_path / "output_notulen" / trial
    output_path.mkdir(exist_ok=True, parents=True)

    if type_notulen == "Kort en bondig":
        if for_vve:
            prompt_template = (Path(__file__).parent / "prompts/prompt_notulen_stukje_kort_vve.md").read_text()
        else:
            prompt_template = (Path(__file__).parent / "prompts/prompt_notulen_stukje_kort.md").read_text()
    elif type_notulen == "Meer uitgebreid":
        if for_vve:
            prompt_template = (Path(__file__).parent / "prompts/prompt_notulen_stukje_uitgebreid_vve.md").read_text()
        else:
            prompt_template = (Path(__file__).parent / "prompts/prompt_notulen_stukje_uitgebreid.md").read_text()
    else:
        # Load default long prompt template when unspecified
        prompt_template = (Path(__file__).parent / "prompts/prompt_notulen_stukje_uitgebreid.md").read_text()

    (output_path / "prompt template notulen.txt").write_text(prompt_template)

    if for_vve:
        output_md = f"# VvE {os.environ.get('vve_number','')}\n\n"
    else:
        output_md = "# Notulen\n\n"
    for agendapunt_nr, content in agenda_splitsing.items():
        prev_generated = output_path / f"{trial} nr {agendapunt_nr}.md"  # previously/already generated
        if prev_generated.exists():
            output = prev_generated.read_text()
            logger.info(f"Read already generated: {agendapunt_nr}")
        elif agendapunt_nr in transcript_gesplitst_dict:
            stukje_transcript = transcript_gesplitst_dict[agendapunt_nr]
            output = genereer_notulen_stukje(
                folder_path, content, agendapunt_nr, stukje_transcript, prompt_template, trial
            )
            (output_path / f"{trial} nr {agendapunt_nr}.md").write_text(output)
            logger.info(f"Generated: agendapunt {agendapunt_nr}")
        else:
            output = f"Agendapunt {agendapunt_nr} niet als agendapunt gedetecteerd in transcript."
            logger.warning(output)
        output_md += f"## {content['titel']}\n\n{output}\n\n"
        (output_path / "notulen.md").write_text(output_md)
        convert_to_docx(output_path / "notulen.md")
    return output_path


def genereer_notulen_stukje(
    folder_path: Path,
    agenda_content: dict,
    agendapunt_nr: str,
    stukje_transcript: str,
    prompt_template: str,
    trial: str,
) -> str:
    """Generates a part of the notes."""
    openai_client = init_openai_client()
    agenda_str = f"**{agenda_content['titel']}**\n\n{agenda_content['body']}"
    prompt = prompt_template.format(
        agendapunt=agenda_str,
        transcript=stukje_transcript,
    )
    (folder_path / "output_notulen" / trial).mkdir(exist_ok=True)
    (folder_path / "output_notulen" / trial / f"{trial} prompt {agendapunt_nr}.txt").write_text(prompt)
    output = make_llm_call(openai_client, prompt, reason=f"stukje notulen, nr {agendapunt_nr}", notulen=True)
    output_processed = process_llm_output(output)
    return output_processed


if __name__ == "__main__":
    # Example usage
    VVE = "1234"
    os.environ["vve_number"] = VVE
    os.environ["timestamp"] = "testtimestamp"
    folder = Path(f"data/{VVE}")
    full_pipeline(folder, folder)
