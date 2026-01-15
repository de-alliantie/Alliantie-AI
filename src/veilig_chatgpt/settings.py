import os

OTAP = os.environ.get("OTAP", "local")

LLM_CHOICE = {
    "GPT-4.1 mini": "safe-chat-gpt-4.1-mini",
    "GPT-4.1": "safe-chat-gpt-4.1",
    "GPT-5": "safe-chat-gpt-5",
}

RETRIEVAL_EXTENSIONS = [
    ".doc",
    ".docx",
    ".pptx",
    ".pdf",
    ".json",
    ".md",
    ".txt",
    # ".c",
    # ".cpp",
    # ".cs",
    # ".css",
    # ".go",
    ".html",
    # ".java",
    # ".js",
    # ".php",
    ".py",
    # ".rb",
    # ".sh",
    # ".tex",
    # ".ts",
]

DATA_EXTENSIONS = [".xls", ".xlsx", ".csv", ".xml"]

IMAGE_EXTENSIONS = [".jpeg", ".jpg", ".png", ".gif"]

# Use this weird order because the file_uploader widget will display these filetypes.
ALLOWED_EXTENSIONS = RETRIEVAL_EXTENSIONS[:4] + DATA_EXTENSIONS + IMAGE_EXTENSIONS + RETRIEVAL_EXTENSIONS[4:]


DATALAKE_LOGGING_BASE_PATH = f"alliantie_ai/{OTAP}"
