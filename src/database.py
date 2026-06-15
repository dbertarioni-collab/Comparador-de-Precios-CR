# src/database.py
import psycopg2

DB_CONFIG = {
    "dbname": "supermercados_cr",
    "user": "postgres",
    "password": "TuPasswordSeguro",
    "host": "localhost",
    "port": "5432"
}

def guardar_datos_dia(datos_scraped, fecha_hoy):
    """Procesa e inserta los datos extraídos en las 3 tablas relacionales."""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        for item in datos_scraped:
            # 1. Asegurar Categoría
            query_categoria = """
                INSERT INTO categorias (nombre) VALUES (%s) 
                ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
                RETURNING id;
            """
            cursor.execute(query_categoria, (item['categoria'],))
            categoria_id = cursor.fetchone()[0]
            
            # 2. Asegurar Producto
            query_producto = """
                INSERT INTO productos (codigo_barras, nombre, marca, categoria_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (codigo_barras) DO UPDATE 
                SET nombre = EXCLUDED.nombre, categoria_id = EXCLUDED.categoria_id
                RETURNING id;
            """
            cursor.execute(query_producto, (item['codigo_barras'], item['nombre'], item.get('marca', ''), categoria_id))
            producto_id = cursor.fetchone()[0]
            
            # 3. Insertar Precio Diario
            query_precio = """
                INSERT INTO historial_precios (producto_id, supermercado, precio, fecha)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (producto_id, supermercado, fecha) DO NOTHING;
            """
            cursor.execute(query_precio, (producto_id, item['supermercado'], item['precio'], fecha_hoy))
            
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error guardando en Base de Datos: {e}")
        return False
    finally:
        cursor.close()
        conn.close()
