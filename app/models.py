from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Float, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
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
    target_niche = Column(String, nullable=True) # ej: "Clínicas Dentales", "Estudios Jurídicos"
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
    total_processed = Column(Integer, default=0)
    total_saved = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    total_skipped = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    prospects = relationship("Prospect", back_populates="job")
    job_prospects = relationship("JobProspect", back_populates="job")
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
    raw_location_text = Column(String, nullable=True)
    parsed_location = Column(JSON, nullable=True)
    city = Column(String, nullable=True)
    region = Column(String, nullable=True)
    country = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    validated_location = Column(String, nullable=True)
    location_match_status = Column(String, nullable=True)
    location_confidence = Column(String, nullable=True)
    detected_language = Column(String, nullable=True)
    language_match_status = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    contact_page_url = Column(String, nullable=True)
    form_detected = Column(Boolean, default=False)
    primary_cta = Column(String, nullable=True)
    booking_url = Column(String, nullable=True)
    pricing_page_url = Column(String, nullable=True)
    whatsapp_url = Column(String, nullable=True)
    contact_channels_json = Column(JSON, nullable=True)
    contact_quality_score = Column(Float, nullable=True)
    contact_consistency_status = Column(String, nullable=True)
    primary_email_confidence = Column(String, nullable=True)
    primary_phone_confidence = Column(String, nullable=True)
    primary_contact_source = Column(String, nullable=True)
    company_size_signal = Column(String, nullable=True)
    service_keywords = Column(JSON, nullable=True)
    
    linkedin_url = Column(String, nullable=True)
    instagram_url = Column(String, nullable=True)
    facebook_url = Column(String, nullable=True)
    
    # Datos genéricos pero adaptativos según la profesión/nicho
    inferred_tech_stack = Column(JSON, nullable=True) # ej: ["WordPress", "Shopify", "React"]
    inferred_niche = Column(String, nullable=True)
    generic_attributes = Column(JSON, nullable=True) # Respuestas a las "preguntas genéricas" que varían por rubro
    observed_signals = Column(JSON, nullable=True)
    inferred_opportunities = Column(JSON, nullable=True)
    entity_type_detected = Column(String, nullable=True)
    entity_type_confidence = Column(String, nullable=True)
    entity_type_evidence = Column(JSON, nullable=True)
    is_target_entity = Column(Boolean, nullable=True)
    
    # Señales detectadas de probabilidad de presupuesto o cierre
    hiring_signals = Column(Boolean, default=False) # ¿Tienen una pestaña "Trabaja con nosotros" / "Careers"?
    estimated_revenue_signal = Column(String, nullable=True) # 'low', 'medium', 'high' deducido de su setup
    has_active_ads = Column(Boolean, nullable=True) # Señal premium de que invierten dinero
    
    source = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    score = Column(Float, default=0.0) # rango esperado: 0.0 a 1.0
    confidence_level = Column(String, nullable=True) # low, medium, high
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    job = relationship("ScrapingJob", back_populates="prospects")
    job_results = relationship("JobProspect", back_populates="prospect")
    contacts = relationship("ProspectContact", back_populates="prospect")
    pages = relationship("ProspectPage", back_populates="prospect")
    signals = relationship("ProspectSignal", back_populates="prospect")


class JobProspect(Base):
    __tablename__ = "job_prospects"
    __table_args__ = (
        UniqueConstraint("job_id", "prospect_id", name="uq_job_prospects_job_prospect"),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("scraping_jobs.id"), nullable=False)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=False)
    workspace_id = Column(String, index=True, nullable=True)

    source_url = Column(String, nullable=True)
    source_type = Column(String, nullable=True)
    discovery_method = Column(String, nullable=True)  # search_query, seed_url, manual, enrichment
    search_query_snapshot = Column(Text, nullable=True)
    rank_position = Column(Integer, nullable=True)
    processing_status = Column(String, default="processed")  # pending, processed, skipped, failed
    quality_status = Column(String, nullable=True)
    quality_flags_json = Column(JSON, nullable=True)
    rejection_reason = Column(String, nullable=True)
    acceptance_decision = Column(String, nullable=True)
    contact_consistency_status = Column(String, nullable=True)
    primary_email_confidence = Column(String, nullable=True)
    primary_phone_confidence = Column(String, nullable=True)
    primary_contact_source = Column(String, nullable=True)
    discovery_confidence = Column(String, nullable=True)
    entity_type_detected = Column(String, nullable=True)
    entity_type_confidence = Column(String, nullable=True)
    entity_type_evidence = Column(JSON, nullable=True)
    is_target_entity = Column(Boolean, nullable=True)

    match_score = Column(Float, default=0.0)  # rango esperado: 0.0 a 1.0
    confidence_level = Column(String, nullable=True)  # low, medium, high
    fit_summary = Column(Text, nullable=True)
    pain_points_json = Column(JSON, nullable=True)
    outreach_angles_json = Column(JSON, nullable=True)
    observed_signals = Column(JSON, nullable=True)
    inferred_opportunities = Column(JSON, nullable=True)
    evidence_json = Column(JSON, nullable=True)
    raw_extraction_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("ScrapingJob", back_populates="job_prospects")
    prospect = relationship("Prospect", back_populates="job_results")


class ProspectContact(Base):
    __tablename__ = "prospect_contacts"
    __table_args__ = (
        UniqueConstraint("prospect_id", "contact_type", "contact_value", name="uq_prospect_contacts_value"),
    )

    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=False)
    contact_type = Column(String, nullable=False)  # email, phone, form, linkedin, whatsapp, booking, other
    contact_value = Column(String, nullable=False)
    label = Column(String, nullable=True)
    is_primary = Column(Boolean, default=False)
    is_public = Column(Boolean, default=True)
    contact_person_name = Column(String, nullable=True)
    contact_person_role = Column(String, nullable=True)
    confidence = Column(Float, default=1.0)
    source_url = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prospect = relationship("Prospect", back_populates="contacts")


class ProspectPage(Base):
    __tablename__ = "prospect_pages"
    __table_args__ = (
        UniqueConstraint("prospect_id", "url", name="uq_prospect_pages_url"),
    )

    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=False)
    url = Column(String, nullable=False)
    page_type = Column(String, nullable=True)  # home, contact, about, pricing, services, portfolio, careers, blog, other
    http_status = Column(Integer, nullable=True)
    title = Column(String, nullable=True)
    meta_description = Column(Text, nullable=True)
    detected_language = Column(String, nullable=True)
    text_hash = Column(String, nullable=True)
    content_signals_json = Column(JSON, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    last_scraped_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prospect = relationship("Prospect", back_populates="pages")


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
