from fastapi import FastAPI, Depends
from core.config import settings
from core.auth import verify_api_key
from api.routes.documents import router as documents_router

app = FastAPI(title=settings.PROJECT_NAME)

app.include_router(documents_router, dependencies=[Depends(verify_api_key)])

@app.get("/health")
def health_check():
    return {"status": "ok"}
