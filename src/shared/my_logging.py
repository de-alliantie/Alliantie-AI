import logging
import os
from logging import Logger
from pathlib import Path
from time import tzset

from azure.monitor.opentelemetry import configure_azure_monitor

APPI_NAMESPACE = os.environ["APPLICATION_INSIGHTS_NAMESPACE"]


def setup_logging(project_afkorting: str) -> Logger:
    """Initiazes the logger."""
    logger = logging.getLogger(project_afkorting)

    if os.getenv("TZ") != "Europe/Amsterdam":
        # set correct timezone to log nicely:
        os.environ["TZ"] = "Europe/Amsterdam"
        tzset()

    if logger.hasHandlers():  # logger already initialized
        return logger

    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logpath = Path("logs/run.log")
    logpath.parent.mkdir(exist_ok=True, parents=True)

    file_handler = logging.FileHandler(logpath, mode="w")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    handlers = [file_handler, stream_handler]

    formatter_other = logging.Formatter(
        fmt=f"[%(asctime)s] [{project_afkorting}:%(filename)s:%(lineno)d] %(levelname)s - %(message)s",
        datefmt="%d/%b/%Y %H:%M:%S",
    )

    for handler in handlers:
        handler.setFormatter(formatter_other)
        logger.addHandler(handler)

    try:
        conn_str = os.environ["APPLICATION_INSIGHTS_CONNECTION_STRING"]
        # this adds an extra handler to logger that logs to Application Insights:
        enable_appi_logging(project_afkorting, conn_str)
    except Exception as e:
        print(f"\n\n\n Azure handler failed for logger \n{e}\n\n")

    logger.info(f"Logger initialized and environment is {os.environ.get('OTAP', 'local')}")

    return logger


def enable_appi_logging(name: str, conn_str: str) -> None:
    """Enable logging handler for Azure Application Insights.

    This function should be called before the first logging message!
    Otherwise it won't have an effect!

    Args:
        name (str): project name that logs will be written under
    """

    vve_number = os.environ.get("vve_number", "")
    opentelemetry_vars = {
        "OTEL_RESOURCE_ATTRIBUTES": f"service.namespace={APPI_NAMESPACE},service.instance.id={name}",
        "OTEL_SERVICE_NAME": f"{name}-{vve_number}",
        "OTEL_TRACES_SAMPLER_ARG": "0.1",
    }
    for k, v in opentelemetry_vars.items():
        os.environ[k] = v

    configure_azure_monitor(connection_string=conn_str, logger_name=name)


# only the first time the logger is initialized, subsequent calls will return the same logger instance
logger = setup_logging("alliantie-genai")
