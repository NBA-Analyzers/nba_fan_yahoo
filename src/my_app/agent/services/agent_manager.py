import services.rag as rag

SYSTEM_PROMPT = "You are a professional coding helper. Use the attached file to guide the user with his coding job interview"

class AgentManager():

    def __init__(self, openai_client, file_manager):
        self.client = openai_client
        self.file_manager = file_manager

    def message_assistant(self, previous_response_id: str, new_user_message: str, tools: dict):
        
        assistant_response = self.client.responses.create(
            model="gpt-4.1-mini",
            input=new_user_message,
            previous_response_id=previous_response_id,
            tools=tools
        )

        return assistant_response

    def start_chat(self, previous_response_id: str, new_user_message: str):

        tools = self.create_tools(new_user_message)
        assistant_response = self.message_assistant(previous_response_id, new_user_message, tools)
        return {
            "assistant_response_text": assistant_response.output_text,
            "response_id": assistant_response.id
        }

    def create_tools(self, user_input: str):
        openai_file_ids = rag.fetch_relevant_file_ids(user_input)
        league_vector_store_id = self.file_manager.create_vector_store(openai_file_ids)
        box_score_vector_store_id = self.file_manager.vs_box_score_id

        
        return [
            {
                "type" : "file_search",
                "vector_store_ids": [league_vector_store_id, box_score_vector_store_id]
            }
        ]