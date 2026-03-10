from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Float, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
from app.database import Base

class ScrapingJob(Base):
    __tablename__ = "scraping_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(String, index=True, nullable=True) # null en MVP sin Auth
    requested_by = Column(String, nullable=True)
    status = Column(String, default="pending") # pending, running, completed, failed
    source_type = Column(String, nullable=True)
    filters_json = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    total_found = Column(Integer, default=0)
    total_saved = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    prospects = relationship("Prospect", back_populates="job")
    logs = relationship("ScrapingLog", back_populates="job")


class Prospect(Base):
    __tablename__ = "prospects"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("scraping_jobs.id"), nullable=True)
    workspace_id = Column(String, index=True, nullable=True)
    
    company_name = Column(String, nullable=True)
    domain = Column(String, index=True, unique=True, nullable=False) # clave primaria lógica para deduplicación
    website_url = Column(String, nullable=True)
    category = Column(String, nullable=True)
    location = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    contact_page_url = Column(String, nullable=True)
    form_detected = Column(Boolean, default=False)
    
    linkedin_url = Column(String, nullable=True)
    instagram_url = Column(String, nullable=True)
    facebook_url = Column(String, nullable=True)
    
    source = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    score = Column(Float, default=0.0)
    confidence_level = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    job = relationship("ScrapingJob", back_populates="prospects")
    signals = relationship("ProspectSignal", back_populates="prospect")


class ProspectSignal(Base):
    __tablename__ = "prospect_signals"
    
    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"))
    signal_type = Column(String, nullable=False)
    signal_value = Column(String, nullable=True)
    confidence = Column(Float, default=1.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    prospect = relationship("Prospect", back_populates="signals")


class ScrapingLog(Base):
    __tablename__ = "scraping_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("scraping_jobs.id"))
    level = Column(String, default="INFO")
    message = Column(Text, nullable=False)
    source_name = Column(String, nullable=True)
    context_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    job = relationship("ScrapingJob", back_populates="logs")
