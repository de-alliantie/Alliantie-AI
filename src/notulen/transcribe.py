import os
import time
from pathlib import Path

from azure.ai.ml import Input, Output
from faster_whisper import WhisperModel

from shared.my_logging import logger


def transcribe(folder_path: Input(type="uri_folder"), output_folder: Output(type="uri_folder")) -> None:  # noqa F821
    """Also able to transcribe multiple audio/video files into a single .txt file."""

    input_path = Path(output_folder) / "input/opname"
    output_path = Path(output_folder) / "transcript.txt"

    # for local dev, check if exists:
    if output_path.exists():
        logger.info(f"{input_path.parent.parent.stem} already transcribed.")
        return

    if not any(input_path.iterdir()):
        raise Exception("No audio/video files found")
    model = WhisperModel(
        # model_size_or_path="/localwhispermodel_large_v2",
        model_size_or_path="large-v2",
        device="cuda",
        compute_type="float16",
        num_workers=1,
        local_files_only=False,
    )
    model.logger = logger
    result = []
    start_time = time.time()

    # Sort the input files by their name without extension,
    # casting to int to make sure filenames like 10, 20 etc. also are properly sorted
    input_files = os.listdir(input_path)
    if len(input_files) > 1:
        try:
            input_files_sorted = sorted(input_files, key=lambda x: int(os.path.splitext(x)[0]))
        except Exception as e:
            raise Exception(f"Failed to sort multiple input recording files \n {e}")
    else:
        input_files_sorted = input_files

    for path in input_files_sorted:
        logger.info(f"Transcribing {path}...")
        segments, _ = model.transcribe(
            audio=(input_path / path).as_posix(), language="nl", beam_size=5, vad_filter=True
        )
        result.extend([s.text.strip() for s in segments])
    end_time = time.time()
    logger.info(
        f"Transcription took {round((end_time-start_time)/60, 1)} minutes, {len(list(input_path.iterdir()))} file(s)."
    )
    with open(output_path, "w") as f:
        f.write("\n".join(result))


if __name__ == "__main__":
    # Example usage
    timestamp = "some_timestamp"
    transcribe(f"data/{timestamp}", f"data/{timestamp}")
