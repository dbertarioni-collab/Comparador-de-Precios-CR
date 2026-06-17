# 🛒 Precios CR — Streamlit App

Aplicación para extraer, almacenar y consultar precios de supermercados de Costa Rica usando IA.

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
streamlit run app.py
```

Abrí `http://localhost:8501` y pegá tu API Key de Anthropic en el panel izquierdo.

## Estructura

```
precios_cr/
├── app.py              ← App principal
├── requirements.txt    ← Dependencias
└── precios_cr.db       ← SQLite (se crea automáticamente)
```

## Pestañas

| Pestaña | Función |
|---|---|
| 💬 Chat | Chat con streaming, enriquecido con datos de la DB |
| ⬇️ Extraer datos | Extrae productos por supermercado y categoría, guarda en SQLite |
| 🗄️ Base de datos | Explora, filtra, analiza y exporta los datos |

## Supermercados
- Walmart CR · Automercado · PriceSmart · Maxi Palí · Fresh Market

## Categorías
Lácteos · Granos y cereales · Carnes · Frutas y verduras · Bebidas ·
Limpieza · Snacks · Panadería · Congelados · Higiene personal · Aceites y condimentos
