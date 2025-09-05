from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

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

