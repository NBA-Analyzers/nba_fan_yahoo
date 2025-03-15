# NBA Fantasy League Analyzer

## Overview
NBA Fantasy League Analyzer is a Python-based tool designed to analyze fantasy basketball leagues using the **Yahoo Fantasy API** and **NBA API**. It retrieves league and player statistics, processes them, and provides insights into player and team performance.

## Features
- **Yahoo Fantasy League Integration**: Syncs fantasy league data from Yahoo.
- **NBA API Integration**: Fetches real-world player statistics.
- **Database Storage**: Stores player and league data in a Microsoft SQL Server database.
- **Team and Player Analysis**: Provides statistical insights into individual players and teams.
- **League-wide Analysis**: Aggregates and compares team performances.

## Project Structure
nba_fantasy/ │── database.py # Inserts NBA player data into the database │── LeagueAnalyzer.py # Analyzes league-wide performance │── PlayerAnalyzer.py # Retrieves and processes player stats │── TeamAnalyzer.py # Computes team stats based on player data │── YahooLeague.py # Handles Yahoo Fantasy API interactions │── main.py # Entry point for running the analysis

## Installation
### Prerequisites
- Python 3.8+
- Microsoft SQL Server
- Yahoo Fantasy API Credentials
- Required Python packages: pip install pandas pyodbc yahoo_fantasy_api nba_api
  
## Usage
1. **Set up Yahoo Fantasy API authentication**  
 Ensure `oauth22.json` is correctly configured for OAuth2 authentication.

2. **Run the main script**  python main.py
   This script fetches league data, analyzes team and player performance, and outputs results.

## Future Improvements
- Add visualization for player and team stats.
- Implement an interactive UI for better insights.
- Expand database schema for additional analytics.
- Use LLMs to generate reports, predict player performances, and suggest strategies.



