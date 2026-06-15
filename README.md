# Comparador de Precios Supermercados - Costa Rica

Prototipo de aplicación analítica utilizando **Streamlit** y **PostgreSQL** para rastrear, almacenar y comparar el historial diario de precios de productos comerciales en Costa Rica.

## 🚀 Arquitectura
- **Backend (Scrapers):** Ubicados en `scripts/`, diseñados para automatizarse diariamente.
- **Base de Datos:** PostgreSQL con estructura relacional de 3 tablas (`categorias`, `productos`, `historial_precios`).
- **Frontend:** Interfaz web interactiva construida 100% en Python con Streamlit.

## 🛠️ Instalación y Uso Local

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/tu-usuario/comparador-precios-cr.git](https://github.com/tu-usuario/comparador-precios-cr.git)
   cd comparador-precios-cr
