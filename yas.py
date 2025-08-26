#!/usr/bin/env python3

import os
import sys
import re
import csv
import pickle
from datetime import datetime
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv

class YouTubeUploader:
    def __init__(self):
        load_dotenv()
        self.scopes = ['https://www.googleapis.com/auth/youtube.upload']
        self.credentials_file = './credentials/client_secret_1013418193976-ljeiugr28a0umkd6tju9pkmimkgcrdpa.apps.googleusercontent.com.json'
        self.token_file = './credentials/token.pickle'
        
        # Create credentials directory if it doesn't exist
        os.makedirs('./credentials', exist_ok=True)
        
        self.youtube = self._authenticate()
    
    def _authenticate(self):
        creds = None
        
        # Load existing token if available
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Token refresh failed: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(f"OAuth2 credentials file not found: {self.credentials_file}")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.scopes)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return build('youtube', 'v3', credentials=creds)
    
    def extract_hashtags_from_description(self, description):
        """Extract hashtags from description text and return as list
        
        Finds all #hashtag patterns in the description and returns them as a clean list
        without the # symbol for use with YouTube API tags field.
        """
        if not description:
            return []
        
        # Find all hashtags (# followed by word characters, allowing underscores)
        hashtag_pattern = r'#(\w+)'
        hashtags = re.findall(hashtag_pattern, description, re.IGNORECASE)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_hashtags = []
        for tag in hashtags:
            if tag.lower() not in seen:
                seen.add(tag.lower())
                unique_hashtags.append(tag)
        
        return unique_hashtags
    
    def parse_datetime(self, date_str, time_str=None):
        """Convert date and time strings to ISO 8601 format for YouTube API
        
        Supports multiple formats:
        - Legacy: parse_datetime('08/21/25', '5PM EST') 
        - New: parse_datetime('08-27-25 8PM PST')
        - ISO: parse_datetime('2025-08-27T16:00:00Z') - passes through
        """
        if not date_str:
            return None
        
        # If it's already in ISO 8601 format, return as-is
        if 'T' in date_str and (':' in date_str):
            try:
                # Validate the ISO format
                datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return date_str
            except ValueError:
                pass  # Fall through to parsing
        
        # Handle combined format: "08-27-25 8PM PST"
        if time_str is None and ' ' in date_str:
            parts = date_str.split(' ', 1)
            date_str = parts[0]
            time_str = parts[1]
        
        if not time_str:
            return None
            
        try:
            # Parse date - support both MM/DD/YY and MM-DD-YY formats
            if '/' in date_str:
                date_parts = date_str.split('/')
            elif '-' in date_str:
                date_parts = date_str.split('-')
            else:
                return None
                
            if len(date_parts) == 3:
                month, day, year = date_parts
                # Convert 2-digit year to 4-digit
                if len(year) == 2:
                    year = f"20{year}"
            else:
                return None
            
            # Parse time (e.g., "5PM EST", "8:30AM PST")
            time_str = time_str.strip().upper()
            
            # Extract timezone - automatically handle DST
            timezone_map = {
                'EST': '-04:00', 'PST': '-07:00', 'CST': '-05:00', 'MST': '-06:00',  # Assume DST during summer
                'EDT': '-04:00', 'PDT': '-07:00', 'CDT': '-05:00', 'MDT': '-06:00',
                'ET': '-04:00', 'PT': '-07:00', 'CT': '-05:00', 'MT': '-06:00'  # Generic time zones (assume current DST)
            }
            
            timezone_offset = '+00:00'  # Default to UTC
            for tz, offset in timezone_map.items():
                if tz in time_str:
                    timezone_offset = offset
                    time_str = time_str.replace(tz, '').strip()
                    break
            
            # Parse time part
            if 'PM' in time_str or 'AM' in time_str:
                is_pm = 'PM' in time_str
                time_part = time_str.replace('PM', '').replace('AM', '').strip()
                
                if ':' in time_part:
                    hours, minutes = time_part.split(':')
                else:
                    hours = time_part
                    minutes = '00'
                
                hours = int(hours)
                minutes = int(minutes)
                
                # Convert to 24-hour format
                if is_pm and hours != 12:
                    hours += 12
                elif not is_pm and hours == 12:
                    hours = 0
            else:
                return None
            
            # Create ISO 8601 datetime string
            iso_datetime = f"{year}-{month.zfill(2)}-{day.zfill(2)}T{hours:02d}:{minutes:02d}:00{timezone_offset}"
            
            # Validate by parsing
            datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))
            
            return iso_datetime
            
        except (ValueError, IndexError) as e:
            print(f"Warning: Could not parse datetime '{date_str} {time_str if time_str else ''}': {e}")
            return None
    
    def parse_manifest(self, manifest_path):
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
        
        videos = []
        
        # Check if it's a CSV file
        if manifest_path.lower().endswith('.csv'):
            with open(manifest_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Extract tags from hashtags in description instead of tags column
                    description = row.get('description', '').strip()
                    tags = self.extract_hashtags_from_description(description)
                    
                    # Support both old and new CSV formats
                    video_filename = row.get('fileName', '') or row.get('video_filename', '')
                    privacy_status = row.get('privacy', 'private').lower()
                    publish_at_raw = row.get('publishAt', '').strip()
                    
                    # Convert human-readable publishAt to ISO 8601
                    publish_at = None
                    if publish_at_raw:
                        publish_at = self.parse_datetime(publish_at_raw)
                    
                    # Handle legacy format: combine release_date + release_time if publishAt not provided
                    if not publish_at:
                        release_date = row.get('release_date', '').strip()
                        release_time = row.get('release_time', '').strip()
                        if release_date and release_time:
                            publish_at = self.parse_datetime(release_date, release_time)
                    
                    video_data = {
                        'video_filename': video_filename.strip(),
                        'title': row.get('title', '').strip(),
                        'description': description,
                        'tags': tags,
                        'privacy_status': privacy_status,
                        'publish_at': publish_at,
                        'playlist': row.get('playlist', '').strip(),
                        # Keep legacy fields for backwards compatibility
                        'release_date': row.get('release_date', '').strip(),
                        'release_time': row.get('release_time', '').strip()
                    }
                    
                    if video_data['video_filename']:
                        videos.append(video_data)
        
        else:
            # Legacy markdown support (kept for backwards compatibility)
            with open(manifest_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split content by video sections (starting with # filename)
            video_sections = re.split(r'\n(?=# \w+\.\w+)', content)
            
            for section in video_sections:
                section = section.strip()
                if not section:
                    continue
                
                # Extract video filename from heading
                lines = section.split('\n')
                video_filename = None
                
                for line in lines:
                    if line.startswith('# '):
                        video_filename = line[2:].strip()
                        break
                
                if not video_filename:
                    continue
                
                # Look for YAML frontmatter between --- markers
                frontmatter_match = re.search(r'---\s*\n(.*?)\n\s*---', section, re.DOTALL)
                
                if not frontmatter_match:
                    continue
                
                # Parse YAML frontmatter
                try:
                    import yaml
                    frontmatter_yaml = frontmatter_match.group(1)
                    metadata = yaml.safe_load(frontmatter_yaml)
                except Exception as e:
                    print(f"Error parsing YAML for {video_filename}: {e}")
                    continue
                
                # Extract content after the second --- marker
                closing_match = re.search(r'---\s*\n(.*?)\n\s*---\s*\n(.*)$', section, re.DOTALL)
                if closing_match:
                    content_after_frontmatter = closing_match.group(2).strip()
                else:
                    content_after_frontmatter = ""
                
                # Parse description and tags
                description_lines = []
                tags = []
                
                for line in content_after_frontmatter.split('\n'):
                    line = line.strip()
                    if line.startswith('- '):
                        tags.append(line[2:].strip())
                    elif line and not line.startswith('- '):
                        description_lines.append(line)
                
                video_data = {
                    'video_filename': video_filename,
                    'title': metadata.get('title', video_filename),
                    'description': '\n'.join(description_lines).strip(),
                    'tags': tags,
                    'release_date': metadata.get('release_date'),
                    'release_time': metadata.get('release_time')
                }
                
                videos.append(video_data)
        
        return videos
    
    def upload_short(self, video_path, title, description="", tags=None, privacy_status="private", publish_at=None, playlist=None):
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        tags = tags or []
        
        # Build status object
        status = {'privacyStatus': privacy_status.lower()}
        
        # Add scheduled publish time if provided
        if publish_at:
            status['publishAt'] = publish_at
            # Note: For scheduled videos, they start as private and become the specified privacy at publish time
        
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': '22'  # People & Blogs category
            },
            'status': status
        }
        
        media = MediaFileUpload(
            video_path,
            chunksize=-1,
            resumable=True,
            mimetype='video/*'
        )
        
        try:
            insert_request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = insert_request.execute()
            
            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            print(f"Upload successful!")
            print(f"Video ID: {video_id}")
            print(f"Video URL: {video_url}")
            print(f"Title: {title}")
            print(f"Status: Private (will become public if scheduled)")
            
            return {
                'video_id': video_id,
                'video_url': video_url,
                'title': title,
                'privacy_status': 'private'
            }
            
        except HttpError as e:
            print(f"An HTTP error occurred: {e}")
            return None
        except Exception as e:
            print(f"An error occurred: {e}")
            return None
    
    def upload_from_manifest(self, manifest_path, video_directory=None):
        videos_metadata = self.parse_manifest(manifest_path)
        
        # Default to ./videos/ subdirectory if not specified
        if video_directory is None:
            video_directory = "./videos/"
        
        video_dir = Path(video_directory)
        
        results = []
        for metadata in videos_metadata:
            # Look for the exact video filename specified in the manifest
            video_path = video_dir / metadata['video_filename']
            
            if not video_path.exists():
                print(f"Warning: Video file not found: {video_path}")
                continue
            
            # Handle publish time - use publishAt if available, otherwise parse legacy format
            publish_at = metadata.get('publish_at', '').strip()
            if not publish_at and metadata.get('release_date') and metadata.get('release_time'):
                publish_at = self.parse_datetime(metadata['release_date'], metadata['release_time'])
            
            privacy_status = metadata.get('privacy_status', 'private')
            playlist = metadata.get('playlist', '').strip()
            
            print(f"\nUploading: {metadata['title']}")
            print(f"Video file: {video_path}")
            print(f"Privacy: {privacy_status}")
            if publish_at:
                print(f"Scheduled for: {publish_at}")
            if playlist:
                print(f"Playlist: {playlist}")
                print("Note: Playlist functionality not yet implemented - video will upload without playlist assignment")
            
            result = self.upload_short(
                video_path=str(video_path),
                title=metadata['title'],
                description=metadata['description'],
                tags=metadata['tags'],
                privacy_status=privacy_status,
                publish_at=publish_at,
                playlist=playlist
            )
            
            if result:
                result.update({
                    'release_date': metadata.get('release_date'),
                    'release_time': metadata.get('release_time')
                })
                results.append(result)
            else:
                print(f"Failed to upload: {metadata['title']}")
        
        return results
    
    def generate_manifest(self, video_directory="./videos/", output_file=None):
        video_dir = Path(video_directory)
        
        if not video_dir.exists():
            raise FileNotFoundError(f"Video directory not found: {video_dir}")
        
        # Find all video files
        video_extensions = ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.webm', '*.m4v']
        video_files = []
        
        for ext in video_extensions:
            video_files.extend(video_dir.glob(ext))
        
        if not video_files:
            print(f"No video files found in {video_dir}")
            return None
        
        # Sort files by name
        video_files.sort()
        
        # Determine output file
        if output_file is None:
            from datetime import datetime
            date_str = datetime.now().strftime("%m_%d_%y")
            output_file = f"videos_{date_str}.csv"
        
        # Ensure video_lists directory exists
        video_lists_dir = Path("./video_lists/")
        video_lists_dir.mkdir(exist_ok=True)
        
        # Write CSV file to video_lists directory
        if not str(output_file).startswith("./video_lists/"):
            output_path = video_lists_dir / output_file
        else:
            output_path = Path(output_file)
        
        # Generate CSV content using new format
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            
            # Write header with new column names (tags column removed since hashtags are parsed from description)
            writer.writerow(['fileName', 'title', 'description', 'privacy', 'publishAt', 'playlist'])
            
            # Write video rows
            for video_file in video_files:
                filename = video_file.name
                title = filename.replace('_', ' ').replace('-', ' ')
                title = title.rsplit('.', 1)[0]  # Remove extension
                title = ' '.join(word.capitalize() for word in title.split())
                
                # Generate default publishAt in human-readable format
                from datetime import datetime, timedelta
                default_time = datetime.now() + timedelta(days=1)
                default_publish_at = f"{default_time.strftime('%m-%d-%y')} {default_time.strftime('%I%p').replace('M', 'M')} PST"
                
                writer.writerow([
                    filename,
                    title,
                    'Add your video description here with #hashtags for auto-tagging.',
                    'private',
                    default_publish_at,
                    'My Shorts Playlist'  # Example playlist name
                ])
        
        print(f"Generated CSV manifest: {output_path}")
        print(f"Found {len(video_files)} video files:")
        for video_file in video_files:
            print(f"  - {video_file.name}")
        
        return str(output_path)
    
    def select_manifest_interactive(self):
        video_lists_dir = Path("./video_lists/")
        
        if not video_lists_dir.exists():
            print("No ./video_lists/ directory found. Run 'python yas.py --generate' first.")
            return None
        
        # Find all .csv and .md files in video_lists directory
        manifest_files = list(video_lists_dir.glob("*.csv")) + list(video_lists_dir.glob("*.md"))
        
        if not manifest_files:
            print("No video list files found in ./video_lists/")
            print("Run 'python yas.py --generate' to create one.")
            return None
        
        # Sort by modification time (newest first)
        manifest_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        print("Available video lists:")
        print()
        
        for i, manifest_file in enumerate(manifest_files, 1):
            # Get file info
            mod_time = manifest_file.stat().st_mtime
            from datetime import datetime
            mod_date = datetime.fromtimestamp(mod_time).strftime("%m/%d/%y %I:%M %p")
            
            # Count videos in manifest
            try:
                videos = self.parse_manifest(str(manifest_file))
                video_count = len(videos)
            except:
                video_count = "?"
            
            print(f"  {i}. {manifest_file.name}")
            print(f"     Modified: {mod_date}")
            print(f"     Videos: {video_count}")
            print()
        
        while True:
            try:
                choice = input(f"Select a video list (1-{len(manifest_files)}) or 'q' to quit: ").strip()
                
                if choice.lower() == 'q':
                    return None
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(manifest_files):
                    selected_file = manifest_files[choice_num - 1]
                    print(f"Selected: {selected_file.name}")
                    return str(selected_file)
                else:
                    print(f"Please enter a number between 1 and {len(manifest_files)}")
                    
            except ValueError:
                print("Please enter a valid number or 'q' to quit")
            except KeyboardInterrupt:
                print("\nCancelled.")
                return None

def main():
    if len(sys.argv) < 2:
        # Interactive mode - prompt user to select video list
        print("YouTube Auto Shorts (YAS) - Interactive Mode")
        print("=" * 45)
        print()
        
        try:
            uploader = YouTubeUploader()
            manifest_path = uploader.select_manifest_interactive()
            
            if manifest_path:
                results = uploader.upload_from_manifest(manifest_path)
                
                if results:
                    print(f"\nBatch upload completed! {len(results)} videos uploaded successfully.")
                else:
                    print("\nBatch upload failed or no videos were uploaded!")
                    sys.exit(1)
            else:
                print("No video list selected. Exiting.")
                sys.exit(0)
                
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        
        return
    
    # Command line mode
    if sys.argv[1] == "--help" or sys.argv[1] == "-h":
        print("Usage:")
        print("  Interactive mode:  python yas.py")
        print("  Single upload:     python yas.py <video_path> <title> [description] [tags]")
        print("  Batch upload:      python yas.py --manifest <manifest_file> [video_directory]")
        print("  Generate manifest: python yas.py --generate [video_directory] [output_file]")
        print("")
        print("Examples:")
        print("  python yas.py")
        print("  python yas.py video.mp4 'My Short Video' 'Description here' 'tag1,tag2,tag3'")
        print("  python yas.py --manifest videos_08_20_25.md")
        print("  python yas.py --manifest ./video_lists/videos_08_20_25.md ./videos/")
        print("  python yas.py --generate")
        print("  python yas.py --generate ./my-videos/ ./video_lists/my_manifest.md")
        sys.exit(0)
    
    try:
        uploader = YouTubeUploader()
        
        if sys.argv[1] == "--generate":
            video_directory = sys.argv[2] if len(sys.argv) > 2 else "./videos/"
            output_file = sys.argv[3] if len(sys.argv) > 3 else None
            
            manifest_path = uploader.generate_manifest(video_directory, output_file)
            
            if manifest_path:
                print(f"\nManifest generation completed!")
                print(f"Edit {manifest_path} to customize titles, descriptions, and tags before uploading.")
            else:
                print("\nManifest generation failed!")
                sys.exit(1)
        
        elif sys.argv[1] == "--manifest":
            if len(sys.argv) < 3:
                print("Error: Manifest file path required")
                sys.exit(1)
            
            manifest_file = sys.argv[2]
            
            # If just filename given, look in ./video_lists/ directory
            if "/" not in manifest_file:
                manifest_path = f"./video_lists/{manifest_file}"
            else:
                manifest_path = manifest_file
            
            video_directory = sys.argv[3] if len(sys.argv) > 3 else None
            
            results = uploader.upload_from_manifest(manifest_path, video_directory)
            
            if results:
                print(f"\nBatch upload completed! {len(results)} videos uploaded successfully.")
            else:
                print("\nBatch upload failed or no videos were uploaded!")
                sys.exit(1)
        
        else:
            if len(sys.argv) < 3:
                print("Error: Both video path and title are required for single upload")
                sys.exit(1)
            
            video_path = sys.argv[1]
            title = sys.argv[2]
            description = sys.argv[3] if len(sys.argv) > 3 else ""
            tags = sys.argv[4].split(',') if len(sys.argv) > 4 and sys.argv[4] else []
            
            result = uploader.upload_short(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags
            )
            
            if result:
                print("\nUpload completed successfully!")
            else:
                print("\nUpload failed!")
                sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()