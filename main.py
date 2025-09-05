import os
import requests
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Department, Municipality, Location, LocationGHI

# ======================
# Configuración BD
# ======================

MESES_ES = {
    "JAN": "ENERO",
    "FEB": "FEBRERO",
    "MAR": "MARZO",
    "APR": "ABRIL",
    "MAY": "MAYO",
    "JUN": "JUNIO",
    "JUL": "JULIO",
    "AUG": "AGOSTO",
    "SEP": "SEPTIEMBRE",
    "OCT": "OCTUBRE",
    "NOV": "NOVIEMBRE",
    "DEC": "DICIEMBRE",
    "ANN": "ANUAL"
}

engine = create_engine("sqlite:///ghi.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# ======================
# Función para obtener GHI desde NASA POWER
# ======================
def get_ghi(lat, lon):
    url = (
        f"https://power.larc.nasa.gov/api/temporal/climatology/point"
        f"?parameters=ALLSKY_SFC_SW_DWN"
        f"&community=RE"
        f"&longitude={lon}&latitude={lat}"
        f"&start=2023&end=2024&format=JSON"
    )
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"❌ Error con NASA API ({lat},{lon}): {resp.text}")
        return None
    
    data = resp.json()
    ghi_values = data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
    return ghi_values  # dict con JAN, FEB... DEC, ANN

# ======================
# Cargar Excel/CSV y procesar
# ======================
def process_file(file_path):
    df = pd.read_csv(file_path) if file_path.endswith(".csv") else pd.read_excel(file_path)
    df_filtrado = df[["Municipio", "Departamento", "Latitud", "Longitud"]].drop_duplicates()

    for _, row in df_filtrado.iterrows():
        dep_name = row["Departamento"]
        mun_name = row["Municipio"]
        lat = float(row["Latitud"])
        lon = float(row["Longitud"])

        # Insertar o buscar departamento
        department = session.query(Department).filter_by(name=dep_name).first()
        if not department:
            department = Department(name=dep_name)
            session.add(department)
            session.commit()

        # Insertar o buscar municipio
        municipality = session.query(Municipality).filter_by(name=mun_name, department=department).first()
        if not municipality:
            municipality = Municipality(name=mun_name, department=department)
            session.add(municipality)
            session.commit()

        # Insertar ubicación
        location = session.query(Location).filter_by(latitude=lat, longitude=lon, municipality=municipality).first()
        if not location:
            location = Location(latitude=lat, longitude=lon, municipality=municipality)
            session.add(location)
            session.commit()

        # Consultar NASA API
        ghi_data = get_ghi(lat, lon)
        if not ghi_data:
            continue

        # Guardar en LocationGHI
# Guardar en LocationGHI
        for month, val in ghi_data.items():
            mes_es = MESES_ES.get(month, month)  # traducir a español
            # evitar duplicados con el mes traducido
            exists = session.query(LocationGHI).filter_by(location=location, month=mes_es).first()
            if not exists:
                ghi_entry = LocationGHI(
                    location=location,
                    month=mes_es,              # guardamos en español
                    value_mj=val,
                    value_kwh=round(val / 3.6, 2)  # conversión MJ → kWh
                )
                session.add(ghi_entry)


        session.commit()
        print(f"✅ Guardado {mun_name} ({dep_name}) con GHI")


if __name__ == "__main__":
    process_file("file.csv")  
