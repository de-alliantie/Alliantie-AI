import hashlib
import os
import time
import uuid
from datetime import datetime
from random import random
from typing import Callable, Generator

import openai
import requests
import streamlit as st
from helpers_webapp import FailSavingChat, container_client, save_metadata, set_styling
from openai.types.responses import Response, ResponseCreatedEvent, ResponseOutputMessage
from openai.types.responses.response_code_interpreter_call_in_progress_event import (
    ResponseCodeInterpreterCallInProgressEvent,
)
from openai.types.responses.response_file_search_call_in_progress_event import (
    ResponseFileSearchCallInProgressEvent,
)
from openai.types.responses.response_file_search_tool_call import (
    ResponseFileSearchToolCall,
)
from openai.types.responses.response_output_item_added_event import (
    ResponseOutputItemAddedEvent,
)
from openai.types.responses.response_output_text import ResponseOutputText
from openai.types.responses.response_reasoning_item import ResponseReasoningItem
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from shared.utils import encode_file_b64, init_openai_client
from veilig_chatgpt.settings import (
    DATA_EXTENSIONS,
    IMAGE_EXTENSIONS,
    LLM_CHOICE,
    OTAP,
    RETRIEVAL_EXTENSIONS,
)


class Content:
    """Wrapper for the response content."""

    def __init__(self, type, filename=None, message_text=None, image=None, annotations=None, quotes=[]):
        """Initialize."""
        self.type = type

        if self.type == "image_file":
            self.filename = filename
            self.image = image
        elif self.type == "refusal":
            self.message_text = message_text
        elif self.type == "output_text":
            self.message_text = message_text
            self.annotations = annotations
            self.quotes = quotes


class Quote:
    """Een quote/chunk die je krijgt uit een zoekresultaat."""

    def __init__(self, filename, text, score):
        """Initialize."""
        self.filename = filename
        self.text = text
        self.score = score  # de score van hoe relevant de chunk is


class Annotation:
    """Class for an annotation.

    This can be a file citation or an AI generated file.
    """

    def __init__(self, index, type, filename, filecontent):
        """Initialises the object."""
        self.index = index
        self.type = type
        self.filename = filename
        self.filecontent = filecontent


set_styling()

INITIAL_MESSAGES = [
    {
        "role": "assistant",
        "content": Content(type="output_text", message_text="Waar kan ik je mee helpen?", annotations=[]),
    }
]

st.markdown("# 💬 Veilig ChatGPT gebruiken")
if datetime.now() < datetime(2025, 11, 1):  # tijdelijke melding
    st.info(
        "✨ Nieuw: de limiet van 10 documenten als bijlage is opgeheven. Je kunt nu (bijna) onbeperkt documenten uploaden.",  # noqa: E501
    )
st.info(
    "Let op! Veilig ChatGPT heeft geen toegang tot het internet of Alliantie-data. Alleen door jezelf geüploade bestanden worden geraadpleegd.",  # noqa: E501
    icon=":material/info:",
)


if "gpt_version" not in st.session_state:
    st.session_state.gpt_version = list(LLM_CHOICE.keys())[0]

if "safechat_messages" not in st.session_state:
    st.session_state.safechat_messages = INITIAL_MESSAGES

if "previous_response_id" not in st.session_state:
    st.session_state.previous_response_id = None

if "file_list" not in st.session_state:
    st.session_state.file_list = []  # list of dicts: {"file_id", "file_name", "processed"}

if "vector_store_id" not in st.session_state:
    st.session_state.vector_store_id = None

if "processed_messages" not in st.session_state:
    st.session_state.processed_messages = []

if "freeze_selectbox" not in st.session_state:
    st.session_state.freeze_selectbox = False  # bevries de selectbox van de gpt versie wanneer de chat is gestart

if "block_chat_input" not in st.session_state:
    st.session_state.block_chat_input = False

if "file_uploader_key" not in st.session_state:  # deze wordt gebruikt om de file uploader te resetten bij nieuwe chat.
    st.session_state.file_uploader_key = str(random())


if "allowed_extensions" not in st.session_state:
    st.session_state.allowed_extensions = (
        RETRIEVAL_EXTENSIONS[:4] + DATA_EXTENSIONS + RETRIEVAL_EXTENSIONS[4:] + IMAGE_EXTENSIONS
    )
if "blob_client" not in st.session_state:
    st.session_state["blob_client"] = container_client()

if "session_uuid" not in st.session_state:
    st.session_state["session_uuid"] = f"""{datetime.now().strftime("%Y%m%d%H%M%S")}_{str(uuid.uuid4())}"""

if "user" not in st.session_state:
    st.session_state.user = {}

if "UserPrincipalName" not in st.session_state.user or st.session_state.user["UserPrincipalName"] == "":
    headers = st.context.headers
    user_email = headers.get("X-Ms-Client-Principal-Name")

    if user_email:
        st.session_state.user["userPrincipalName"] = user_email
    else:
        st.session_state.user["userPrincipalName"] = ""


@st.cache_resource
def get_client() -> openai.OpenAI:
    """Get the AzureOpenAI client and cache it in Streamlit."""
    client = init_openai_client()
    return client


def reset_conversation():
    """Resets the state so a new conversation can be started."""
    st.session_state.safechat_messages = INITIAL_MESSAGES
    st.session_state.processed_messages = []
    st.session_state.file_list = []
    st.session_state.freeze_selectbox = False
    st.session_state.block_chat_input = False
    st.session_state.file_uploader_key = str(random())
    st.session_state.previous_response_id = None


def llm_call(prompt: str) -> Callable[[], Generator[str, None, None]]:
    """Make LLM call using the Responses API. Return an event generator and a function to get the final responses (LLM
    can give multiple messages). The event generator streams the events from the Responses API call, which can be used
    to display the response in real-time. The function to get the final responses will be used when streaming is done to
    overwrite the streamed content with the final responses, processed with citations and AI generated files.

    Look for file attachments first and finish processing them here (the processing started outside of this function,
    when they were uploaded by the user). If there are files, check if they are retrieval files (documents) or tabular
    data files (Excel, CSV) or images. For retrieval files, we add the vector store to the request. For tabular data
    files, we add the file_id's to the code interpreter tool. For images, we encode them in base64 and add that to the
    request.

    We always enable the code interpreter tool (e.g. for data analysis).
    """
    content = [{"type": "input_text", "text": prompt}]
    tools = [{"type": "code_interpreter", "container": {"type": "auto"}}]
    data_file_list = []  # file_id's of excel files and other tabular data files

    if len(st.session_state.file_list) > 0:
        for i, file_info in enumerate(st.session_state.file_list):
            file_id = file_info["file_id"]
            file_name = file_info["file_name"]
            processed = file_info["processed"]
            if not processed:
                if file_name.endswith(tuple(RETRIEVAL_EXTENSIONS)):
                    tools.append(
                        {
                            "type": "file_search",
                            "vector_store_ids": [st.session_state.vector_store_id],
                            "max_num_results": st.session_state.search_k,
                        }
                    )
                elif file_name.endswith(tuple(IMAGE_EXTENSIONS)):
                    content.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{file_info.get('b64_encoded_file')}",
                            "detail": st.session_state.image_quality,  # optional, can be 'low' or 'high' or 'auto'
                        }
                    )
                elif file_name.endswith(tuple(DATA_EXTENSIONS)):
                    data_file_list.append(file_id)
                # Set processed state to True
                st.session_state.file_list[i]["processed"] = True
        if len(data_file_list) > 0:
            tools[0] = {  # replace the code interpreter tool to include the data files
                "type": "code_interpreter",
                "container": {"type": "auto", "file_ids": data_file_list},
            }
    client = get_client()

    stream = client.responses.create(
        model=LLM_CHOICE[st.session_state.gpt_version],
        tools=tools,
        previous_response_id=st.session_state.previous_response_id,
        input=[{"role": "user", "content": content}],
        # include=["file_search_call.results"], # not needed now, we retrieve it later
        stream=True,
    )

    def event_generator() -> Generator:
        """Generator function to stream events from the run."""
        file_search_shown = False
        code_interpreter_shown = False
        reasoning_shown = False
        buffer = ""
        for event in stream:
            if isinstance(event, ResponseCreatedEvent):
                st.session_state.previous_response_id = event.response.id

            # Visualize tool usage (show only once per tool per run)
            elif isinstance(event, ResponseCodeInterpreterCallInProgressEvent) and not code_interpreter_shown:
                code_interpreter_shown = True
                yield "  \n 💻 Code schrijven...  \n"

            elif isinstance(event, ResponseFileSearchCallInProgressEvent) and not file_search_shown:
                file_search_shown = True
                yield "  \n 🔎 Bestanden doorzoeken...  \n"

            elif isinstance(event, ResponseOutputItemAddedEvent):
                item = getattr(event, "item", None)
                if item and isinstance(item, ResponseReasoningItem) and not reasoning_shown:
                    reasoning_shown = True
                    yield "  \n 🤔 Reasoning...  \n"

            # Existing message streaming
            elif isinstance(event, ResponseTextDeltaEvent):
                delta = getattr(event, "delta", None)
                if delta:

                    # Check for missing space between sentences
                    if (
                        buffer
                        and (buffer[-1] == "." or buffer[-1] == "!" or buffer[-1] == "?")
                        and delta
                        and delta[0].isupper()
                    ):
                        # If the last character in the buffer is a sentence-ending punctuation,
                        # # and the first character in the delta is an uppercase, add a whitepsace
                        if delta:  # delta can be None
                            buffer = f" {delta}"
                            yield buffer

                    # No missing space, set the buffer to the delta
                    else:
                        if delta:  # delta can be None
                            buffer = delta
                            yield buffer
                    # yield delta

    return event_generator


def get_final_responses() -> list[Content]:
    """Get the final responses after the run is completed."""

    response = retrieve_response_with_backoff(client)

    responses = []
    file_search_results = []
    for message_data in response.output:
        if isinstance(message_data, ResponseFileSearchToolCall):
            results = getattr(message_data, "results", None)
            if results:
                file_search_results.extend(results)
            continue
        elif not isinstance(message_data, ResponseOutputMessage):
            continue

        if message_data.role == "user":
            continue
        if message_data.role == "assistant":
            if message_data.id not in st.session_state.processed_messages:
                for content in message_data.content:
                    parsed_content = parse_content(content, file_search_results)
                    responses.append(parsed_content)
                st.session_state.processed_messages.append(message_data.id)
    return responses


def retrieve_response_with_backoff(client: openai.OpenAI) -> Response | None:
    """Retrieve the response.

    Keep trying with exponential backoff in case of NotFoundError.
    """
    max_attempts = 8
    attempt = 0
    response = None
    while attempt < max_attempts:
        try:
            response = client.responses.retrieve(
                st.session_state.previous_response_id, include=["file_search_call.results"]
            )
            break  # Success
        except openai.NotFoundError:
            attempt += 1
            if attempt == max_attempts:
                raise
            time.sleep(0.5 * (2 ** (attempt - 1)))  # Exponential backoff: 0.5s, 1s, 2s, etc.

    return response


def retrieve_file_from_container(container_id: str, file_id: str) -> bytes:
    """Return the bytes string of an AI generated file.

    Using the Responses API, the LLM will work in a sandboxed container to run the code interpreter tool and generate
    files when requested.
    """
    url = f"{os.environ['OPENAI_SWEDEN_ENDPOINT']}/openai/v1/containers/{container_id}/files/{file_id}/content"
    headers = {"Authorization": f"Bearer {os.environ.get('OPENAI_SWEDEN')}"}
    response = requests.get(url, headers=headers)
    if not response.status_code == 200:
        print(f"Error: {response.status_code} - {response.text}")

    return response.content


def parse_content(content: ResponseOutputText, file_search_results: list) -> Content | None:
    """Parses the content dependend on the type.

    If the LLM invoked the file search tool, then: (1) process the file search results to show the quotes (chunks) that
    were used to answer the question; and (2) process the annotations (of the type file_citation) to insert the
    citations [1], [2] etc. at the right place in the text. If there are AI generated files ('annotation' of the type
    'container_file_citation'), retrieve the file from the container.
    """
    if content.type == "refusal":
        parsed_content = Content(type=content.type, message_text="Ik weiger dit te beantwoorden.")
    elif content.type == "output_text":
        quotes = [
            Quote(
                filename=getattr(result, "filename", ""),
                text=getattr(result, "text", ""),
                score=getattr(result, "score", ""),
            )
            for result in file_search_results
        ]
        message_content = content
        message_text = message_content.text.strip('"')
        len_message_text = len(message_text)
        parsed_annotations = []
        annotations = message_content.annotations
        insert_at = None
        for index, annotation in enumerate(annotations):
            index += 1
            # An annotation can be the citation of a document, or an AI generated file
            # check the 'type' attribute of the annotation object to see which one it is

            # we insert the [1], [2] etc. at the right position in the text
            if annotation.type == "file_citation":
                if annotation.index == insert_at:  # duplicate annotations might happen
                    continue
                insert_at = annotation.index
                reversed_index = (
                    insert_at - len_message_text
                )  # count from the end of the string, otherwise the indices change when we insert [1], [2] etc.
                message_text = message_text[:reversed_index] + f"[{index}]" + message_text[reversed_index:]
                parsed_annotations.append(
                    Annotation(index=index, type="file_citation", filename=annotation.filename, filecontent="")
                )

            elif annotation.type == "container_file_citation":  # this is an AI generated file
                file = retrieve_file_from_container(annotation.container_id, annotation.file_id)
                parsed_annotations.append(
                    Annotation(
                        index=index, type="container_file_citation", filename=annotation.filename, filecontent=file
                    )
                )

        parsed_content = Content(
            type=content.type, message_text=message_text, annotations=parsed_annotations, quotes=quotes
        )
    else:
        parsed_content = None
        pass  # no other type is possible

    return parsed_content


def display_content(content: Content):
    """Displays a content object (answer from LLM).

    If the LLM invoked the file search tool, then display the quotes (chunks) that were used to answer the question in
    an expander and show the sources at the bottom of the answer. If there are AI generated files, show a download
    button. If an image file was generated, additionally, show the image.
    """
    if content.type == "refusal":
        st.write(content.message_text)

    elif content.type == "output_text":
        st.write(content.message_text)

        if hasattr(content, "annotations"):
            if content.annotations is not None:
                for annotation in content.annotations:
                    if annotation.type == "file_citation":
                        st.write(f"Bron: [{annotation.index}] {annotation.filename}")
                    elif annotation.type == "container_file_citation":  # if it is an AI generated file
                        if annotation.filename.endswith(tuple(IMAGE_EXTENSIONS)):  # if image, show image
                            st.image(annotation.filecontent)
                        st.download_button(
                            label=f"Download {annotation.filename}",
                            data=annotation.filecontent,
                            file_name=annotation.filename,
                            # unique key to prevent duplicate widget id
                            key=f"download_{annotation.filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        )
        if len(content.quotes) > 0:
            with st.expander("Dit zijn de stukken tekst die ik heb gelezen"):
                for quote in content.quotes:
                    st.write(f"### {quote.filename}")
                    st.write(quote.text)


def disable_stuff():
    """Disable the chat input box and disable the selection box for model selection.

    Do this after the user inputs his/her first message.
    """
    st.session_state.block_chat_input = True
    st.session_state.freeze_selectbox = True


with st.sidebar:
    st.button("Start nieuwe chat", on_click=reset_conversation)
    st.selectbox(
        "ChatGPT versie",
        LLM_CHOICE.keys(),
        key="gpt_version",
        disabled=st.session_state.freeze_selectbox,
        help="Volgorde van goedkoop naar duur is GPT-4.1 mini, GPT-4.1, GPT-5.",
    )

    with st.expander("Geavanceerde opties"):
        st.selectbox(
            "Hoeveel stukken brontekst wil je dat het model gebruikt voor het antwoord?",
            (1, 2, 3, 5, 10, 20),
            key="search_k",
            index=5,  # this is the default (index of the tuple)
            help="""
            Veilig ChatGPT kan antwoorden baseren op documenten die je uploadt.
            Om dit te doen deelt hij jouw documenten op in stukken tekst (chunks).
            Wanneer je een vraag stelt, worden de stukken opgehaald die het meest relevant zijn voor jouw vraag.
            Met deze knop controleer je hoeveel stukken gebruikt worden om je vraag te beantwoorden.
            Een prima keuze is 20. Dit is irrelevant als je niks uploadt, of als je bijv. een Excel uploadt.""",
        )
        image_quality_dict = {"Normaal (snel)": "low", "Hoog (langzaam)": "high"}
        selected_quality = st.selectbox(
            "Vision detail",
            list(image_quality_dict.keys()),
            index=0,  # default is "Normaal (snel)"
            help="""
            Veilig ChatGPT kan afbeeldingen bekijken en interpreteren.
            Met deze knop kies je de kwaliteit van de afbeelding die aan Veilig ChatGPT wordt doorgegeven.
            Met Normaal heb je het snelste antwoord. Met Hoog kan Veilig ChatGPT meer detail zien.
            """,
        )
        if selected_quality is not None:
            st.session_state.image_quality = image_quality_dict[selected_quality]
        else:
            st.session_state.image_quality = "low"  # fallback default

    upload_files_widget = st.file_uploader(
        label="Upload bestanden als bijlage.",
        type=st.session_state.allowed_extensions,
        accept_multiple_files=True,
        key=st.session_state.file_uploader_key,
        help="Upload bestanden om er vragen over te stellen, of vraag Veilig ChatGPT om aanpassingen te maken, documenten te vergelijken etc.",  # noqa:E501
    )

if st.session_state.gpt_version == "GPT-4.1 mini":
    pass
elif st.session_state.gpt_version == "GPT-4.1":
    st.info(
        "Deze versie van ChatGPT is beter dan `GPT-4.1 mini` maar ook iets duurder, heb je al geprobeerd je vraag via `GPT-4.1 mini` te stellen?",  # noqa:E501
        icon="🤖",
    )
elif st.session_state.gpt_version == "GPT-5":
    st.info(
        "Dit is de beste ChatGPT versie maar daarmee ook het duurste. Gebruik deze svp alleen als het niet lukt met `GPT-4.1 mini` of `GPT-4.1`.",  # noqa:E501
        icon="🤖",
    )

for message in st.session_state.safechat_messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["content"])
        else:
            display_content(message["content"])


prompt = st.chat_input(
    placeholder="Stel je vraag hier", on_submit=disable_stuff, disabled=st.session_state.block_chat_input
)
if prompt:
    st.chat_message("user").write(prompt)
    # Insert the message into streamlit memory
    st.session_state.safechat_messages.append({"role": "user", "content": prompt})

# ontraad de gebruiker om een geupload bestand te verwijderen
nr_of_currently_uploaded_files = len(st.session_state[st.session_state.file_uploader_key])
if nr_of_currently_uploaded_files < len(st.session_state.file_list):
    st.error("Let op: je geüploade bestanden worden onthouden. Wil je dit niet, start dan een nieuwe chat.")

# Process newly uploaded files. Check if the file is already uploaded by comparing the filename.
# Retrieval files (documents) need to be added to a vector store, whereas tabular data files need to be uploaded
# to be accessible by the code interpreter. Images are encoded in base64 and later
# included in the content of the prompt, at the moment the Responses API call is made.
# Therefore the file processing will not be finished here, but during the LLM call.
with st.spinner("Bestanden verwerken..."):
    client = get_client()
    uploaded_file_names = [f["file_name"] for f in st.session_state.file_list]
    if upload_files_widget is not None:
        for widget_file in upload_files_widget:
            if widget_file.name not in uploaded_file_names:  # else file is already uploaded
                with open(widget_file.name, "wb") as f:
                    f.write(widget_file.read())

                if widget_file.name.endswith(tuple(RETRIEVAL_EXTENSIONS + DATA_EXTENSIONS)):
                    # If it's a tabular data file, we need to upload it to add it to the Responses API call later
                    # If it's a retrieval file, we need to upload it to add it to a vector store a few lines below.
                    file = client.files.create(file=open(widget_file.name, "rb"), purpose="assistants")
                    file_id = file.id
                else:  # image extension
                    # we don't upload images here, but we encode it in base64 and
                    # include it in the request of the responses API
                    file_id = "no_file_id"

                file_info = {"file_id": file_id, "file_name": widget_file.name, "processed": False}

                if widget_file.name.endswith(tuple(RETRIEVAL_EXTENSIONS)):
                    # Add the file to a vector store to make it searchable
                    if st.session_state.vector_store_id is None:
                        vector_store = client.vector_stores.create()
                        st.session_state.vector_store_id = vector_store.id
                    client.vector_stores.files.create(vector_store_id=st.session_state.vector_store_id, file_id=file_id)

                elif widget_file.name.endswith(tuple(IMAGE_EXTENSIONS)):
                    file_info["b64_encoded_file"] = encode_file_b64(widget_file.name)

                st.session_state.file_list.append(file_info)


# Checks if the last message on the message stack was sent by a human. If so, invoke the LLM to get a response
if len(st.session_state.safechat_messages) >= 1 and st.session_state.safechat_messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        user_prompt = st.session_state.safechat_messages[-1]["content"]
        event_generator = llm_call(user_prompt)

        with st.spinner("Veilig ChatGPT is aan het denken..."):
            st.write_stream(event_generator())
        responses = get_final_responses()

        for response in responses:
            display_content(response)
            st.session_state.safechat_messages.append({"role": "assistant", "content": response})

    st.session_state.block_chat_input = False

    # Save chat metadata after each interaction
    try:
        chat = {
            "environment": OTAP,
            "session_uuid": st.session_state.session_uuid,
            "timestamp_last_chat": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "hashed_user": hashlib.sha512(st.session_state.user["userPrincipalName"].encode("utf-8")).hexdigest(),
        }
        save_metadata(client=st.session_state["blob_client"], chat=chat)
    except Exception as e:
        raise FailSavingChat(message=f"Opslaan van metadata is niet gelukt: {repr(e)}")

    # rerun script to re-enable chat input box
    st.rerun()
