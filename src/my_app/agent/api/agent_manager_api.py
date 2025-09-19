from fastapi import APIRouter, HTTPException, Body, Depends, Request
from fastapi_utils.cbv import cbv
from pydantic import BaseModel
from typing import Optional, List, Dict
from dependencies import get_agent_manager
from services.agent_manager import AgentManager


chat_sessions = []

class ChatRequest(BaseModel):
    session_id: str
    user_message: str

class ChatSession(BaseModel):
    session_id: str
    previous_openai_response_id: str

class AssistantResponse(BaseModel):
    assistant_response_text: str
    response_id: str

agent_router = APIRouter()

@cbv(agent_router)
class AgentAPI:
    agent_manager: AgentManager = Depends(get_agent_manager)

    @agent_router.post("/chat")
    def chat_with_openai(self, request: ChatRequest):

        response_text = ""
        # quit chat session
        if request.user_message.lower() == "quit":
            response_text = "Goodbye!"
            chat_sessions = [item for item in chat_sessions if item.session_id != request.session_id]

        else:
            assistant_response = self.agent_manager.start_chat(
                previous_response_id=request.previous_response_id,
                new_user_message=request.new_user_message
            )

            # Start new chat
            if request.session_id not in chat_sessions:
                response_text = "Welcome to Fantasy Basketball Helper (type 'quit' to exit)\n"
                new_chat_session = ChatSession(            
                    session_id=request.session_id,
                    previous_openai_response_id=assistant_response.response_id
                )
                chat_sessions.append(new_chat_session)
            else:
                for chat_session in chat_sessions:
                    if chat_session.session_id == request.session_id:
                        chat_session.previous_openai_response_id = assistant_response.response_id
                        break
            response_text += "User: "+request.user_message+"\n"
            response_text += "Assistant: "+assistant_response.assistant_response_text
        return response_text
