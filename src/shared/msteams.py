import os

import pymsteams


def log_result_to_MS_teams(result: str) -> None:
    """Logt een string naar een bepaald Microsoft Teams-kanaal.

    Args:
        result (str): Te loggen informatie

    Returns:
        None
    """
    teams_webhook = os.environ["TEAMS_WEBHOOK_DATASCIENCE_ALGEMEEN"]
    myTeamsMessage = pymsteams.connectorcard(teams_webhook)
    myTeamsMessage.text(result)
    myTeamsMessage.send()

    return None
