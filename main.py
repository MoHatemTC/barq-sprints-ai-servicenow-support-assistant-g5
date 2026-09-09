import uvicorn
from App.app import app

if __name__ == "__main__":
    uvicorn.main("main:app", host="0.0.0.0", port=8000, reload=True)