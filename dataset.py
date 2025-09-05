import time
import requests
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import sessionmaker, relationship, declarative_base

# === MODELOS DE DATOS ===
Base = declarative_base()

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    municipalities = relationship("Municipality", back_populates="department")

class Municipality(Base):
    __tablename__ = "municipalities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    department = relationship("Department", back_populates="municipalities")
    locations = relationship("Location", back_populates="municipality")

class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    municipality_id = Column(Integer, ForeignKey("municipalities.id"), nullable=False)
    municipality = relationship("Municipality", back_populates="locations")
    ghi_values = relationship("LocationGHI", back_populates="location")
    __table_args__ = (UniqueConstraint('latitude', 'longitude', 'municipality_id', name='uix_lat_lon_mun'),)


class LocationGHI(Base):
    __tablename__ = "location_ghi"
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    month = Column(String, nullable=False)  # ENERO, FEBRERO, etc.
    value_mj = Column(Float, nullable=False)  # en MJ/m²/día
    value_kwh = Column(Float, nullable=False) # en kWh/m²/día
    year = Column(Integer, nullable=False)
    location = relationship("Location", back_populates="ghi_values")
    __table_args__ = (UniqueConstraint('location_id', 'month', 'year', name='uix_location_month_year'),)


# === CONFIGURACIÓN DE LA BASE DE DATOS ===
engine = create_engine("sqlite:///ghi.db")
Base.metadata.create_all(engine) # Crea las tablas si no existen
Session = sessionmaker(bind=engine)

# === MESES EN ESPAÑOL ===
MESES_ES = {
    "01": "ENERO", "02": "FEBRERO", "03": "MARZO", "04": "ABRIL",
    "05": "MAYO", "06": "JUNIO", "07": "JULIO", "08": "AGOSTO",
    "09": "SEPTIEMBRE", "10": "OCTUBRE", "11": "NOVIEMBRE", "12": "DICIEMBRE"
}

# === OBTENER GHI MENSUAL DE NASA POWER ===
# Se consultarán los años 2019 a 2023 (inclusive)
def get_ghi_monthly(lat, lon, start_year=2019, end_year=2023):
    # Redondeamos para que las coordenadas sean más consistentes en la API
    lat = round(lat, 3)
    lon = round(lon, 3)

    # URL de la API de NASA POWER para datos mensuales
    # Utiliza 'start' y 'end' en formato YYYY para obtener todos los meses de esos años
    url = (
        f"https://power.larc.nasa.gov/api/temporal/monthly/point"
        f"?latitude={lat}"
        f"&longitude={lon}"
        f"&start={start_year}"
        f"&end={end_year}"
        f"&community=RE"  # 'SB' para "Surface and Solar"
        f"&parameters=ALLSKY_SFC_SW_DWN" # GHI: Irradiación Solar Horizontal de Cielo Completo en la Superficie
        f"&format=json"
    )

    try:
        print(f"📡 Consultando NASA POWER para Lat: {lat}, Lon: {lon} (Años: {start_year}-{end_year})")
        response = requests.get(url, timeout=30) # Aumentar timeout por si la API tarda

        if response.status_code == 200:
            data = response.json()
            # La clave de los datos GHI es 'allsky_sfc_sw_dwn'
            # y los datos vienen en un diccionario donde la clave es "YYYYMM"
            if "properties" in data and "parameter" in data["properties"] and "ALLSKY_SFC_SW_DWN" in data["properties"]["parameter"]:
                return data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
            else:
                print(f"⚠️ No se encontraron datos GHI en la respuesta de la API para Lat: {lat}, Lon: {lon}")
                return None
        else:
            print(f"❌ Error en la API de NASA POWER ({response.status_code}): {response.text}")
            return None

    except requests.exceptions.Timeout:
        print(f"❌ Timeout al consultar NASA API para Lat: {lat}, Lon: {lon}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión con NASA API para Lat: {lat}, Lon: {lon}: {e}")
        return None
    except Exception as e:
        print(f"❌ Error inesperado al procesar datos de NASA API para Lat: {lat}, Lon: {lon}: {e}")
        return None

# === PROCESAR EL ARCHIVO CSV ===
def process_file(file_path):
    session = Session() # Inicia una sesión por cada ejecución del proceso

    try:
        # Leer CSV (asegurar separador por comas si es un CSV real)
        # Si tu archivo es realmente un Excel, deberías usar pd.read_excel(file_path)
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip()  # Limpiar espacios en nombres de columnas

        # Asegúrate de que los nombres de las columnas coincidan exactamente con tu Excel/CSV
        required_cols = ["Municipio", "Departamento", "Latitud", "Longitud"]
        if not all(col in df.columns for col in required_cols):
            print(f"❌ Error: El archivo debe contener las columnas: {', '.join(required_cols)}")
            return

        # Eliminar filas con valores nulos en las columnas importantes y duplicados
        df = df[required_cols].drop_duplicates().dropna(subset=["Municipio", "Departamento", "Latitud", "Longitud"])
        
        print(f"📦 Procesando {len(df)} entradas de municipios/ubicaciones del archivo '{file_path}'...")

        for idx, row in df.iterrows():
            try:
                dep_name = str(row["Departamento"]).strip()
                mun_name = str(row["Municipio"]).strip()
                lat = float(row["Latitud"])
                lon = float(row["Longitud"])

                # --- Obtener o crear Departamento ---
                department = session.query(Department).filter_by(name=dep_name).first()
                if not department:
                    department = Department(name=dep_name)
                    session.add(department)
                    session.flush() # flush para obtener el ID antes del commit

                # --- Obtener o crear Municipio ---
                municipality = session.query(Municipality).filter_by(
                    name=mun_name, department_id=department.id
                ).first()
                if not municipality:
                    municipality = Municipality(
                        name=mun_name,
                        department_id=department.id
                    )
                    session.add(municipality)
                    session.flush()

                # --- Obtener o crear Ubicación ---
                # Usamos los 3 decimales para la búsqueda de la ubicación
                location = session.query(Location).filter_by(
                    latitude=round(lat, 3), longitude=round(lon, 3), municipality_id=municipality.id
                ).first()
                if not location:
                    location = Location(
                        latitude=round(lat, 3), # Guardar redondeado para consistencia
                        longitude=round(lon, 3), # Guardar redondeado para consistencia
                        municipality_id=municipality.id
                    )
                    session.add(location)
                    session.flush()

                # --- Consultar NASA API para los datos GHI ---
                ghi_data = get_ghi_monthly(lat, lon)
                if not ghi_data:
                    print(f"⚠️ No se pudo obtener GHI para {mun_name} (Lat: {lat}, Lon: {lon}). Saltando...")
                    continue

                # --- Guardar cada mes y año de los datos GHI ---
                for date_key, value_kwh in ghi_data.items():
                    year = int(date_key[:4])
                    month_num = date_key[4:6]
                    month_name = MESES_ES.get(month_num)

                    if month_name is None:
                        print(f"⚠️ Mes desconocido '{month_num}' para la fecha '{date_key}'. Saltando.")
                        continue
                    
                    if value_kwh is None: # La API puede devolver None para algunos meses
                        print(f"⚠️ Valor GHI nulo para {month_name}-{year} en {mun_name}. Saltando.")
                        continue

                    # Verificar si el registro ya existe para evitar duplicados (gracias al UniqueConstraint)
                    exists = session.query(LocationGHI).filter_by(
                        location_id=location.id, month=month_name, year=year
                    ).first()
                    
                    if not exists:
                        # Convertir kWh/m²/día → MJ/m²/día (1 kWh ≈ 3.6 MJ)
                        value_mj = round(value_kwh, 2) 
                        value_kwh_rounded = round(value_kwh / 3.6, 2)

                        ghi_entry = LocationGHI(
                            location_id=location.id,
                            month=month_name,
                            value_mj=value_mj,
                            value_kwh=value_kwh_rounded,
                            year=year
                        )
                        session.add(ghi_entry)
                    # else:
                    #     print(f"Información GHI para {month_name}-{year} en {mun_name} ya existe. Omitiendo.")

                session.commit() # Commit para guardar los cambios de esta ubicación y sus GHI
                print(f"✅ GHI guardado/actualizado para {mun_name}, {dep_name} (Lat: {lat}, Lon: {lon})")

                # ⏸️ Pausa para respetar los límites de la API de NASA POWER
                # La API de NASA tiene un límite de 1000 solicitudes por hora por IP.
                # Una pausa de 1.5 a 2 segundos es buena práctica.
                time.sleep(4)

            except Exception as e:
                session.rollback() # Si hay un error en una fila, revertimos esa transacción
                print(f"❌ Error procesando la fila {idx} ({row.get('Municipio', 'N/A')}, {row.get('Departamento', 'N/A')}): {e}")

    except Exception as e:
        print(f"❌ Error general al procesar el archivo '{file_path}': {e}")
    finally:
        session.close() # Asegurarse de cerrar la sesión al finalizar

    print("🎉 ¡Proceso de extracción y guardado de datos GHI completado!")


# === EJECUCIÓN ===
if __name__ == "__main__":
    # Asegúrate de que 'file.csv' sea el nombre correcto de tu archivo CSV.
    # Si es un Excel, cambia a pd.read_excel y ajusta el nombre del archivo.
    process_file("file.csv")