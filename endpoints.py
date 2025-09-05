from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import *
from database import SessionLocal
from sqlalchemy.orm import Session, joinedload

class TextInput(BaseModel):
    text: str

class Enpoints():
    def __init__(self):
        self.app = FastAPI()
        self.app.add_middleware(CORSMiddleware,  allow_origins=["*"])
        self.routes()

    def get_db(self):
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def routes(self):
        @self.app.get('/')
        def index():
            return {"message":"APIS FUNCIONANDO"}

        
        
        @self.app.get('/locations')
        def send_message():
            db = SessionLocal()
            locations = db.query(Location)\
                    .options(
                        joinedload(Location.municipality),
                        joinedload(Location.ghi_values)
                    ).all()

            result = []

            for loc in locations:
                # Buscar el GHI que corresponde al mes "ANUAL"
                anual_ghi = next(
                    (ghi for ghi in loc.ghi_values if ghi.month.upper() == "ANUAL"), None
                )

                if anual_ghi:
                    result.append({
                        "municipality_name": loc.municipality.name,
                        "latitude": loc.latitude,
                        "longitude": loc.longitude,
                        "valor_anual_kwh": anual_ghi.value_kwh
                    })

            return result