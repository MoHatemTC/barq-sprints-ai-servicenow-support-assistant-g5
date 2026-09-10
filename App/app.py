from fastapi import FastAPI
from Routes import webhook
<<<<<<< HEAD
=======
from dotenv import load_dotenv 
from Routes.kb import router as kb_router

load_dotenv()


>>>>>>> f8b719208b7db80bedaf857e9e2120dd2a160434
app = FastAPI(
    title="AI ServiceNow Support Assistant API",
    version="1.0.0",
    description="Backend service for processing ServiceNow incident webhooks and running AI retrieval workflows."
)

# Connect router to the main app
app.include_router(webhook.router)
<<<<<<< HEAD
=======
app.include_router(kb_router)
>>>>>>> f8b719208b7db80bedaf857e9e2120dd2a160434

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "fastapi-backend"}