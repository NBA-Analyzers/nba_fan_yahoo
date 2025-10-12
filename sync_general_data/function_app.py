import azure.functions as func
app = func.FunctionApp()

@app.function_name(name="sync_full_league")
@app.route(route="sync_full_league", auth_level=func.AuthLevel.ANONYMOUS)
def test_sync_full_league(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("Hello, World!")
    # TODO - Box Score + Injuries
    # Upload to Azure
    # Upload to openAI
    # Save in DB 

    
    # TODO  - add argrument league_id
    # TODO - Get from DB the Yahoo Tokens
    # TODO - Get the League from Yahoo SDK
    # TODO - Call Sync League with the League