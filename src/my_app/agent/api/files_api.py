from curses import meta
from dataclasses import dataclass
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, Body, Request, UploadFile
from openai.types import file_purpose, vector_store
from pydantic import BaseModel
from typing import Optional, List, Dict
from dependencies import get_file_manager, get_vector_store_manager
from my_app.agent.services.vector_store_manager import VectorStoreManager, VectorStorePurpose
from services.file_manager import FileManager
from fastapi_utils.cbv import cbv

files_router = APIRouter()

@dataclass
class UpdateFile:
    file_name: str
    file_path: str

@cbv(files_router)
class FilesAPI:

    file_manager: FileManager = Depends(get_file_manager)

    @files_router.post("/{league_id}/update_files")
    def update_league_files(
        self, 
        league_id: str,
        files: List[UpdateFile]
    ):
        # TODO: validate all league files are in the list
        self.file_manager.update_league_files(league_id, files)


    @files_router.post("/update_box_score")
    def update_box_score(self, box_score_path: str):
        self.file_manager.update_box_score(UpdateFile("Box Score", box_score_path))

    @files_router.post("/update_rules")
    def update_rules(self, files: List[UpdateFile]):
        self.file_manager.update_rules(files)