import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_refresh_token():
    try:
        # 1. Check if token.json already exists
        if os.path.exists('token.json'):
            print("[DEBUG] token.json found, checking validity...")
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            if creds and creds.valid:
                print("[INFO] Token is still valid – no need to re‑authenticate.")
                return
            if creds and creds.expired and creds.refresh_token:
                print("[DEBUG] Token expired, refreshing...")
                creds.refresh(Request())
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
                print("[INFO] Token refreshed successfully.")
                return

        # 2. Check for credentials.json
        if not os.path.exists('credentials.json'):
            print("[ERROR] credentials.json not found in the current folder!")
            print("[FIX] Download your OAuth client ID from Google Cloud Console and save as 'credentials.json'.")
            sys.exit(1)

        print("[DEBUG] Starting OAuth flow...")
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        
        # 3. Run local server – this should open a browser.
        # If the browser doesn't open, the terminal will print a URL.
        print("[INFO] A browser window should open. If it doesn't, look for a URL in the terminal below.")
        creds = flow.run_local_server(port=0, open_browser=True)
        
        # 4. Save the token
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        print("[SUCCESS] token.json saved. You can now run the bot!")

    except Exception as e:
        print(f"[FATAL ERROR] {e}")
        print("[DEBUG] Full exception details:", file=sys.stderr)
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    get_refresh_token()