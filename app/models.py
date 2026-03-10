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
    
    # Contexto de lo que hace el usuario (El Vendedor)
    user_profession = Column(String, nullable=True) # ej: "Editor de Video", "Desarrollador Web"
    user_technologies = Column(JSON, nullable=True) # ej: ["Premiere Pro", "After Effects"]
    user_value_proposition = Column(Text, nullable=True) # ej: "Aumento retención con edición dinámica"
    
    # Factores de cierre del Vendedor (Agregados para mejorar outreach)
    user_past_successes = Column(JSON, nullable=True) # ej: ["Canal X subió 30%", "Ahorro de $10k"]
    user_roi_metrics = Column(JSON, nullable=True) # ej: ["ROI 3x", "Ahorro de 5 horas a la semana"]
    
    # Contexto de a quién busca (El Comprador / Prospecto)
    target_niche = Column(String, nullable=True) # ej: "YouTubers de Finanzas", "Clínicas Dentales"
    target_location = Column(String, nullable=True) # ej: "España", "Remoto"
    target_language = Column(String, nullable=True) # ej: "es", "en"
    target_company_size = Column(String, nullable=True) # ej: "1-10 empleados"
    target_pain_points = Column(JSON, nullable=True) # ej: ["Canal estancado", "Mala iluminación"]
    target_budget_signals = Column(JSON, nullable=True) # ej: ["Buscan contratar", "Tienen anuncios activos"]
    
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
    
    # Datos genéricos pero adaptativos según la profesión/nicho
    inferred_tech_stack = Column(JSON, nullable=True) # ej: ["WordPress", "Shopify", "React"]
    inferred_niche = Column(String, nullable=True)
    generic_attributes = Column(JSON, nullable=True) # Respuestas a las "preguntas genéricas" que varían por rubro
    
    # Señales detectadas de probabilidad de presupuesto o cierre
    hiring_signals = Column(Boolean, default=False) # ¿Tienen una pestaña "Trabaja con nosotros" / "Careers"?
    estimated_revenue_signal = Column(String, nullable=True) # 'low', 'medium', 'high' deducido de su setup
    has_active_ads = Column(Boolean, nullable=True) # Señal premium de que invierten dinero
    
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
