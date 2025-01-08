from fastapi import FastAPI, Request, Form, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template
import uvicorn
import json
import os
from .face_recognition import train_face, recognize_face


from face_recognition import train_face, recognize_face
from blink_detection import detect_blink

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Load user data
USER_DATA_PATH = "backend/user_data.json"
if not os.path.exists(USER_DATA_PATH):
    with open(USER_DATA_PATH, "w") as f:
        json.dump({}, f)

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html") as f:
        template = Template(f.read())
    return template.render()

@app.post("/login/")
async def login(id: str = Form(...)):
    # Implement face recognition for login
    pass

@app.get("/add_user/")
async def add_user():
    with open("templates/add_person.html") as f:
        template = Template(f.read())
    return template.render()

@app.post("/add_user/")
async def save_user(id: str = Form(...), name: str = Form(...), balance: float = Form(...), video: UploadFile = None):
    # Save new user data and train face
    pass
