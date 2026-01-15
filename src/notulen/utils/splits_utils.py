import re
from pathlib import Path


def extract_agendapunten(folder_path: Path) -> dict:
    """Dit splitst het PDF bestand van de agenda in losse agendapunten. Hierbij is eerst het PDF bestand geconverteerd
    naar Markdown. Het verwacht een PDF uit TwinQ en dus ook een specifieke opmaak, namelijk dat de titels (in Markdown)

    er zo uit zien:
    **Ter besluitvorming - Opening** **1.**
    of
    **1.** **Ter besluitvorming - Opening**
    """
    agenda_path = folder_path / "processed_input_docs" / "agenda.md"
    agenda_str = agenda_path.read_text()

    pattern_titeltekst = r"\*\*[^*]+\*\*"  # bijv. **Ter besluitvorming - Opening**
    pattern_agendapuntnummer = r"\*\*\d{1,2}\.\S{0,2}\*\*"  # bijv. **1.** of **1.a** of **1.1**
    pattern_titel_dan_nummer = rf"{pattern_titeltekst}\s*{pattern_agendapuntnummer}"
    pattern_nummer_dan_titel = rf"{pattern_agendapuntnummer}\s*{pattern_titeltekst}"
    pattern_agendapunt_titel = rf"{pattern_titel_dan_nummer}|{pattern_nummer_dan_titel}"
    pattern_fix_kopjes = r"\*\*((?s).*?)\*\*((?s).*?)\*\*(.*?)\*\*"

    matches = re.findall(pattern_agendapuntnummer, agenda_str)  # agendapuntnummers
    matches2 = re.findall(pattern_agendapunt_titel, agenda_str)  # vind de titels

    kopjes_fixed = []
    for kopje in matches2:
        match = re.match(pattern_fix_kopjes, kopje)
        if match:
            kopje_fixed = match.group(3) + " " + match.group(1)
        else:
            kopje_fixed = kopje
        kopjes_fixed.append(kopje_fixed)

    agendapunttypes = [
        "ter besluitvorming"
        if "ter besluitvorming" in s.lower()
        else "ter info"
        if "ter informatie" in s.lower()
        else "anders"
        for s in matches2
    ]
    agendapuntnummers = [x.replace("**", "").lower() for x in matches]
    agendapuntnummers = [_replace_numbers_with_letters(x) for x in agendapuntnummers]
    agendapuntnummers = [x.replace(".", "") for x in agendapuntnummers]

    splitsing = re.split(pattern_agendapunt_titel, agenda_str)
    splitsing_dict = {
        agendapuntnummers[i]: {
            "body": splitsing[i + 1].strip(),
            "type": agendapunttypes[i],  # doe we nu niks mee
            "titel": kopjes_fixed[i],
        }
        for i in range(len(agendapuntnummers))
    }
    return splitsing_dict


def extract_agendapunten_txt(folder_path: Path) -> dict:
    """Splitst de agenda wanneer dit direct wordt aangeleverd als Markdown bestand (dus niet initieel een PDF).

    Hierbij moeten de titels van de vorm # 3a Titel agendapunt zijn (ook mogelijk: 3a. of 3.a i.p.v 3a). Zie
    utils/agenda_voorbeeld.txt voor een voorbeeld.
    """
    agenda_path = folder_path / "input" / "agenda.txt"
    agenda_str = agenda_path.read_text()

    # Lines starting with '#', followed by 1-2 digits, optional dot/lowercase letter/whitespace,
    # then any text (agenda item title)
    pattern_agendapunt_titel = r"\#\s\d{1,2}\.?[a-zA-x]?\.?\s+.+"
    # Matches lines starting with '#', followed by 1-2 digits, optional dot/letter (a-z or A-Z) (agenda item number)
    pattern_agendapuntnummer = r"\#\s\d{1,2}\.?[a-zA-Z]?"

    agendapuntnummers = re.findall(pattern_agendapuntnummer, agenda_str)  # agendapuntnummers
    titels = re.findall(pattern_agendapunt_titel, agenda_str)  # vind de titels
    agendapuntnummers = [x.replace("#", "").replace(".", "").strip() for x in agendapuntnummers]
    titels = [x.replace("#", "").strip() for x in titels]

    splitsing = re.split(pattern_agendapunt_titel, agenda_str)
    splitsing_dict = {
        agendapuntnummers[i]: {
            "body": splitsing[i + 1].strip(),
            "titel": titels[i],
        }
        for i in range(len(agendapuntnummers))
    }
    return splitsing_dict


def _replace_numbers_with_letters(text: str) -> str:
    """Convert the string '2.3' in '2.c' for the agendapuntnummers.

    This is necessary for the apply_gpt_split function.
    """
    # Create a dictionary mapping ".1" to ".a", etc.
    mapping = {f".{i}": f".{chr(96 + i)}" for i in range(1, 27)}

    for key, value in mapping.items():
        text = text.replace(key, value)  # Replace each occurrence

    return text


class AgendapuntMetTranscript:
    """Deze klasse representeert een agendapunt (nummer) en een bijbehorende lijst van intervallen van regelnummers uit
    het transcript."""

    def __init__(self, agendapuntnummer: str, list_of_intervals: list[tuple[int, int]], laatste_regel_transcript: int):
        """Initialize."""
        self.agendapuntnummer = agendapuntnummer
        self.list_of_intervals = list_of_intervals
        self.laatste_regel_transcript = laatste_regel_transcript

        if len(list_of_intervals) == 0:
            # LLM did not detect relevant lines, so we give it the entire transcript
            self.left_boundary_gebied = 1
            self.right_boundary_gebied = laatste_regel_transcript
            self.right_boundary_gebied_old = self.right_boundary_gebied
            self.list_of_intervals = [(self.left_boundary_gebied, self.right_boundary_gebied)]
        else:
            self.left_boundary_gebied = min([interval[0] for interval in list_of_intervals])
            self.right_boundary_gebied = max([interval[1] for interval in list_of_intervals])
            self.right_boundary_gebied_old = self.right_boundary_gebied
            self.verwijder_overlap()

    def verwijder_overlap(self):
        """Maak de intervallen disjunct door overlappende en ingesloten delen samen te voegen.

        Ook worden de intervallen op een logische volgorde gesorteerd.
        """
        if len(self.list_of_intervals) == 1:
            return

        # Sorteer de intervallen op startregel
        sorted_intervals = sorted(self.list_of_intervals, key=lambda x: x[0])
        merged = [sorted_intervals[0]]

        for current in sorted_intervals[1:]:
            prev_start, prev_end = merged[-1]
            curr_start, curr_end = current

            if curr_start <= prev_end:
                # Overlap (of direct aansluitend) en dus samenvoegen
                merged[-1] = (prev_start, max(prev_end, curr_end))
            else:
                # Geen overlap, nieuw interval
                merged.append(current)

        self.list_of_intervals = merged

        # Update boundaries
        self.left_boundary_gebied = merged[0][0]
        self.right_boundary_gebied = merged[-1][1]

    def add_interval(self, new_interval: tuple[int, int]):
        """Voeg een zelfgemaakt interval toe als het logisch is."""
        self.list_of_intervals.append(new_interval)


def apply_gpt_split(transcript_lines: list[str], gpt_dict: dict, splits_path: Path) -> dict:
    """Gegeven de dictionary van de splitsing van de LLM, splits de string van het transcript.

    Maar eerst verwerken we de splitsing dictionary van de LLM met zelfgeschreven logica, omdat de output soms onlogisch
    is.
    """
    transcript_split = {}
    laatste_regel_transcript = len(transcript_lines)

    # prepare keys/agendapuntnummers
    gpt_dict = {k.replace(".", "").lower(): v for k, v in gpt_dict.items()}
    items_list = list(gpt_dict.items())
    # enforce that the agendapuntnummers are in the correct order inside the items list
    items_list = sorted(items_list, key=_helper_sorting)

    agendapunten_met_transcript = [
        AgendapuntMetTranscript(agendapuntnummer, list_of_intervals, laatste_regel_transcript)
        for agendapuntnummer, list_of_intervals in items_list
    ]
    # Verwerk onlogische output van LLM met zelfgeschreven logica.
    # Het taalmodel is beter in het herkennen van waar een agendapunt begint dan waar die eindigt
    for agendapunt_index, agendapunt_met_transcript in enumerate(agendapunten_met_transcript):
        if len(agendapunten_met_transcript) == 1:
            # Als er maar 1 agendapunt is, krijgt die gewoon het hele transcript. De elif en else statements worden geskipt # noqa: E501
            agendapunt_met_transcript.list_of_intervals = [(1, laatste_regel_transcript)]
        elif agendapunt_index == 0:
            # het eerste agendapunt moet lopen van het begin van het transcript tot het volgende agendapunt
            agendapunt_met_transcript.list_of_intervals = [
                (1, agendapunten_met_transcript[agendapunt_index + 1].left_boundary_gebied)
            ]
        elif agendapunt_index == len(agendapunten_met_transcript) - 1:
            # het laatste agendapunt moet gewoon het laatste gedeelte van het transcript vangen
            agendapunt_met_transcript.list_of_intervals = [
                (
                    agendapunt_met_transcript.left_boundary_gebied,
                    laatste_regel_transcript,
                )  # wijzig eindpunt maar niet startpunt
            ]
        else:
            for interval_index, interval in enumerate(agendapunt_met_transcript.list_of_intervals):
                left_boundary = interval[0]  # van het interval, niet van het hele gebied
                right_boundary = interval[1]

                # De volgende aanpassing kan nuttig zijn als het blijkt dat het beginpunt niet goed wordt herkend # noqa: E501
                # en dat er daardoor te weinig context wordt meegegeven. Voor nu uitgecomment. # noqa: E501
                # als het eerste interval later begint dan het vorige agendapunt eindigt, veranderen we dit (door de linkergrens te wijzigen) # noqa: E501
                # if interval_index == 0 and left_boundary > agendapunten_met_transcript[agendapunt_index - 1].right_boundary_gebied_old + 1: # noqa: E501
                #     left_boundary = agendapunten_met_transcript[agendapunt_index - 1].right_boundary_gebied_old + 1 # noqa: E501

                # de volgende if statement vergroot het gebied van het agendapunt d.m.v. 2 aanpassingen: # noqa: E501
                # (1) verwijdert "onnodige" gaten tussen intervallen van 1 agendapunt en (2) verwijdert het gat naar het volgende agendapunt # noqa: E501
                if (
                    # elk interval dat eindigt voor het beginpunt van het volgende agendapunt is een onzinnig interval,
                    # dat interval moest lopen tot het beginpunt van het volgende agendapunt
                    right_boundary
                    < agendapunten_met_transcript[agendapunt_index + 1].left_boundary_gebied
                ):
                    right_boundary = agendapunten_met_transcript[
                        agendapunt_index + 1
                    ].left_boundary_gebied  # maak interval groter naar start volgende agendapunt

                if (left_boundary, right_boundary) != interval:  # if interval changed
                    agendapunt_met_transcript.add_interval(new_interval=(left_boundary, right_boundary))
            agendapunt_met_transcript.verwijder_overlap()  # opnieuw overlap verwijderen, gecreeerd binnen de else statement # noqa: E501

        # Klaar met verwerken voor dit agendapunt. Extraheer het relevante deel van het transcript.
        transcript_split[agendapunt_met_transcript.agendapuntnummer] = ""
        for interval in agendapunt_met_transcript.list_of_intervals:
            start = interval[0] - 1
            end = interval[1]
            transcript_split[agendapunt_met_transcript.agendapuntnummer] += "".join(transcript_lines[start:end])

    # save processed split
    output_path = splits_path / "splitsing output LLM processed.txt"
    if output_path.exists():
        output_path.unlink()
    for agendapunt_met_transcript in agendapunten_met_transcript:
        with output_path.open("a") as f:
            f.write(f"{agendapunt_met_transcript.agendapuntnummer}: {agendapunt_met_transcript.list_of_intervals}\n")

    return transcript_split


def _helper_sorting(dict_item: dict) -> float | int:
    """Map for example the string "10a" to 10.097 (note: ord("a")=97) and "3" to 3 so that we can make sure the
    agendapuntnummers are in the correct order in the dictionary."""
    s = dict_item[0]  # the alphanumeric string, like "10a"
    match = re.match(r"(\d+)(\D+)", s)
    if match:
        integer_part = int(match.group(1))
        letter_part = match.group(2)
        return integer_part + ord(letter_part) / 1000
    else:
        return int(s)


def create_agenda_groups(agendapuntnummers: list, groupsize: int) -> list[list]:
    """Verdeel de agendapuntnummers in groepjes van grootte groupsize.

    Dit is ook de minimale size, dus wanneer het laatste groepje minder groot is, dit groepje aanvullen met
    agendapuntnummers van het vorige groepje.
    """
    N = len(agendapuntnummers)
    agendapuntnummers_groups = [agendapuntnummers[i : i + groupsize] for i in range(0, N, groupsize)]  # noqa:E203
    indices = [i for i in range(0, N, groupsize)]
    if 0 < N - groupsize < indices[-1]:
        agendapuntnummers_groups[-1] = agendapuntnummers[N - groupsize :]  # noqa:E203
    return agendapuntnummers_groups


if __name__ == "__main__":
    pass
