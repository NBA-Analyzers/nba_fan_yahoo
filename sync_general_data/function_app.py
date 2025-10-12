import azure.functions as func
app = func.FunctionApp()
from appl.repository.azure.azure_blob_storage import AzureBlobStorage

@app.function_name(name="sync_full_league")
@app.route(route="sync_full_league", auth_level=func.AuthLevel.ANONYMOUS)
def test_sync_full_league(req: func.HttpRequest) -> func.HttpResponse:
    azure_container="fantasy1"
    azure_storage = AzureBlobStorage(container_name=azure_container)

    return func.HttpResponse("connection string:" + azure_storage.connection_string + "container name: " + azure_storage.container_name)

    # TODO - Box Score + Injuries
    # Upload to Azure
    # Upload to openAI
    # Save in DB 


    # TODO  - add argrument league_id
    # TODO - Get from DB the Yahoo Tokens
    # TODO - Get the League from Yahoo SDK
    # TODO - Call Sync League with the League