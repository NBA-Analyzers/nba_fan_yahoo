### How To Run Locally 

## 2 Options: 

# 1. If you want to run and get an example League without Login with Yahoo, insert at .env file:
```bash
export DEBUG=True
```

# 2. If you want to Login with Yahoo follow this steps:

1. Install Ngrok  
   Download and install ngrok from: https://ngrok.com/download

2. Start your local server  
   ```bash
   python src/yahoo_login.py
   ```

3. Run Ngrok  
   In a new terminal, start ngrok to tunnel port 5001:
   ```bash
   ngrok http 5001
   ```
   Copy the HTTPS forwarding URL that ngrok provides (e.g., `https://xxxx.ngrok-free.app`).

4. Set your Yahoo API redirect URI  
   - Go to the [Yahoo Developer Console](https://developer.yahoo.com/apps/)
   - Create your app and set the redirect URI to the ngrok HTTPS URL (e.g., `https://xxxx.ngrok-free.app/callback`).

5. Enviroment Variables
   - Create .env file from .env.template
   - Paste from Yahoo API your client id as YAHOO_CLIENT_ID and client secret as YAHOO_CLIENT_SECRET
   - Set also YAHOO_REDIRECT_URL to the ngrok HTTPS URL (e.g., `https://xxxx.ngrok-free.app`).
   - Leave Google Keys empty in this stage.

6. Start the OAuth flow  
   - Open your browser and go to your ngrok HTTPS URL (e.g., `https://xxxx.ngrok-free.app`)
   - Click "Login with Yahoo" to begin authentication.

