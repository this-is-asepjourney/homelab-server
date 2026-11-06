from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from .database import Base

class Device(Base):
    __tablename__ = "devices"

    mac_address = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    mcid = Column(String, index=True, nullable=True)          # Machine ID — kunci mapping MAC ↔ MCID
    category = Column(String, index=True, default="Heatpress", nullable=True)  # Hirarki Kategori utama: Heatpress
    device_type = Column(String, nullable=True)               # ESP32, MC, dsb
    model = Column(String, index=True, nullable=True)         # Model: HPM 55, AF-450, APM-LOGO, comingsoon
    location = Column(String, index=True, nullable=True)
    description = Column(String, nullable=True)               # Catatan tambahan
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

