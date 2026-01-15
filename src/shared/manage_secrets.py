import argparse
import os
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from dotenv import dotenv_values, load_dotenv

# For a new secret, update needed-secrets.txt as well as the YAML file,
# after --secure-environment-variables


def manage_secrets(all_secrets: bool = False):
    """Create a .env file with your secrets. Choose between all secrets in the key vault, or only those where the names
    are given in needed-secrets.txt.

    To whitelist your IP in the keyvault, run for example
    az keyvault network-rule add -n KEYVAULT-NAME -g RESOURCEGROUP-NAME --ip-address $(curl -s ifconfig.me)
    Or see Confluence documentation for more details.

    Don't use service principal - use your private account with the appropriate dev/prd pitwall.

    Args:
        all_secrets (bool, optional): Whether to load all secrets or only the subset
        in needed-secrets.txt. Defaults to False.
    """
    print(f"GETTING SECRETS! Your environment is {os.environ.get('OTAP', 'local')}")
    credential = DefaultAzureCredential()
    kv_client = get_keyvault_client(credential)
    env_file_path = create_dotenv_if_not_exists()
    kv_secret_names = list_kv_secrets(kv_client, all_secrets)
    kv_secrets = get_kv_secrets(kv_client, kv_secret_names)
    update_dotenv(env_file_path, kv_secrets)
    print("DONE")


def list_kv_secrets(kv_client, all_secrets: bool) -> list[str]:
    """List secrets in the key vault.

    If all_secrets is False, only the secrets from needed-secrets.txt are returned.
    """
    if not all_secrets:
        with open("needed-secrets.txt", "r") as f:
            kv_secret_names = f.readlines()
        kv_secret_names = [x.strip() for x in kv_secret_names]
    else:
        kv_secret_names = [
            secret.name for secret in kv_client.list_properties_of_secrets() if valid_content_type(secret)
        ]
    return kv_secret_names


def valid_content_type(secret) -> bool:
    """Check if the secret has a valid content type."""
    return (secret.content_type is None) or (secret.content_type == "")


def create_dotenv_if_not_exists(env_file_path=".env") -> Path:
    """Create a .env file if it does not exist."""
    env_p = Path(env_file_path)
    if not env_p.exists():
        env_p.touch()
    print(f"env exists: {'.env' in os.listdir()}")
    return env_file_path


def get_keyvault_client(credential: DefaultAzureCredential) -> SecretClient:
    """Get the Azure Key Vault client."""
    if os.environ.get("OTAP") == "P":
        kv_name = os.environ["KEYVAULT_NAME_PRD"]
    else:
        kv_name = os.environ["KEYVAULT_NAME_DEV"]
    kv_uri = f"https://{kv_name}.vault.azure.net"
    client = SecretClient(vault_url=kv_uri, credential=credential)
    return client


def get_kv_secrets(client: SecretClient, kv_secret_names: list[str]) -> dict:
    """Get secrets from the Azure Key Vault."""
    secrets = {secret_name: client.get_secret(secret_name).value for secret_name in kv_secret_names}
    return secrets


def parse_dotenv(dotenv_file: Path):
    """Parse the .env file and yield secret names and values."""
    with open(dotenv_file) as f:
        env_lines = f.readlines()
        for line in env_lines:
            if line[0] == "#":
                continue
            if "=" not in line:
                continue
            secret_name = line.split("=")[0]
            secret_value = "=".join(line.split("=")[1:]).strip("\n").strip("''").strip('""')

            yield secret_name, secret_value


def update_dotenv(dotenv_file: Path, kv_secrets: dict):
    """Update the .env file with the secrets from the Azure Key Vault."""
    kv_secrets = {key.replace("-", "_"): value for key, value in kv_secrets.items()}
    current_secrets = dotenv_values(dotenv_path=dotenv_file)
    current_secrets.update(kv_secrets)
    print(f"currently in {os.getcwd()}")
    print(f"writing to: {dotenv_file}")
    with open(dotenv_file, "w") as f:
        for secret_name, secret_value in current_secrets.items():
            print(f"Writing secret {secret_name} to {dotenv_file}")
            f.write(f"{secret_name}={secret_value}\n")


def get_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--useSP",
        help="whether script will use service principal credentials",
        default=False,
        type=bool,
        required=False,
    )
    parser.add_argument("--projectName", help="name of the current project", type=str)
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    load_dotenv()
    manage_secrets(all_secrets=False)
