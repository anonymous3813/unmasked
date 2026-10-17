from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/analyze")
async def analyze(Text: str):
    return {"message": "todo"}