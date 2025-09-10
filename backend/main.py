# backend/main.py
import os
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment or .env")

# Initialize OpenAI client (modern client)
client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="Smart Crop Advisory - Backend (FastAPI)")

# CORS - allow your local frontend origins (Vite default 5173 or CRA 3000)
allowed = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
origins = [o.strip() for o in allowed.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AdviceRequest(BaseModel):
    text: str
    lang: str = "hi"    # "hi" for Hindi, "en" for English
    lat: float | None = None
    lon: float | None = None
    crop: str | None = None

@app.post("/api/advice")
async def get_advice(req: AdviceRequest):
    """
    Sends the farmer query plus simple context to an OpenAI chat model and returns advice.
    """
    system_prompt = (
        "You are an empathetic, practical agricultural advisor for small Indian farmers. "
        "Keep answers short, actionable, step-by-step (max ~6 steps). "
        "Use simple words and include one immediate action the farmer can take today. "
        "If language is Hindi (lang='hi'), reply in simple Hindi; if 'en', reply in English."
    )

    user_content = f"Location: lat={req.lat}, lon={req.lon}. Crop={req.crop}. Query: {req.text}"

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # change model if you prefer
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            max_tokens=450,
            temperature=0.2,
        )
        # extract text (support both attribute and dict access)
        try:
            advice = resp.choices[0].message.content
        except Exception:
            advice = resp["choices"][0]["message"]["content"]
        return {"advice": advice}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Accepts an audio file upload and returns the transcription (Whisper).
    """
    try:
        suffix = os.path.splitext(file.filename)[1] or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        # Open file and call OpenAI Whisper transcription
        with open(tmp_path, "rb") as audio_file:
            resp = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-1",
            )

        # resp may provide text as resp.text or resp['text']
        try:
            text = resp.text
        except Exception:
            text = resp.get("text") if isinstance(resp, dict) else None

        # ensure we remove temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        if not text:
            raise HTTPException(status_code=500, detail="Transcription returned empty result")
        return {"text": text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription error: {e}")
