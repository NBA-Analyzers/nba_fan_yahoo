import requests
import json
from datetime import datetime
from typing import Dict, List, Optional
import time
class ESPNInjuryManager:
    """
    ESPN Fantasy API injury data manager for fantasy basketball
    Focused on fantasy-relevant injury information
    """
    
    def __init__(self):
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
        self.cache = {}
        self.cache_duration = 300  # 5 minutes cache
    
    def get_all_injuries(self, force_refresh: bool = False) -> Dict:
        """
        Get all current NBA player injuries from ESPN
        
        Args:
            force_refresh: Skip cache and fetch fresh data
            
        Returns:
            Dict with organized injury data
        """
        cache_key = "all_injuries"
        
        # Check cache first
        if not force_refresh and self._is_cache_valid(cache_key):
            return self.cache[cache_key]['data']
        
        try:
            print("Fetching fresh injury data from ESPN...")
            
            # Get all NBA athletes from ESPN
            url = f"{self.base_url}/athletes"
            params = {
                'limit': 600,  # Ensure we get all players
                'active': 'true'
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract injured players
            injured_players = self._extract_injured_players(data)
            
            # Process and organize the data
            processed_data = self._process_injury_data(injured_players)
            
            # Cache the results
            self.cache[cache_key] = {
                'data': processed_data,
                'timestamp': datetime.now()
            }
            
            print(f"✅ Found {len(injured_players)} injured players")
            return processed_data
            
        except requests.RequestException as e:
            print(f"❌ ESPN API request failed: {e}")
            return self._get_empty_injury_report()
        except Exception as e:
            print(f"❌ Error processing injury data: {e}")
            return self._get_empty_injury_report()

    def _extract_injured_players(self, espn_data: Dict) -> List[Dict]:
        """Extract injured players from ESPN API response"""
        injured_players = []
        
        athletes = espn_data.get('athletes', [])
        
        for athlete in athletes:
            # Check if player has any injuries
            injuries = athlete.get('injuries', [])
            
            if injuries:
                # Get the most recent/relevant injury
                current_injury = injuries[0]  # ESPN puts most recent first
                
                player_info = {
                    'player_id': athlete.get('id'),
                    'name': athlete.get('displayName', 'Unknown Player'),
                    'first_name': athlete.get('firstName', ''),
                    'last_name': athlete.get('lastName', ''),
                    'team_id': athlete.get('team', {}).get('id'),
                    'team': athlete.get('team', {}).get('abbreviation', 'FA'),
                    'team_name': athlete.get('team', {}).get('displayName', 'Free Agent'),
                    'position': athlete.get('position', {}).get('abbreviation', 'N/A'),
                    'jersey_number': athlete.get('jersey', 'N/A'),
                    'headshot': athlete.get('headshot', {}).get('href', ''),
                    
                    # Injury details
                    'injury_status': current_injury.get('status', 'UNKNOWN').upper(),
                    'injury_type': current_injury.get('type', 'Undisclosed'),
                    'injury_description': current_injury.get('longComment', ''),
                    'injury_short_comment': current_injury.get('shortComment', ''),
                    'date_injured': current_injury.get('date', ''),
                    'details': current_injury.get('details', ''),
                
                    
                    # Metadata
                    'last_updated': datetime.now().isoformat()
                }
                
                injured_players.append(player_info)
        
        return injured_players
    def _get_empty_injury_report(self) -> Dict:
        """Return empty injury report structure"""
        return {
            'summary': {
                'last_updated': datetime.now().isoformat(),
                'total_injured': 0,
                'out': 0, 'doubtful': 0, 'questionable': 0, 'day_to_day': 0, 'probable': 0
            },
            'by_status': {}, 'by_team': {}, 'by_impact': {'HIGH': [], 'MEDIUM': [], 'LOW': [], 'UNKNOWN': []},
            'non_startable': [], 'monitor_closely': [], 'all_players': []
        }

    def _process_injury_data(self, injured_players: List[Dict]) -> Dict:
        """Organize injury data for easy consumption"""
        processed = {
            'summary': {
                'last_updated': datetime.now().isoformat(),
                'total_injured': len(injured_players),
                'out': len([p for p in injured_players if p['injury_status'] == 'OUT']),
                'doubtful': len([p for p in injured_players if p['injury_status'] == 'DOUBTFUL']),
                'questionable': len([p for p in injured_players if p['injury_status'] == 'QUESTIONABLE']),
                'day_to_day': len([p for p in injured_players if p['injury_status'] == 'DAY_TO_DAY']),
                'probable': len([p for p in injured_players if p['injury_status'] == 'PROBABLE'])
            },
            'by_status': {},
            'by_team': {},
            'by_impact': {'HIGH': [], 'MEDIUM': [], 'LOW': [], 'UNKNOWN': []},
            'non_startable': [],  # OUT + DOUBTFUL players
            'monitor_closely': [],  # QUESTIONABLE + DAY_TO_DAY
            'all_players': injured_players
        }
        
        # Organize data
        for player in injured_players:
            status = player['injury_status']
            team = player['team']
            impact = player['fantasy_impact']
            
            # By status
            if status not in processed['by_status']:
                processed['by_status'][status] = []
            processed['by_status'][status].append(player)
            
            # By team
            if team not in processed['by_team']:
                processed['by_team'][team] = []
            processed['by_team'][team].append(player)
            
            # By fantasy impact
            processed['by_impact'][impact].append(player)
            
            # Fantasy-specific groupings
            if not player['is_startable']:
                processed['non_startable'].append(player)
            elif status in ['QUESTIONABLE', 'DAY_TO_DAY']:
                processed['monitor_closely'].append(player)
        
        return processed
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self.cache:
            return False
        
        cache_age = datetime.now() - self.cache[cache_key]['timestamp']
        return cache_age.total_seconds() < self.cache_duration