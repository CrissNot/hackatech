from fastapi import FastAPI, Query, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from sqlalchemy.orm import Session, joinedload
from database import SessionLocal
from main import Gemini  # Asumimos que está bien definido
from models import Department, Municipality, Location, LocationGHI
import json


from math import ceil


from typing import List, Dict, Any
import numpy as np

def calculate_metrics(y_true: List[float], y_pred: List[float]) -> Dict[str, float]:
    """
    Calcula métricas de evaluación entre valores reales y predichos.
    """
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100  # en %
    
    # R² opcional
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

    return {
        "MAE": round(mae, 3),
        "RMSE": round(rmse, 3),
        "MAPE (%)": round(mape, 2),
        "R2": round(r2, 3)
    }


def calcular_paneles(lat: float, lon: float, ghi_kwh: float, desired_kwh_day: float):
    """
    Calcula 5 opciones de cantidad de paneles según diferentes eficiencias.
    
    Parámetros:
        lat (float): Latitud (solo referencia, no se usa en cálculo)
        lon (float): Longitud (solo referencia, no se usa en cálculo)
        ghi_kwh (float): Valor GHI en kWh/m²/día
        desired_kwh_day (float): Energía deseada en kWh/día
    
    Retorna:
        dict con 5 opciones de paneles
    """
    performance_ratio = 0.8   # pérdidas del sistema (~20%)
    area_panel = 1.95         # área de un panel típico en m²
    eficiencias = [0.18, 0.19, 0.20, 0.21, 0.22]

    opciones = []

    for eff in eficiencias:
        energia_por_panel = ghi_kwh * area_panel * eff * performance_ratio
        n_paneles = ceil(desired_kwh_day / energia_por_panel)
        energia_total = energia_por_panel * n_paneles

        opciones.append({
            "cantidad_paneles": n_paneles,
            "eficiencia": round(eff * 100, 1),  # en %
            "energia_total_generada_kwh_dia": round(energia_total, 2)
        })

    return {
        "latitud": lat,
        "longitud": lon,
        "energia_deseada_kwh_dia": desired_kwh_day,
        "ghi_usado_kwh_m2_dia": round(ghi_kwh, 3),
        "opciones": opciones
    }



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
                max_ghi = None
                min_ghi = None
                closest_loc = None
                for loc in mun.locations:
                    for ghi in loc.ghi_values:
                        if ghi.year == year and ghi.month.upper() != "ANUAL":
                            # max
                            if max_ghi is None or ghi.value_kwh > max_ghi.value_kwh:
                                max_ghi = ghi
                            # min
                            if min_ghi is None or ghi.value_kwh < min_ghi.value_kwh:
                                min_ghi = ghi
                            # mean (más cercano al promedio)
                            if closest_ghi is None or abs(ghi.value_kwh - mean_val) < abs(closest_ghi.value_kwh - mean_val):
                                closest_ghi = ghi

                result.append({
                    "municipio": mun.name,
                    "max": {
                        "month": max_ghi.month if max_ghi else "N/A",
                        "value_kwh": round(max_val, 2)
                    },
                    "min": {
                        "month": min_ghi.month if min_ghi else "N/A",
                        "value_kwh": round(min_val, 2)
                    },
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
                    if ghi.year == year and ghi.month.upper() in month_order[start_idx:end_idx + 1]:
                        values.append({"month": ghi.month.upper(), "value_kwh": ghi.value_kwh})

            if not values:
                raise HTTPException(
                    status_code=404,
                    detail=f"No hay datos para {start_month}-{end_month} en el año {year}"
                )

            # 🔹 Ordenar por el índice de month_order
            values.sort(key=lambda v: month_order.index(v["month"]))

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
        
        @self.app.get("/panels")
        def get_panels( 
    lat: float = Query(None, description="Latitud (opcional si se da municipio)"),
    lon: float = Query(None, description="Longitud (opcional si se da municipio)"),
    energia_deseada: float = Query(..., description="Energía deseada en kWh/día")):
            db = next(self.get_db())

            url = (
        f"https://power.larc.nasa.gov/api/temporal/monthly/point"
        f"?latitude={lat}"
        f"&longitude={lon}"
        f"&start=2023"
        f"&end=2024"
        f"&community=RE"  # 'SB' para "Surface and Solar"
        f"&parameters=ALLSKY_SFC_SW_DWN" # GHI: Irradiación Solar Horizontal de Cielo Completo en la Superficie
        f"&format=json"
    )
            response = requests.get(url, timeout=30) # Aumentar timeout por si la API tarda

            print(response.json())
            return calcular_paneles(lon=lon, lat=lat, desired_kwh_day=energia_deseada,ghi_kwh=response.json()["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["202413"])


                
        @self.app.post("/evaluate_model")
        def evaluate_model(
            department_name: str = Query(None, description="Filtrar por departamento (opcional)"),
            municipality_name: str = Query(None, description="Filtrar por municipio (opcional)"),
            year: int = Query(..., description="Año a evaluar"),
            predicted_data: list = Body(..., description="Predicciones en formato JSON con mes, año y value_kwh")
        ):
            db = next(self.get_db())

            # Obtener municipios a evaluar
            query = db.query(Municipality).options(
                joinedload(Municipality.locations).joinedload(Location.ghi_values)
            )

            if department_name:
                dept = db.query(Department).filter(Department.name.ilike(department_name)).first()
                if not dept:
                    raise HTTPException(status_code=404, detail=f"Departamento '{department_name}' no encontrado")
                query = query.join(Department).filter(Department.id == dept.id)

            if municipality_name:
                query = query.filter(Municipality.name.ilike(municipality_name))

            municipalities = query.all()

            if not municipalities:
                raise HTTPException(status_code=404, detail="No se encontraron municipios para evaluar")

            month_order = [
                "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
                "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
            ]

            report = []

            # Organizar predicciones por mes
            predicted_map = {item["month"].upper(): item["value_kwh"] for item in predicted_data if item["year"] == year}

            for mun in municipalities:
                print(f"\nEvaluando municipio: {mun.name}")

                # Recolectar datos reales
                real_values = []
                months = []
                for loc in mun.locations:
                    for ghi in loc.ghi_values:
                        if ghi.year == year and ghi.month.upper() in month_order:
                            months.append(ghi.month.upper())
                            real_values.append(ghi.value_kwh)

                if not real_values:
                    print(f"⚠️ Sin datos reales para {year} en {mun.name}")
                    continue

                # Ordenar reales por mes
                months_sorted = sorted(months, key=lambda m: month_order.index(m))
                real_array = [next(ghi.value_kwh for loc in mun.locations for ghi in loc.ghi_values if ghi.year == year and ghi.month.upper() == m) for m in months_sorted]

                # Predichos en el mismo orden
                predicted_array = [predicted_map[m] for m in months_sorted if m in predicted_map]

                if len(predicted_array) != len(real_array):
                    print(f"⚠️ Longitud de predicción no coincide con real en {year} - {mun.name}")
                    continue

                # Calcular métricas
                metrics = calculate_metrics(real_array, predicted_array)

                report.append({
                    "municipio": mun.name,
                    "departamento": mun.department.name,
                    "año_evaluado": year,
                    "meses": months_sorted,
                    "valores_reales": [round(v, 2) for v in real_array],
                    "valores_predichos": [round(v, 2) for v in predicted_array],
                    "metricas": metrics
                })

            if not report:
                raise HTTPException(status_code=404, detail="No se pudo generar reporte de evaluación")

            return {
                "resumen_global": {
                    "total_evaluaciones": len(report),
                    "MAE_promedio": round(np.mean([r["metricas"]["MAE"] for r in report]), 3),
                    "RMSE_promedio": round(np.mean([r["metricas"]["RMSE"] for r in report]), 3),
                    "MAPE_promedio (%)": round(np.mean([r["metricas"]["MAPE (%)"] for r in report]), 2),
                },
                "detalle_por_municipio": report
            }