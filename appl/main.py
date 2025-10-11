import os

import uvicorn
from .router.agent_manager_api import agent_router, AgentAPI, set_agent_api_instance
from .router.files_api import files_router
from .config.dependencies import set_services
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from .service.agent_manager import AgentManager
from .service.file_manager import FileManager
from .service.vector_store_manager import VectorStoreManager


app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.environ["openai_api_key"])
vs_box_score_id = None # TODO - search DB
vector_store_manager = VectorStoreManager(client)
file_manager = FileManager(client, vector_store_manager)
agent_manager = AgentManager(client, file_manager)
set_services(agent_manager, file_manager, vector_store_manager)

# Initialize AgentAPI singleton instance at startup
agent_api_instance = AgentAPI(agent_manager)
set_agent_api_instance(agent_api_instance)
app.include_router(agent_router)
app.include_router(files_router)

# Serve static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Serve the main page
@app.get("/")
async def read_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

if __name__ == "__main__":

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5001,
        reload=True)