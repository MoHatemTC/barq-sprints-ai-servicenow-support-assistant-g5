from fastapi import FastAPI
from Routes import webhook
app = FastAPI(
    title="AI ServiceNow Support Assistant API",
    version="1.0.0",
    description="Backend service for processing ServiceNow incident webhooks and running AI retrieval workflows."
)

# Connect router to the main app
app.include_router(webhook.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "fastapi-backend"}