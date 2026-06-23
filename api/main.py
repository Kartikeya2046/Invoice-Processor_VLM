from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from core.auth import verify_api_key
from api.routes.documents import router as documents_router

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

app.include_router(documents_router, dependencies=[Depends(verify_api_key)])

@app.get("/health")
def health_check():
    return {"status": "ok"}
