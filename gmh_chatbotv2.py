import sys
import urllib.request
import requests
import boto3
import cloudinary
import cloudinary.uploader
from cloudinary.uploader import upload
from cloudinary.utils import cloudinary_url
from gtts import gTTS
import gradio as gr
import os
import time
import warnings

# Constants
DIRECTORY = ""  # Local directory to store the output video
GMH_FACE_IMAGE = "https://i.imgur.com/7Nnvv7d.png"  # Face image of George Moses Horton
ROLE_SET = "You are George Moses Horton, an African American Poet. Please speak like George Moses Horton."

# API Keys and Credentials (to be filled in)
DID_KEY = ""
ACCESS_KEY = ""  # OpenAI access key
SECRET_KEY = ""  # AWS secret key
OPENAI_API_KEY = ""  # OpenAI API key
CLOUDINARY_CONFIG = {
    "cloud_name": "",
    "api_key": "",
    "api_secret": ""
}

# Configure AWS and Cloudinary
polly = boto3.client('polly', region_name='us-east-1', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
session = boto3.Session(aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
s3 = session.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
cloudinary.config(**CLOUDINARY_CONFIG)

# Set up headers
HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": "Basic " + DID_KEY
}

# Initialize messages for chat
MESSAGES = [{"role": "system", "content": ROLE_SET}]

# Function to open a file and read its contents
def open_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as infile:
        return infile.read()

# Function to upload a file to Cloudinary and return the secure URL
def upload_to_cloudinary(file_path):
    response = cloudinary.uploader.upload(file_path, resource_type="video")
    return response["secure_url"]

# Function to check video status based on talk ID
def check_video_status(video_id, headers):
    get_url = f"https://api.d-id.com/talks/{video_id}"
    
    while True:
        get_response = requests.get(get_url, headers=headers)
        video_status = get_response.json().get("status")

        print(f"Video status: {get_response.json()}")
        if video_status == "done":
            return get_response.json().get("result_url")
        elif video_status == "failed":
            print("Video generation failed.")
            return None
        time.sleep(5)

# Process function for Gradio to handle audio input and generate responses
def decipher(audio):
    global MESSAGES

    # Using OpenAI's speech-to-text model
    audio_file = open(audio, "rb")
    transcript = openai.Audio.transcribe("whisper-1", audio_file)
    MESSAGES.append({"role": "user", "content": transcript["text"]})

    # Let ChatGPT generate a response based on user's input
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=MESSAGES
    )
    
    system_message = response["choices"][0]["message"]["content"]
    MESSAGES.append({"role": "assistant", "content": system_message})

    # Use AWS Polly to convert ChatGPT's response to speech
    voice_stream = polly.synthesize_speech(Text=system_message, VoiceId='Joey', OutputFormat='mp3')
    with open('system_message.mp3', 'wb') as f:
        f.write(voice_stream['AudioStream'].read())

    # Upload the audio file to Cloudinary and get the public URL
    audio_public_url = upload_to_cloudinary('system_message.mp3')

    # D-ID API call to create a video
    url = "https://api.d-id.com/talks"
    payload = {
        "script": {
            "type": "text",
            "provider": {
                "type": "amazon",
                "voice_id": "Joey"
            },
            "input": system_message,
            "audio_url": audio_public_url
        },
        "source_url": GMH_FACE_IMAGE,
        "driver_url": "bank://lively/driver-05",
        "config": {
            "stitch": "true"
        }
    }

    # Create video using D-ID API call
    response = requests.post(url, json=payload, headers=HEADERS)
    video_id = response.json().get("id")

    # Make a GET request to get the video URL
    video_url = check_video_status(video_id, HEADERS)
    if video_url is not None:
        webbrowser.open(video_url)

    chat_transcript = "\n\n".join(f"{message['role']}: {message['content']}" for message in MESSAGES if message['role'] != "system")
    urllib.request.urlretrieve(video_url, 'video_name.mp4')

    return chat_transcript, os.path.join(DIRECTORY, "video_name.mp4")

# Main function to launch the Gradio interface and create a shareable URL
interface = gr.Interface(share=True, fn=decipher, inputs=gr.Audio(source="microphone", type="filepath"), outputs=["text", "playablevideo"])
interface.launch()
