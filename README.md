# Getting Started

## Install Python

[https://www.python.org/downloads/](https://www.python.org/downloads/)

## Create Python Virtual Environment

Virtual environment setup:
`python -m venv yas-env`
macos/linux:
`source yas-env/bin/activate`
windows:
`yas-env\Scripts\activate`

## Install Python Dependencies

`pip install -r requirements.txt`

## Create Google Dev Project + API Key

1. Create a Google Cloud Project

- https://console.cloud.google.com/
- Click "New Project" at the top left.
- Name it "YouTube Shorts Uploader"
- Click "Create"

2. Enable YouTube Data API v3

- Go to "APIs & Services" > "Library"
- Click "+ Enable APIs and services"
- Search for "YouTube Data API v3"
- Click into it and then click "Enable"

3. Create an oAuth2 Auth Flow

- Click on the "Create Credentials" at the top right.
- Set Select an API to "YouTube Data API v3"
- Set Credential Type to "User Data"
- Click "Next"
- Set App Name to "youtube-shorts-uploader"
- Set user support e-mail to your gmail account.
- Set developer contact information to your gmail account.
- Click "Add or remove scopes"
- Scroll down to Manually add scopes and enter "https://www.googleapis.com/auth/youtube.upload"
- Click "Add to Table"
- Click either "Update" or "Save"
- Verify that it added under "Your sensitive scopes"
- Click "Save and continue"
- Under OAuth Client ID
  - Application type: Desktop App
  - Name: youtube-shorts-uploader

4. Add yourself as a test user

- Go to your project

## Create a Video List file.

```bash
python yas.py --generate
```

When you run the command above, it will create a file with today's date in the ./video_lists sub-directory of this folder.

That file will contain an editable list of all of the videos you haver copied into the ./videos/ sub-directory.

This will allow you to set descriptions, release dates, and tags for each video you want to upload.

## Upload Video Files
