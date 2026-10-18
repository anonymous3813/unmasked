from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

from backend.app.services.shop_marks import page_report

app = FastAPI()


class PageNotesRequest(BaseModel):
    url: HttpUrl
    listed_price: str | None = None


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/page-notes")
def page_notes(body: PageNotesRequest):
    """Return the price, policy, and product marks for one product page."""
    return page_report(str(body.url), body.listed_price)


@app.get("/analyze")
async def analyze(Text: str):
    return {"message": "todo"}
