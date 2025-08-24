from services.auth_services import AuthService
from services.fantasy_services import FantasyService
from services.league_services import LeagueService
from models.google_auth import GoogleAuth
from models.yahoo_auth import YahooAuth
from models.google_fantasy import GoogleFantasy
from models.yahoo_league import YahooLeague
from exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError

def main():
    # Initialize services
    auth_service = AuthService()
    fantasy_service = FantasyService()
    league_service = LeagueService()
    
    try:
        # 1. User signs in with Google
        google_user = GoogleAuth(
            google_user_id="google_123",
            full_name="John Doe",
            email="john.doe@gmail.com",
            access_token="google_token_123"
        )
        created_google_user = auth_service.create_or_update_google_user(google_user)
        print(f"✅ Google user created: {created_google_user.full_name}")
        
        # 2. User connects Yahoo account
        yahoo_user = YahooAuth(
            yahoo_user_id="yahoo_456",
            access_token="yahoo_access_123",
            refresh_token="yahoo_refresh_123"
        )
        created_yahoo_user = auth_service.create_or_update_yahoo_user(yahoo_user)
        print(f"✅ Yahoo user created: {created_yahoo_user.yahoo_user_id}")
        
        # 3. Link Google user to Yahoo account
        fantasy_connection = GoogleFantasy(
            google_user_id="google_123",
            fantasy_user_id="yahoo_456",  # FK to yahoo_auth
            fantasy_platform="yahoo"
        )
        created_connection = fantasy_service.connect_fantasy_platform(fantasy_connection)
        print(f"✅ Fantasy connection created: Google -> Yahoo")
        
        # 4. Add Yahoo leagues
        league1 = YahooLeague(
            yahoo_user_id="yahoo_456",
            league_id="league_789",
            team_name="John's Team"
        )
        created_league = league_service.create_yahoo_league(league1)
        print(f"✅ League created: {created_league.team_name}")
        
        # 5. Get user's leagues through Google ID
        leagues = league_service.get_yahoo_leagues_by_google_user("google_123")
        print(f"✅ Found {len(leagues)} leagues for Google user")
        
        # 6. Get all fantasy connections for Google user
        connections = fantasy_service.get_user_fantasy_connections("google_123")
        print(f"✅ User has {len(connections)} fantasy platform connections")
        
    except ValidationError as e:
        print(f"❌ Validation error: {e}")
    except NotFoundError as e:
        print(f"❌ Not found error: {e}")
    except DuplicateError as e:
        print(f"❌ Duplicate error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()