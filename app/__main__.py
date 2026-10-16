import os
os.environ.setdefault('GRADIO_ANALYTICS_ENABLED','False')
import uvicorn
from app.config import Settings
from app.api import create_app

if __name__ == '__main__':
    settings=Settings()
    uvicorn.run(create_app(settings),host=settings.host,port=settings.port)
