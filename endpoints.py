from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from database import SessionLocal
from main import Gemini  # Asumimos que está bien definido
from models import Department, Municipality, Location, LocationGHI
import json

class TextInput(BaseModel):
    text: str


class Enpoints:
    def __init__(self):
        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.gemini = Gemini()  # Inicializar una sola vez
        self.routes()

    def get_db(self) -> Session:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def routes(self):
        @self.app.get("/")
        def index():
            return {"message": "APIS FUNCIONANDO"}

        # === /locations - Promedio anual calculado (sin depender de "ANUAL") ===
        @self.app.get("/locations")
        def send_message(year: int = Query(..., description="Año para filtrar los valores GHI.")):
            db = next(self.get_db())

            locations = (
                db.query(Location)
                .options(
                    joinedload(Location.municipality),
                    joinedload(Location.ghi_values)
                )
                .all()
            )

            result = []
            for loc in locations:
                # Obtener todos los valores mensuales del año (excluyendo "ANUAL" si existe)
                monthly_values = [
                    ghi.value_kwh for ghi in loc.ghi_values
                    if ghi.year == year and ghi.month.upper() != "ANUAL"
                ]

                if not monthly_values:
                    continue

                avg_kwh = sum(monthly_values) / len(monthly_values)

                result.append({
                    "municipality_name": loc.municipality.name,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "valor_anual_kwh": round(avg_kwh, 2),
                    "year": year
                })

            if not result:
                raise HTTPException(status_code=404, detail=f"No se encontraron datos para el año {year}")

            return result

        # === /departments/{name} - Estadísticas por departamento ===
        @self.app.get("/departments/{department_name}")
        def get_department_stats(
            department_name: str,
            year: int = Query(..., description="Año para filtrar los valores GHI.")
        ):
            db = next(self.get_db())

            municipalities = (
                db.query(Municipality)
                .join(Department)
                .filter(Department.name == department_name)
                .options(
                    joinedload(Municipality.locations)
                    .joinedload(Location.ghi_values)
                )
                .all()
            )

            if not municipalities:
                raise HTTPException(status_code=404, detail=f"Departamento '{department_name}' no encontrado")

            result = []
            for mun in municipalities:
                # Obtener todos los valores GHI del municipio (de todas sus ubicaciones)
                all_values = []
                for loc in mun.locations:
                    monthly_vals = [
                        ghi.value_kwh for ghi in loc.ghi_values
                        if ghi.year == year and ghi.month.upper() != "ANUAL"
                    ]
                    if monthly_vals:
                        # Promediar por ubicación
                        all_values.append(sum(monthly_vals) / len(monthly_vals))

                if not all_values:
                    continue

                max_val = max(all_values)
                min_val = min(all_values)
                mean_val = sum(all_values) / len(all_values)

                # Encontrar el mes más cercano al promedio (usando la primera ubicación)
                closest_ghi = None
                closest_loc = None
                for loc in mun.locations:
                    for ghi in loc.ghi_values:
                        if ghi.year == year and ghi.month.upper() != "ANUAL":
                            if closest_ghi is None or abs(ghi.value_kwh - mean_val) < abs(closest_ghi.value_kwh - mean_val):
                                closest_ghi = ghi
                                closest_loc = loc

                result.append({
                    "municipio": mun.name,
                    "max": {"value_kwh": round(max_val, 2)},
                    "min": {"value_kwh": round(min_val, 2)},
                    "mean": {
                        "month": closest_ghi.month if closest_ghi else "N/A",
                        "value_kwh": round(mean_val, 2)
                    }
                })

            if not result:
                raise HTTPException(status_code=404, detail=f"No hay datos GHI para el año {year}")

            return {
                "department": department_name,
                "year": year,
                "municipalities": result
            }

        # === /departments - Lista de todos los departamentos ===
        @self.app.get("/departments")
        def get_departments():
            db = next(self.get_db())
            departments = db.query(Department).all()
            return [dept.name for dept in departments]

        # === /municipalities/{name}/range - Valores en un rango de meses ===
        @self.app.get("/municipalities/{municipality_name}/range")
        def get_municipality_range(
            municipality_name: str,
            start_month: str,
            end_month: str,
            year: int = Query(..., description="Año para filtrar los valores GHI.")
        ):
            db = next(self.get_db())

            municipality = (
                db.query(Municipality)
                .filter(Municipality.name == municipality_name)
                .options(
                    joinedload(Municipality.locations)
                    .joinedload(Location.ghi_values)
                )
                .first()
            )

            if not municipality:
                raise HTTPException(status_code=404, detail=f"Municipio '{municipality_name}' no encontrado")

            month_order = [
                "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
                "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
            ]

            start_upper = start_month.upper()
            end_upper = end_month.upper()

            if start_upper not in month_order or end_upper not in month_order:
                raise HTTPException(status_code=400, detail="Mes inválido. Usa: ENERO, FEBRERO...")

            start_idx = month_order.index(start_upper)
            end_idx = month_order.index(end_upper)

            if start_idx > end_idx:
                raise HTTPException(status_code=400, detail="El mes inicial no puede ser mayor que el final")

            # Filtrar valores en el rango de meses y año
            values = []
            for loc in municipality.locations:
                for ghi in loc.ghi_values:
                    if ghi.year == year and ghi.month in month_order[start_idx:end_idx + 1]:
                        values.append({"month": ghi.month, "value_kwh": ghi.value_kwh})

            if not values:
                raise HTTPException(
                    status_code=404,
                    detail=f"No hay datos para {start_month}-{end_month} en el año {year}"
                )

            return {
                "municipality": municipality.name,
                "range": f"{start_month} - {end_month}",
                "year": year,
                "values": values
            }

        # === /ia_prediction/{name} - Predicción con IA (Gemini) ===
        @self.app.get("/ia_prediction/{municipality_name}/")
        def ia_data(
            municipality_name: str,
            start_month: str,
            end_month: str,
            year: int = Query(..., description="Año que se desea predecir (ej: 2025)")
        ):
            db = next(self.get_db())

            # === 1. Buscar el municipio con TODOS sus datos ===
            municipality = (
                db.query(Municipality)
                .filter(Municipality.name == municipality_name)
                .options(
                    joinedload(Municipality.locations)
                    .joinedload(Location.ghi_values)
                )
                .first()
            )

            if not municipality:
                raise HTTPException(
                    status_code=404,
                    detail=f"Municipio '{municipality_name}' no encontrado"
                )

            # === 2. Validar meses ===
            month_order = [
                "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
                "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
            ]

            start_upper = start_month.upper()
            end_upper = end_month.upper()

            if start_upper not in month_order or end_upper not in month_order:
                raise HTTPException(
                    status_code=400,
                    detail="Mes inválido. Usa: ENERO, FEBRERO, ..., DICIEMBRE"
                )

            # === 3. Años históricos disponibles en la BD ===
            historical_years = [2019, 2020, 2021, 2022, 2023]

            # === 4. Recolectar TODOS los valores mensuales (todos los meses, todos los años) ===
            from collections import defaultdict
            monthly_data = defaultdict(list)  # (mes, año) → [valores de todas las ubicaciones]

            for loc in municipality.locations:
                for ghi in loc.ghi_values:
                    if ghi.year in historical_years and ghi.month.upper() != "ANUAL":
                        monthly_data[(ghi.month, ghi.year)].append(ghi.value_kwh)

            # Calcular promedio por mes/año (por si hay múltiples ubicaciones)
            all_historical_values = []
            for (month, year_val), values in monthly_data.items():
                avg_kwh = sum(values) / len(values)
                all_historical_values.append({
                    "month": month,
                    "year": year_val,
                    "value_kwh": round(avg_kwh, 2)
                })

            if not all_historical_values:
                raise HTTPException(
                    status_code=404,
                    detail="No hay datos históricos (2019-2024) para este municipio"
                )

            # === 5. Ordenar cronológicamente ===
            all_historical_values.sort(key=lambda x: (x["year"], month_order.index(x["month"])))

            # === 6. Enviar TODO el historial a la IA + meta de predicción ===
            data = {
                "municipality": municipality.name,
                "target_prediction": {
                    "year": year,
                    "start_month": start_upper,
                    "end_month": end_upper,
                    "range": f"{start_upper} - {end_upper}"
                },
                "historical_data": all_historical_values  # ✅ Todos los meses y años completos
            }

            # === 7. Llamar a Gemini con todo el contexto ===
            try:
                prediction = self.gemini.send_message(anio=year, endmonth=end_month, startmonth=start_month, data=data)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error en IA: {str(e)}")
            finally:
                db.close()
                print(f'"""{prediction.replace("json", " ").replace("```", " ").replace("```", " ")}"""')
            return json.loads(f'{prediction.replace("json", " ").replace("```", " ").replace("```", " ")}')
        

        @self.app.get("/municipios/{departamento}")
        def get_municipios(departamento: str):
            db = next(self.get_db())
            # Buscar el departamento (case insensitive)
            dept = db.query(Department).filter(Department.name.ilike(departamento)).first()
            
            if not dept:
                raise HTTPException(status_code=404, detail=f"El departamento '{departamento}' no existe")

            municipios = db.query(Municipality).filter(Municipality.department_id == dept.id).all()

            return {
                "departamento": dept.name,
                "municipios": [m.name for m in municipios]
            }