from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import *
from database import SessionLocal
from sqlalchemy.orm import Session, joinedload
from main import Gemini

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
        
        @self.app.get('/departments')
        def get_departments():
            db = SessionLocal()
            departments = db.query(Department).all()
            db.close()

            return [dept.name for dept in departments]

        @self.app.get('/municipalities/{municipality_name}/range')
        def get_municipality_range(municipality_name: str, start_month: str, end_month: str):
            db = SessionLocal()

            # Buscar el municipio con sus GHI
            municipality = (
                db.query(Municipality)
                .filter(Municipality.name == municipality_name)
                .options(
                    joinedload(Municipality.locations).joinedload(Location.ghi_values)
                )
                .first()
            )

            if not municipality:
                db.close()
                return {"error": f"No se encontró el municipio {municipality_name}"}

            # Definimos el orden de los meses
            month_order = [
                "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
                "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
            ]

            # Normalizamos entrada a mayúsculas
            start_month = start_month.upper()
            end_month = end_month.upper()

            if start_month not in month_order or end_month not in month_order:
                db.close()
                return {"error": "Mes inicial o final inválido. Usa nombres en español (ej: ENERO, FEBRERO...)"}

            start_idx = month_order.index(start_month)
            end_idx = month_order.index(end_month)

            if start_idx > end_idx:
                db.close()
                return {"error": "El mes inicial no puede ser mayor que el mes final"}

            # Filtrar valores dentro del rango
            values = [
                {"month": ghi.month, "value_kwh": ghi.value_kwh}
                for loc in municipality.locations
                for ghi in loc.ghi_values
                if ghi.month in month_order[start_idx:end_idx+1]
            ]

            db.close()
            return {
                "municipality": municipality.name,
                "range": f"{start_month} - {end_month}",
                "values": values
            }


        @self.app.get('/ia_prediction/{municipality_name}/')
        def ia_data(municipality_name: str, start_month: str, end_month: str):

            db = SessionLocal()

            # Buscar el municipio con sus GHI
            municipality = (
                db.query(Municipality)
                .filter(Municipality.name == municipality_name)
                .options(
                    joinedload(Municipality.locations).joinedload(Location.ghi_values)
                )
                .first()
            )

            if not municipality:
                db.close()
                return {"error": f"No se encontró el municipio {municipality_name}"}

            # Definimos el orden de los meses
            month_order = [
                "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
                "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
            ]

            # Normalizamos entrada a mayúsculas
            start_month = start_month.upper()
            end_month = end_month.upper()

            if start_month not in month_order or end_month not in month_order:
                db.close()
                return {"error": "Mes inicial o final inválido. Usa nombres en español (ej: ENERO, FEBRERO...)"}

            start_idx = month_order.index("ENERO")
            end_idx = month_order.index("DICIEMBRE")

            if start_idx > end_idx:
                db.close()
                return {"error": "El mes inicial no puede ser mayor que el mes final"}

            # Filtrar valores dentro del rango
            values = [
                {"month": ghi.month, "value_kwh": ghi.value_kwh}
                for loc in municipality.locations
                for ghi in loc.ghi_values
                if ghi.month in month_order[start_idx:end_idx+1]
            ]
            data = {
                "municipality": municipality.name,
                "range": f"{"ENERO"} - {"DICIEMBRE"}",
                "values": values,
                "year":"2024"
            }

            gen = Gemini()
            gen.send_message(data, start_month, end_month)
            return {"":""}