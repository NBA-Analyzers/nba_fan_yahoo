from openai import OpenAI
from fastapi import FastAPI
from api.agent_manager_api import agent_router
from api.files_api import files_router
import uvicorn 
import sys
import os
from contextlib import asynccontextmanager
from my_app.agent.services import vector_store_manager
from services.file_manager import FileManager
from services.agent_manager import AgentManager
from services.vector_store_manager import VectorStoreManager
from dependencies import set_services



app = FastAPI()
client = OpenAI(api_key=os.environ["openai_api_key"])
vs_box_score_id = None # TODO - search DB
vector_store_manager = VectorStoreManager(client)
file_manager = FileManager(client, vector_store_manager)
agent_manager = AgentManager(client, file_manager)
set_services(agent_manager, file_manager, vector_store_manager)
app.include_router(agent_router)
app.include_router(files_router)

if __name__ == "__main__":

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5001,
        reload=True)