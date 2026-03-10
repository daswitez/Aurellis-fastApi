import os
import json
import logging
from typing import Dict, Any, List
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# DeepSeek es compatible con el SDK de OpenAI. Solo cambiamos la base_url
# y pasamos la API key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# Iniciamos el cliente asíncrono
client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

async def extract_business_entity_ai(
    domain: str, 
    clean_text: str, 
    job_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Usa DeepSeek-Chat (V3) para analizar el texto de la web y devolver un JSON estricto
    con la perfilación del prospecto y un Match Score, optimizando el uso de tokens.
    """
    
    # 1. OPTIMIZACIÓN DE TOKENS (Ahorro agresivo)
    # DeepSeek cobra por token de entrada. Las webs tienen mucha basura.
    # El parser ya limpió el HTML en 'clean_text', pero aún así lo truncaremos
    # a los primeros ~10,000 caracteres (aprox 2500 - 3000 tokens) porque
    # la propuesta de valor de un negocio casi siempre está en el home/arriba.
    max_chars = 10000 
    truncated_text = clean_text[:max_chars] if clean_text else ""
    
    if not truncated_text or len(truncated_text) < 100:
        logger.warning(f"Texto insuficiente para IA en {domain}. Fallback manual.")
        return _empty_ai_response()
        
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY no encontrada. Por favor agrégala al archivo .env")
        return _empty_ai_response("No API Key")

    # 2. CONTEXTO PARA MATCHMAKING
    buyer_persona = f"""
    Profesión: {job_context.get('user_profession', 'No especificado')}
    Tecnologías que manejo: {job_context.get('user_technologies', [])}
    Mi propuesta de valor: {job_context.get('user_value_proposition', '')}
    Nicho objetivo: {job_context.get('target_niche', 'General')}
    Puntos de dolor que curo: {job_context.get('target_pain_points', [])}
    """

    # 3. PROMPT DE SISTEMA ESTRICTO PARA JSON
    sys_prompt = f"""Eres un clasificador B2B experto en Mapeo de Prospectos. 
Evalúa el texto extraído del dominio '{domain}' y compáralo contra mi perfil de ventas:
{buyer_persona}

RESPONDE EXCLUSIVAMENTE CON UN JSON VÁLIDO. No añadas Markdown (`json`), ni saludos ni comentarios.
Debe tener exactamente esta estructura:
{{
  "inferred_niche": "Industria principal deducida del texto (ej. Clínica Dental, Abogados, Logística, Desconocido)",
  "inferred_tech_stack": ["lista", "de", "nombres", "de", "tecnologias", "detectadas", "o", "vacia"],
  "generic_attributes": {{
    "evaluation_method": "DeepSeek API",
    "pain_points_detected": ["Lista de problemas que notaste en su web (ej. 'web lenta', 'no tiene reservas', 'diseño antiguo', 'poco tráfico') que yo podría solucionarle"]
  }},
  "hiring_signals": false, // true si mencionan "trabaja con nosotros", "careers", "vacantes", etc.
  "estimated_revenue_signal": "low", // "low", "medium", "high" basado en lo sofisticado de los servicios o precios que muestran
  "score": 0.00, // Número decimal entre 0.00 y 1.00. (1.00 es el calce perfecto para comprar mis servicios según mi perfil. 0.00 es que no necesitan lo que vendo)
  "confidence_level": 0.00 // De 0.00 a 1.00 qué tan seguro estás de la extracción basada en el texto (ej. 0.90 si la web es muy clara)
}}
"""

    try:
        # Llamada a IA
        # Usamos deepseek-chat por ser ridículamente barato ($0.14 / 1M input tokens) 
        # y suficientemente inteligente para JSON
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"TEXTO EXTRAIDO DE {domain}:\n\n{truncated_text}"}
            ],
            temperature=0.1, # Baja temperatura para JSON predecible
            max_tokens=500,  # Respuesta JSON debe ser corta (menos coste salida)
            response_format={"type": "json_object"} # Fuerza a DeepSeek a escupir JSON puro
        )
        
        raw_output = response.choices[0].message.content
        logger.info(f"Respuesta IA para {domain} completada. Parseando JSON.")
        
        # Intentar parsear
        parsed_data = json.loads(raw_output)
        
        # Validar tipo de score
        score = float(parsed_data.get("score", 0.0))
        confidence = float(parsed_data.get("confidence_level", 0.5))
        
        return {
            "inferred_tech_stack": parsed_data.get("inferred_tech_stack", []),
            "inferred_niche": parsed_data.get("inferred_niche", "Desconocido"),
            "generic_attributes": parsed_data.get("generic_attributes", {"evaluation_method": "DeepSeek API", "pain_points_detected": []}),
            "hiring_signals": bool(parsed_data.get("hiring_signals", False)),
            "estimated_revenue_signal": parsed_data.get("estimated_revenue_signal", "low"),
            "score": score,
            "confidence_level": confidence
        }

    except json.JSONDecodeError as je:
        logger.error(f"DeepSeek no devolvió un JSON válido para {domain}: {str(je)}")
        return _empty_ai_response("JSON Parse Error")
    except Exception as e:
        logger.error(f"Fallo en API de DeepSeek para {domain}: {str(e)}")
        return _empty_ai_response("API Error")


def _empty_ai_response(reason: str = "Fallback") -> Dict[str, Any]:
    return {
        "inferred_tech_stack": [],
        "inferred_niche": "Desconocido",
        "generic_attributes": {"evaluation_method": reason, "pain_points_detected": []},
        "hiring_signals": False,
        "estimated_revenue_signal": "low",
        "score": 0.0,
        "confidence_level": 0.0
    }
