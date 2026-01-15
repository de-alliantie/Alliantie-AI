import re
import shutil
import time
from pathlib import Path

import pypandoc
from openai import AzureOpenAI
from pdf4llm import to_markdown
from pydantic import BaseModel, Field
from unidecode import unidecode

from notulen.settings import DEPLOYMENT_NAME
from shared.my_logging import logger


# De volgende 3 classes definieren de "structured output".
# Ik verwacht dat de docstring van een class en de discription in
# een Field meegenomen wordenin de pre-prompting onder de motorkap in de API.
class ClosedIntervalOfLineNumbers(BaseModel):
    """Geeft een gesloten interval, in wiskundige zin, van regelnummers van het transcript."""

    left_endpoint: int
    right_endpoint: int


class RegelnummersVoorAgendapunt(BaseModel):
    """Geeft een verzameling van alle regelnummers van het transcript."""

    agendapuntnummer: str = Field(description="een nummer zoals '1' of '1a'")
    set_of_intervals: list[ClosedIntervalOfLineNumbers] = Field(
        description="Een verzameling van intervallen (in wiskundige zin) van regelnummers van het transcript die horen bij het agendapunt."  # noqa: E501
    )


class AgendapuntenMetGevondenRegels(BaseModel):
    """."""

    result: list[RegelnummersVoorAgendapunt] = Field(
        description="Lijst van agendapunten en de bijbehorende verzamelingen van regelnummers."
    )


def get_splitsing_prompt(folder_path: Path, agendapuntnummers, for_vve: bool) -> tuple[str, str]:
    """Returns the prompt."""
    try:
        agenda_str = (folder_path / "processed_input_docs/agenda.md").read_text()
    except FileNotFoundError:
        try:
            agenda_str = (folder_path / "input/agenda.txt").read_text()
        except FileNotFoundError:
            raise Exception("No agenda in .md or .txt found")

    transcript_lines_numbered = load_transcript(folder_path, numbered=True)
    transcript = "".join(transcript_lines_numbered)

    if for_vve:
        prompt_template = (Path(__file__).parent.parent / "prompts" / "prompt_splitsen_vve.md").read_text()
    else:
        prompt_template = (Path(__file__).parent.parent / "prompts" / "prompt_splitsen.md").read_text()

    agendapuntnummers_str = ", ".join(agendapuntnummers)
    prompt = prompt_template.format(transcript=transcript, agenda=agenda_str, agendapuntnummers=agendapuntnummers_str)
    return prompt, prompt_template


def load_transcript(folder_path: Path, numbered: bool) -> list[str]:
    """Loads the transscript."""
    with open(folder_path / "transcript.txt", "r", encoding="utf-8") as f:
        transcript_lines = f.readlines()
    transcript_lines_numbered = [f"{i+1}) " + line for i, line in enumerate(transcript_lines)]
    if numbered:
        (folder_path / "transcript_numbered.txt").write_text("".join(transcript_lines_numbered))
        return transcript_lines_numbered
    else:
        return transcript_lines


def make_llm_call(client: AzureOpenAI, prompt: str, notulen: bool, reason: str = "") -> dict | str | None:
    """Stuur de prompt naar Azure OpenAI GPT-4o."""

    logger.info(f"Prompting the LLM: {reason}")
    starttime = time.time()
    prompt = unidecode(prompt)
    prompt = prompt.replace("\ufeff", "")  # you get this when using MS Word
    if notulen:
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            response_format={"type": "text"},
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            temperature=0.01,
            # top_p = 0.001
        )
        if response.choices[0].finish_reason == "content_filter":
            logger.error("Azure OpenAI content filter triggered")
            return "Notulen konden niet worden gegenereerd vanwege content filter van het taalmodel."
        content = response.choices[0].message.content
    else:  # splitsing transcript
        response = client.beta.chat.completions.parse(
            model=DEPLOYMENT_NAME,
            messages=[{"role": "user", "content": prompt}],
            response_format=AgendapuntenMetGevondenRegels,
        )
        if response.choices[0].message.refusal:
            logger.error("API (structured outputs) refused the call.")
            return {}

        extracted_data = response.choices[0].message.parsed
        if len(extracted_data.result) == 0:
            logger.error("Could parse output but got an empty list. So none of agendapunten detected.")
            return {}
        splitsing_parsed = {}
        for agendapunt_met_data in extracted_data.result:
            intervallen = agendapunt_met_data.set_of_intervals
            # intervallen allowed to be empty, syntax wise, but can also actually be empty in weird cases.
            intervallen_parsed = []
            for i in intervallen:
                intervallen_parsed.append((i.left_endpoint, i.right_endpoint))
            splitsing_parsed[agendapunt_met_data.agendapuntnummer] = intervallen_parsed

        content = splitsing_parsed
    logger.info(f"LLM call: {round((time.time() - starttime)/60, 1)} minutes")
    logger.info(
        f"Input tokens: {response.usage.prompt_tokens}, output tokens: {response.usage.completion_tokens} (API)"
    )

    return content


def process_llm_output(output: str) -> str:
    """Processes the output from the LLM."""
    output2 = output.replace("`", "").strip()
    output2 = output2[8:] if output2.startswith("markdown") else output2
    output2 = output2.replace("\nBesluiten:", "\n**Besluiten:**")
    output2 = output2.replace("\nActiepunten:", "\n**Actiepunten:**")
    return output2.strip()


def extract_leading_number(filename: str) -> int | None:
    """Extracts the first number in a filename."""
    match = re.match(r"(\d+)", filename)
    if match:
        return int(match.group(1))
    else:
        raise Exception


def convert_from_pdf_to_markdown(folder_path: Path) -> None:
    """Convert the agenda and notulen pdf documents."""
    path = folder_path / "processed_input_docs"
    if (path / "agenda.md").is_file():
        return

    pdf_files = list((folder_path / "input").glob("*.pdf"))
    if len(pdf_files) != 1:
        raise Exception(f"Zero or more than one PDF file found as agenda.\nPDF files are: {pdf_files}")
    else:
        agenda_path = pdf_files[0].as_posix()
    md_text_agenda = to_markdown(agenda_path, pages=None)

    path.mkdir(parents=True, exist_ok=True)
    (path / "agenda.md").write_text(md_text_agenda)
    logger.info("Converted agenda from pdf to markdown")
    return


def convert_from_rtf_to_markdown(folder_path: Path) -> None:
    """Convert the agenda rtf document."""
    path = folder_path / "processed_input_docs"
    agenda_path = list((folder_path / "input").glob("*Agenda*.rtf"))[0].as_posix()
    pypandoc.convert_file(source_file=agenda_path, to="markdown", outputfile=path / "agenda_rtf.md")
    return


def convert_to_docx(path_to_md: str):
    """Convert markdown file.

    Fix some formatting.
    """
    name = Path(path_to_md).stem
    parent_folder = Path(path_to_md).parent
    with open(path_to_md, "r") as f:
        lines = f.readlines()

    chars = ("1.", "-", "_-", "*-")
    nr_lines = len(lines)
    lines2 = [
        "\n" + line
        if line.strip().startswith(chars) and not lines[i - 1].strip().startswith(chars)
        else line.replace("\n", "  \n")
        if i < nr_lines - 1 and line.startswith(("_-", "*-")) and not lines[i + 1].strip().startswith(("_-", "*-"))
        else line
        for i, line in enumerate(lines)
    ]
    output = "".join(lines2)
    (parent_folder / "output_processed.md").write_text(output)
    pypandoc.convert_text(source=output, to="docx", format="markdown", outputfile=parent_folder / f"{name}.docx")


def new_trial_nr(path: Path) -> str:
    """Find n+1 where n is the number of trials already done, because we want to create a new folder with the name n+1.

    Of course only during development do we have multiple trials.
    """
    try:
        files_folders = [f.stem for f in path.iterdir()]
        latest_trial_number = max([extract_leading_number(f) for f in files_folders])
        trial = latest_trial_number + 1
    except Exception as e:
        logger.error(f"Error in new_trial_nr: {e}")
        trial = 1
    return str(trial)


def convert_stuff_to_docx_for_stakeholders(folder_path: Path, splits_path: Path, notulen_output_path: Path):
    """This creates the following .docx files if stakeholders are interested.

    Also interesting for debugging.
    - prompt template used to split the transcript
    - the output of the LLM when it was asked to split the transcript
    - actual lines of the transcript that are split in groups
    - full transcript
    - prompt template for generating meeting notes
    - final meeting notes
    """
    out_path = folder_path / "result"
    out_path.mkdir(exist_ok=True, parents=True)
    pypandoc.convert_file(
        source_file=splits_path / "splitsing output LLM.txt",
        format="md",
        to="docx",
        outputfile=out_path / "splitsing output LLM.docx",
    )
    pypandoc.convert_file(
        source_file=splits_path / "resultaat splitsing.md",
        format="md",
        to="docx",
        outputfile=out_path / "resultaat splitsing.docx",
    )
    shutil.copy(src=notulen_output_path / "notulen.docx", dst=out_path / "notulen.docx")


def prepare_markdown_string(my_str: str) -> str:
    """Prepare a string for markdown rendering."""
    return my_str.replace("_\n", "_  \n").replace("\n_", "  \n_").replace("\n\n-----\n\n", "")


if __name__ == "__main__":
    # Example
    vve = "VvE 1234"
    source = f"data/{vve}/output_notulen/11.md"
    convert_to_docx(source)
