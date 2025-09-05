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
            db.close()
            return result
        
        @self.app.get('/departments/{department_name}')
        def get_department_stats(department_name: str):
            db = SessionLocal()

            # Traer todos los municipios del departamento con sus ubicaciones y GHI
            municipalities = (
                db.query(Municipality)
                .join(Department)
                .filter(Department.name == department_name)  # ajusta si no guardas en mayúsculas
                .options(
                    joinedload(Municipality.locations).joinedload(Location.ghi_values)
                )
                .all()
            )

            if not municipalities:
                db.close()
                return {"error": f"No se encontraron datos para {department_name}"}

            result = []
            for mun in municipalities:
                # Recolectar todos los valores de GHI de ese municipio (solo meses, no anual)
                values = [
                    ghi for loc in mun.locations for ghi in loc.ghi_values
                    if ghi.month != "ANUAL"
                ]

                if not values:
                    continue

                # Calcular máximo, mínimo y promedio
                max_val = max(values, key=lambda x: x.value_kwh)
                min_val = min(values, key=lambda x: x.value_kwh)
                mean_val = sum(v.value_kwh for v in values) / len(values)

                # Buscar el mes más cercano al promedio
                mean_month, mean_value = min(
                    [(ghi.month, ghi.value_kwh) for ghi in values],
                    key=lambda x: abs(x[1] - mean_val)
                )

                result.append({
                    "municipio": mun.name,
                    "max": {"month": max_val.month, "value_kwh": max_val.value_kwh},
                    "min": {"month": min_val.month, "value_kwh": min_val.value_kwh},
                    "mean": {"month": mean_month, "value_kwh": round(mean_value, 2)}
                })

            db.close()
            return {
                "department": department_name,
                "municipalities": result
            }