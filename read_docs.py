import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def main():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        docs_service = build('docs', 'v1', credentials=creds)

        doc_url = 'https://docs.google.com/document/d/1RFGdf5q8kHueTwThJvt7ITkhsSqsin39hHl5ugIveX8/edit?usp=sharing'
        
        document_id = doc_url.split('/d/')[1].split('/')[0]

        document = docs_service.documents().get(documentId=document_id).execute()
        
        print(f"SUCCESS! Reading links from document: '{document.get('title')}'")
        print("-" * 30)

        # --- UPDATED CODE STARTS HERE ---
        doc_content = document.get('body').get('content')
        
        print("Found the following links:")
        
        # Loop through each structural element in the document
        for element in doc_content:
            if 'paragraph' in element:
                para_elements = element.get('paragraph').get('elements')
                for para_element in para_elements:
                    if 'textRun' in para_element:
                        text_run = para_element.get('textRun')
                        
                        # Check if this textRun has a link style attached
                        text_style = text_run.get('textStyle')
                        if text_style and 'link' in text_style:
                            # It's a link! Let's get the text and the URL.
                            visible_text = text_run.get('content').strip()
                            url = text_style.get('link').get('url')
                            
                            # We only want to print if both text and URL exist
                            if visible_text and url:
                                print(f"  - {visible_text} -> {url}")
        # --- UPDATED CODE ENDS HERE ---

    except HttpError as err:
        print(err)

if __name__ == '__main__':
    main()