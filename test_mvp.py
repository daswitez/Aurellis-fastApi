import asyncio
import httpx

async def submit_search_job():
    async with httpx.AsyncClient() as client:
        print("1. Creado solicitud al buscador automático: 'Clínicas veterinarias en Lima'")
        payload = {
            "search_query": "clinica veterinaria lima",
            "max_results": 3,
            "user_profession": "Marketing Agency",
            "target_niche": "Veterinaria"
        }
        
        response = await client.post("http://localhost:8000/api/v1/jobs/scrape", json=payload)
        response_data = response.json()
        print("Respuesta del servidor:", response_data)
        
        if response.status_code != 202:
            return
            
        job_id = response_data["job_id"]
        
        # Polling del Estado
        for _ in range(15):  # Esperar hasta 30s
            await asyncio.sleep(2)
            status_res = await client.get(f"http://localhost:8000/api/v1/jobs/{job_id}")
            status_data = status_res.json()
            print(f"Status del Job {job_id}: {status_data['status']}")
            
            if status_data["status"] == "completed":
                # Ver Resultados
                results_res = await client.get(f"http://localhost:8000/api/v1/jobs/{job_id}/results")
                print("\n=== PROSPECTOS ENCONTRADOS Y PARSEADOS ===")
                for prospect in results_res.json():
                    print("-", prospect["company_name"], "|", prospect["domain"], "| Tiene Ads?:", prospect["has_active_ads"])
                break

if __name__ == "__main__":
    asyncio.run(submit_search_job())
