import os.path
import json
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.cloud import firestore # <-- NEW IMPORT

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
TOC_DOCUMENT_URL = 'https://docs.google.com/document/d/1RFGdf5q8kHueTwThJvt7ITkhsSqsin39hHl5ugIveX8/edit?usp=sharing'

def get_credentials():
    """Handles user authentication and returns valid credentials."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=8081)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def read_paragraph_text(elements):
    """Reads the text from a list of paragraph elements."""
    text = ''
    for element in elements:
        if 'textRun' in element:
            text += element.get('textRun').get('content')
    return text

def get_lesson_urls(docs_service, document_id):
    """Reads the TOC doc and extracts all lesson URLs."""
    # This function remains the same as before.
    print("Reading Table of Contents to find lesson URLs...")
    urls = {}
    try:
        document = docs_service.documents().get(documentId=document_id).execute()
        content = document.get('body').get('content')
        for element in content:
            if 'paragraph' in element:
                para_elements = element.get('paragraph').get('elements')
                for para_element in para_elements:
                    if 'textRun' in para_element:
                        text_run = para_element.get('textRun')
                        text_style = text_run.get('textStyle')
                        if text_style and 'link' in text_style:
                            text = text_run.get('content').strip()
                            url = text_style.get('link').get('url')
                            if text and url and 'docs.google.com' in url:
                                urls[text] = url
        print(f"Found {len(urls)} lesson links.")
        return urls
    except HttpError as err:
        print(f"Error reading TOC: {err}")
        return {}

def parse_lesson_doc(docs_service, title, url):
    """
    Reads a single lesson doc and intelligently parses it into structured sections.
    """
    print(f"  -> Parsing lesson: '{title}'")
    try:
        doc_id = url.split('/d/')[1].split('/')[0]
        document = docs_service.documents().get(documentId=doc_id).execute()
        content = document.get('body').get('content')
        
        today_date = datetime.date.today().isoformat()
        lesson_data = {
            'title': title,
            'url': url,
            'version': '1.0',
            'date_updated': today_date,
            'goal': '',
            'outcomes': [],
            'talking_points': '',
            'resources': [],
            'philosophy': '',
            'other_notes': '',
            'tasks': []
        }
        
        current_section = None
        
        for element in content:
            if 'paragraph' in element:
                para = element.get('paragraph')
                text = read_paragraph_text(para.get('elements')).strip()

                if not text:
                    continue

                if text.startswith('Version:'):
                    lesson_data['version'] = text.replace('Version:', '').strip()
                    current_section = None
                elif text.startswith('Date:'):
                    lesson_data['date_updated'] = text.replace('Date:', '').strip()
                    current_section = None
                elif text.startswith('Chapter Goal:'):
                    current_section = 'goal'
                    lesson_data['goal'] = text.replace('Chapter Goal:', '').strip()
                elif text.startswith('By the end of this chapter you will be able to:'):
                    current_section = 'outcomes'
                elif text.startswith('Advisor Talking Points (Cliff Version):'):
                    current_section = 'talking_points'
                    lesson_data['talking_points'] = text.replace('Advisor Talking Points (Cliff Version):', '').strip()
                elif text.startswith('Key Advisor Tools/Resources:'):
                    current_section = 'resources'
                elif text.startswith('Abundo Philosophy:'):
                    current_section = 'philosophy'
                    lesson_data['philosophy'] = text.replace('Abundo Philosophy:', '').strip()
                elif text.startswith('Other Notes:'):
                    current_section = 'other_notes'
                    lesson_data['other_notes'] = text.replace('Other Notes:', '').strip()
                elif text.startswith('Chapter Task List'):
                    current_section = 'tasks'
                else:
                    if current_section == 'goal':
                        lesson_data['goal'] += ' ' + text
                    elif current_section == 'outcomes':
                        lesson_data['outcomes'].append(text)
                    elif current_section == 'talking_points':
                        lesson_data['talking_points'] += ' ' + text
                    elif current_section == 'resources':
                        lesson_data['resources'].append(text)
                    elif current_section == 'philosophy':
                        lesson_data['philosophy'] += ' ' + text
                    elif current_section == 'other_notes':
                        lesson_data['other_notes'] += ' ' + text
                    elif current_section == 'tasks':
                        is_bold = para.get('elements')[0].get('textRun').get('textStyle').get('bold', False)
                        if is_bold:
                            lesson_data['tasks'].append({'title': text, 'description': ''})
                        elif lesson_data['tasks']:
                            lesson_data['tasks'][-1]['description'] += ' ' + text
        
        return lesson_data

    except HttpError as err:
        print(f"    ERROR: Could not parse doc '{title}'. Reason: {err}")
        return None

def main():
    """Main function to run the parser and upload to Firestore."""
    creds = get_credentials()
    docs_service = build('docs', 'v1', credentials=creds)
    
    toc_doc_id = TOC_DOCUMENT_URL.split('/d/')[1].split('/')[0]
    lesson_urls = get_lesson_urls(docs_service, toc_doc_id)

    if not lesson_urls:
        print("No lesson URLs found. Exiting.")
        return

    # --- NEW FIRESTORE LOGIC ---
    # Initialize Firestore client
    db = firestore.Client()
    print("\nUploading lessons to Firestore...")

    for title, url in lesson_urls.items():
        if "Getting Started" in title or "The Abundo High Five" in title:
            print(f"  -> Skipping non-lesson doc: '{title}'")
            continue
        
        lesson_data = parse_lesson_doc(docs_service, title, url)
        if lesson_data:
            # We will use the lesson title as the unique ID for the document.
            # We replace slashes to make it a valid ID.
            doc_id = title.replace('/', '-')
            
            # Get a reference to the document and upload the data
            doc_ref = db.collection('ContentMaster').document(doc_id)
            doc_ref.set(lesson_data)
            print(f"    -> Successfully uploaded '{title}'")
    
    print("\nSUCCESS! All content has been uploaded to the Firestore 'ContentMaster' collection.")

if __name__ == '__main__':
    main()