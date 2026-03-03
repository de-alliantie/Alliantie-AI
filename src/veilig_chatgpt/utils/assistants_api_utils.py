"""Deze logica kan ad hoc word gebruikt worden om assistants te beheren via de Assistants API van OpenAI (en wordt dus
niet actief gebruikt)."""

# from src.veilig_chatgpt.helpers import get_client
from shared.utils import init_openai_client


class AssistantManager:
    """Wrapper to interact with assistants in the Assistants API."""

    def __init__(self, client):
        """Initialize."""
        self.client = client

    def list_assistants(self):
        """Returns a list of all assistants."""
        return self.client.beta.assistants.list()

    def delete_unused_assistants(self, assistant_ids_to_keep: list[str]):
        """Deletes assistants that are not in the predefined ASSISTANT_ID list."""
        assistant_list = self.list_assistants()

        for assistant in assistant_list.data:
            if assistant.id not in assistant_ids_to_keep:
                print(f"Deleting: ID: {assistant.id}, Name: {assistant.name}, Model: {assistant.model}")
                self.client.beta.assistants.delete(assistant_id=assistant.id)
            else:
                print(f"Keeping: ID: {assistant.id}, Name: {assistant.name}, Model: {assistant.model}")
        print()

    def create_assistant(self, name: str, model: str):
        """Creates a new assistant with the given name and model."""
        response = self.client.beta.assistants.create(name=name, model=model)
        print(f"Created Assistant: ID: {response.id}, Name: {response.name}, Model: {response.model}")
        return response


if __name__ == "__main__":
    # Example usage
    assistant_ids_to_keep = ["first_id", "second_id"]
    client = init_openai_client()
    manager = AssistantManager(client)
    manager.delete_unused_assistants(assistant_ids_to_keep)
