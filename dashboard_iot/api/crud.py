from sqlalchemy.orm import Session
from sqlalchemy import or_
from . import models, schemas
from typing import Optional


def get_device(db: Session, mac_address: str):
    return db.query(models.Device).filter(models.Device.mac_address == mac_address).first()


def get_device_by_mcid(db: Session, mcid: str):
    return db.query(models.Device).filter(models.Device.mcid == mcid).first()


def get_devices(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    category: Optional[str] = None,
    model: Optional[str] = None,
):
    """Get all devices with optional full-text search and hierarchy filters (category & model)."""
    query = db.query(models.Device)

    if category:
        query = query.filter(models.Device.category.ilike(category))

    if model:
        # Match either exact or lenient (e.g. HPM-55 or HPM 55)
        clean_model = model.replace("-", " ").strip()
        query = query.filter(
            or_(
                models.Device.model.ilike(f"%{model}%"),
                models.Device.model.ilike(f"%{clean_model}%")
            )
        )

    if search:
        term = f"%{search.lower()}%"
        query = query.filter(
            or_(
                models.Device.name.ilike(term),
                models.Device.mac_address.ilike(term),
                models.Device.mcid.ilike(term),
                models.Device.location.ilike(term),
                models.Device.model.ilike(term),
                models.Device.category.ilike(term),
                models.Device.device_type.ilike(term),
            )
        )

    return query.offset(skip).limit(limit).all()



def get_devices_count(db: Session) -> int:
    return db.query(models.Device).count()


def get_devices_by_mcid_mapped(db: Session) -> int:
    """Count devices yang sudah memiliki MCID (sudah di-mapping ke mesin)."""
    return db.query(models.Device).filter(
        models.Device.mcid.isnot(None),
        models.Device.mcid != ""
    ).count()


def create_device(db: Session, device: schemas.DeviceCreate):
    db_device = models.Device(**device.model_dump())
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device


def update_device(db: Session, mac_address: str, device: schemas.DeviceUpdate):
    db_device = get_device(db, mac_address)
    if db_device:
        update_data = device.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_device, key, value)
        db.commit()
        db.refresh(db_device)
    return db_device


def delete_device(db: Session, mac_address: str):
    db_device = get_device(db, mac_address)
    if db_device:
        db.delete(db_device)
        db.commit()
    return db_device
