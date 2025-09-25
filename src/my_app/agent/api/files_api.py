from fastapi import APIRouter, Depends
from typing import List
from dependencies import get_file_manager1
from services.file_manager import FileManager, UpdateFile, OpenaiStoredFiles
from fastapi_utils.cbv import cbv

files_router = APIRouter()

@cbv(files_router)
class FilesAPI:

    file_manager: FileManager = Depends(get_file_manager1)

    @files_router.post("/{league_id}/update_files")
    def update_league_files(
        self, 
        league_id: str,
        files: List[UpdateFile]
    ) -> OpenaiStoredFiles:
        # TODO: validate all league files are in the list
        return self.file_manager.update_league_files(league_id, files)


    @files_router.post("/update_box_score")
    def update_box_score(self, box_score_path: str) -> OpenaiStoredFiles:
        return self.file_manager.update_box_score(UpdateFile("Box Score", box_score_path))

    @files_router.post("/update_rules")
    def update_rules(self, files: List[UpdateFile]) -> OpenaiStoredFiles:
        return self.file_manager.update_rules(files)