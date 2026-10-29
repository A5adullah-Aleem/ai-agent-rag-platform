from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.organizations import router as organization_router
from app.api.documents import router as documents_router
from app.api.conversations import router as conversations_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI Knowledge Platform API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://neural-desk-hazel.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(organization_router)
app.include_router(conversations_router)


app.include_router(documents_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }