from sqlalchemy import Column, Integer, String, Float, ForeignKey
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


class LocationGHI(Base):
    __tablename__ = "location_ghi"
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    month = Column(String, nullable=False)  # "JAN", "FEB", ...
    value_mj = Column(Float, nullable=False)  # valor en MJ/m²/día
    value_kwh = Column(Float, nullable=False) # valor en kWh/m²/día

    location = relationship("Location", back_populates="ghi_values")
