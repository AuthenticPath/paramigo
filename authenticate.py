import os
from google_auth_oauthlib.flow import InstalledAppFlow

# This is the scope we defined in the Google Cloud Console.
# It requests read-only access to Google Drive.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def main():
    """
    This function handles the user authentication flow.
    """
    creds = None
    
    # The file token.json stores the user's access and refresh tokens.
    # It is created automatically when the authorization flow completes for the first time.
    if os.path.exists('token.json'):
        print("Token file already exists. Authentication successful.")
        return

    # If there are no (valid) credentials available, let the user log in.
    # This will read your 'client_secret.json' file.
    flow = InstalledAppFlow.from_client_secrets_file(
        'client_secret.json', SCOPES)
    
    # This line will automatically open a browser window for you to log in.
    creds = flow.run_local_server(port=8080)
    
    # Save the credentials for the next run
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
        
    print("Authentication successful! A 'token.json' file has been created.")

if __name__ == '__main__':
    main()