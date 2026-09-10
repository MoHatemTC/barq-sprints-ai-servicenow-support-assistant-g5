from fastapi import FastAPI
from dotenv import load_dotenv 
from Routes.kb import router as kb_router

load_dotenv()


app = FastAPI(
    title="AI ServiceNow Support Assistant API",
    version="1.0.0",
    description="Backend service for processing ServiceNow incident webhooks and running AI retrieval workflows."
)

app.include_router(kb_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "fastapi-backend"}