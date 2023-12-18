from nba_api.stats.static import players
import pyodbc

connection = pyodbc.connect('Driver={SQL Server};'
                            'Server=PC-URI;'
                            'Database=NBA_API;'
                            'Trusted_Connection=yes;')

cursor = connection.cursor()

# Define your SQL INSERT statement
insert_query_players = "INSERT INTO players (id, last_name, first_name, full_name, is_active) VALUES (?, ?, ?, ?, ?)"

# Get the list of players
player_data = players.get_players()

# Iterate over the player data and insert each player into the database
for player in player_data:
    data = (player['id'], player['last_name'], player['first_name'], player['full_name'], player['is_active'])
    cursor.execute(insert_query_players, data)

# Commit the changes to the database
connection.commit()

# Close the cursor and connection
cursor.close()
connection.close()
