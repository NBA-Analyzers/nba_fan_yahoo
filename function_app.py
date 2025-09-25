import azure.functions as func
app = func.FunctionApp()

@app.function_name(name="sync_full_league")
@app.route(route="sync_full_league", auth_level=func.AuthLevel.ANONYMOUS)
def test_sync_full_league(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("Hello, World!")