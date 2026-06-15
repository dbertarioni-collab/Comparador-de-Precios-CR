# scripts/run_all.py
import sys
import os
import datetime

# Permitir la importación de módulos desde la carpeta raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.database import guardar_datos_dia

def simular_scraping_walmart():
    """Simula la recolección de datos de Walmart CR."""
    return [
        {"codigo_barras": "7441001305417", "nombre": "Leche Semidescremada Dos Pinos 1L", "categoria": "Lácteos", "marca": "Dos Pinos", "supermercado": "Walmart", "precio": 920.00},
        {"codigo_barras": "7441019124505", "nombre": "Café Rey Tarrazú 500g", "categoria": "Abarrotes", "marca": "Café Rey", "supermercado": "Walmart", "precio": 3450.00},
        {"codigo_barras": "7441001112223", "nombre": "Arroz Tío Pelón 99% 1.8kg", "categoria": "Abarrotes", "marca": "Tío Pelón", "supermercado": "Walmart", "precio": 1620.00}
    ]

def simular_scraping_automercado():
    """Simula la recolección de datos de Auto Mercado."""
    return [
        {"codigo_barras": "7441001305417", "nombre": "Leche Semidescremada Dos Pinos 1L", "categoria": "Lácteos", "marca": "Dos Pinos", "supermercado": "Auto Mercado", "precio": 980.00},
        {"codigo_barras": "7441019124505", "nombre": "Café Rey Tarrazú 500g", "categoria": "Abarrotes", "marca": "Café Rey", "supermercado": "Auto Mercado", "precio": 3890.00},
        {"codigo_barras": "7441001112223", "nombre": "Arroz Tío Pelón 99% 1.8kg", "categoria": "Abarrotes", "marca": "Tío Pelón", "supermercado": "Auto Mercado", "precio": 1750.00}
    ]

if __name__ == "__main__":
    fecha_hoy = datetime.date.today()
    print(f"--- Iniciando recolección del día: {fecha_hoy} ---")
    
    # 1. Correr extracciones
    datos_totales = []
    datos_totales.extend(simular_scraping_walmart())
    datos_totales.extend(simular_scraping_automercado())
    
    # 2. Guardar en Base de Datos
    exito = guardar_datos_dia(datos_totales, fecha_hoy)
    
    if exito:
        print(f"--- Proceso finalizado con éxito para {len(datos_totales)} registros ---")
    else:
        print("--- Ocurrió un error en el proceso diario ---")
