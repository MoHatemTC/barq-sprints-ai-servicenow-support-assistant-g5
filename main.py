import uvicorn
from app.core.server import app
import logging
logging.basicConfig(level=logging.INFO)
if __name__ == "__main__":
    uvicorn.main("main:app", host="0.0.0.0", port=8000, reload=True)