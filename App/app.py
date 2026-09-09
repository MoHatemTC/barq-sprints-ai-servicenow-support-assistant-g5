from fastapi import FastAPI

app = FastAPI(
    title="AI ServiceNow Support Assistant API",
    version="1.0.0",
    description="Backend service for processing ServiceNow incident webhooks and running AI retrieval workflows."
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "fastapi-backend"}