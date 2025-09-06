import time
import xml.etree.ElementTree as ET
from datetime import datetime
from flask import session
from ..supaBase.repositories.yahoo_league_repository import YahooLeagueRepository
from ..fantasy_platforms_integration.yahoo.sync_yahoo_league import YahooLeague
from ..azure.azure_blob_storage import AzureBlobStorage
import os

class YahooService:
    def __init__(self, token_store):
        self.token_store = token_store
        
    def get_user_leagues(self, user_guid):
        """Get user's leagues from Yahoo API"""
        try:
            from ..utils.helpers import get_yahoo_sdk
            yahoo_game = get_yahoo_sdk(self.token_store, {'user': user_guid})
            if not yahoo_game:
                return []
                
            league_ids = yahoo_game.league_ids()
            league_options = []
            for league_id in league_ids:
                league = yahoo_game.to_league(league_id)
                league_name = league.settings()['name']
                league_options.append({'id': league_id, 'name': league_name})
            return league_options
        except Exception as e:
            print(f"❌ Error getting user leagues: {e}")
            return []
    
    def sync_league_data(self, league_id, user_guid, azure_container="fantasy1"):
        """Sync league data and store in database"""
        try:
            from ..utils.helpers import get_yahoo_sdk
            yahoo_game = get_yahoo_sdk(self.token_store, {'user': user_guid})
            if not yahoo_game:
                return {"error": "Yahoo SDK not available"}
                
            league = yahoo_game.to_league(league_id)
            
            # Get league information for database insertion
            league_settings = league.settings()
            league_name = league_settings.get('name', 'Unknown League')
            
            # Get user's team information
            teams = league.teams()
            user_team_name = None
            
            # Get the user's actual team key from Yahoo API
            try:
                user_team_key = league.team_key()  # This gets YOUR actual team key
                if user_team_key and user_team_key in teams:
                    user_team_name = teams[user_team_key].get('name', 'Unknown Team')
                else:
                    print(f"⚠️ User team key {user_team_key} not found in teams list")
                    # Fallback to first team if user team not found
                    if teams:
                        first_team_key = list(teams.keys())[0]
                        user_team_name = teams[first_team_key].get('name', 'Unknown Team')
            except Exception as e:
                print(f"⚠️ Error getting user team key: {e}")
                # Fallback to first team if there's an error
                if teams:
                    first_team_key = list(teams.keys())[0]
                    user_team_name = teams[first_team_key].get('name', 'Unknown Team')
            
            # Get yahoo_user_id from token store
            yahoo_user_id = self.token_store[user_guid].get('xoauth_yahoo_guid') or self.token_store[user_guid].get('guid')
            if not yahoo_user_id:
                return {"error": "Yahoo user ID not found"}
            
            # Insert into yahoo_league table
            yahoo_league_repo = YahooLeagueRepository()
            league_data = {
                'yahoo_user_id': yahoo_user_id,
                'league_id': league_id,
                'team_name': user_team_name or 'Unknown Team',
                'created_at': datetime.now().isoformat()
            }
            
            # Check if league already exists for this user
            existing_league = yahoo_league_repo.get_by_league_id(league_id)
            if existing_league:
                # Update existing record
                yahoo_league_repo.update_by_league_id(league_id, league_data)
                db_message = "League updated in database"
            else:
                # Create new record
                yahoo_league_repo.create(league_data)
                db_message = "League added to database"
            
            # Sync league data
            yahoo_league = YahooLeague(league)
            
            # Check if Azure Storage is configured
            azure_connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if azure_connection_string:
                try:
                    azure_storage = AzureBlobStorage(container_name=azure_container)
                    results = yahoo_league.sync_full_league(azure_storage)
                except Exception as azure_error:
                    print(f"⚠️ Azure Storage error: {azure_error}")
                    results = {"warning": "Azure Storage not available, data not backed up"}
            else:
                print("⚠️ Azure Storage not configured, skipping data backup")
                results = {"warning": "Azure Storage not configured, data not backed up"}
            
            return {
                "success": True,
                "db_message": db_message,
                "sync_results": results
            }
            
        except Exception as e:
            print(f"❌ Error during league sync: {e}")
            return {"error": str(e)}
    
    def get_user_synced_leagues(self, user_guid):
        """Get user's synced leagues from database"""
        try:
            yahoo_user_id = self.token_store[user_guid].get('xoauth_yahoo_guid') or self.token_store[user_guid].get('guid')
            if not yahoo_user_id:
                return []
            
            yahoo_league_repo = YahooLeagueRepository()
            return yahoo_league_repo.get_by_yahoo_user_id(yahoo_user_id)
        except Exception as e:
            print(f"❌ Error retrieving user leagues: {e}")
            return []
