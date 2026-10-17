from fastapi import FastAPI
from app.services.claim_detection_service import ClaimDetectionService
app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/analyze")
async def analyze(Text: str):
    service = ClaimDetectionService
    return { "result" : service.analyze_url(Text) }