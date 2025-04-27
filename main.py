import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional, Protocol
from fastapi.middleware.cors import CORSMiddleware
import logging
import psycopg2
from psycopg2 import pool
from datetime import datetime
from prometheus_fastapi_instrumentator import Instrumentator
import base64
import io
import numpy as np
import face_recognition
from PIL import Image




app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

instrumentator = Instrumentator().instrument(app).expose(app)

# Interfaces para la conexión a bases de datos
class DatabaseConnector(Protocol):
    def connect(self):
        pass


class PostgreSQLConnector:
    def __init__(self):
        self.connection_string = (
            f"dbname={os.getenv('POSTGRES_DB')} "
            f"user={os.getenv('POSTGRES_USER')} "
            f"password={os.getenv('POSTGRES_PASSWORD')} "
            f"host={os.getenv('POSTGRES_HOST')} "
            f"port={os.getenv('POSTGRES_PORT')}"
        )
        self.pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=self.connection_string
        )

    def connect(self):
        return self.pool.getconn()

    def release(self, conn):
        self.pool.putconn(conn)
# Instancias de conexiones

load_dotenv(dotenv_path=".env", override=True)

postgres_db = PostgreSQLConnector()

class Chef(BaseModel):
    id_colab: int
    nombre_chef: str
    contrasena: str
    administrador: bool

# Modelos de datos
class ItemResponse(BaseModel):
    ItemCode: str
    Dealmacen: Optional[str]
    Dscription: str
    UomCode: Optional[str] = None


class Item(BaseModel):
    iditem: str
    itemname: str
    um_art: Optional[str] = "N/A"
    cantidad_art: float
    emite: str
    destino: str
    timestamp: datetime
    sucursal_destino: str
    chef: int
    observaciones: Optional[str]

class RegisteredItem(BaseModel):
    id_ingrediente: int
    ItemCode: str
    ItemName: str
    UomCode: str
    Quantity: float
    emite: str
    destino: str
    fecha: str
    hora: str
    sucursal_destino: str
    nombre_chef: Optional[str]
    id_colab: Optional[int]
    id_partida_lista: int
    enviado: bool
    cantidad_almacen: Optional[float] = None  # Nuevo campo
    acepta_almacen: Optional[str] = None      # Nuevo campo
    observaciones: Optional[str]

class FaceRegisterRequest(BaseModel):
    image_base64: str
    nombre_chef: str
    contrasena: str
    id_colab: int

class FaceLoginRequest(BaseModel):
    image_base64: str


# Repositorio para manejar la base de datos
class ItemRepository:
    def __init__(self, pg_connector: DatabaseConnector):
        self.pg_connector = pg_connector


    def update_enviado(self, id_ingrediente: int):
            
            conn = self.pg_connector.connect()
            try:
                  with conn.cursor() as cursor:
                    query = """
                        UPDATE itemsselected
                        SET enviado = TRUE
                        WHERE id_ingrediente = %s
                    """
                    cursor.execute(query, (id_ingrediente,))
                    conn.commit()

                    if cursor.rowcount == 0:
                        raise HTTPException(status_code=404, detail="Registro no encontrado")

                    return {"message": "Registro marcado como enviado"}
            
            except psycopg2.Error as e:
                logging.error(f"Error al actualizar el campo enviado: {str(e)}")
                raise HTTPException(status_code=500, detail="Error al actualizar el campo enviado")
            finally:
                self.pg_connector.release(conn)

    def delete_item(self, id_ingrediente: int):

        """Elimina un registro por `id_ingrediente`"""
        conn = self.pg_connector.connect()
        try:
            with conn.cursor() as cursor:
                query = "DELETE FROM itemsselected WHERE id_ingrediente = %s"
                cursor.execute(query, (id_ingrediente,))
                conn.commit()

                if cursor.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Registro no encontrado")

                return {"message": "Registro eliminado correctamente"}
        except psycopg2.Error as e:
            logging.error(f"Error al eliminar el registro: {str(e)}")
            raise HTTPException(status_code=500, detail="Error al eliminar el registro")
        finally:
            self.pg_connector.release(conn)
        
    def get_chefs(self) -> List[Chef]:
            conn = self.pg_connector.connect()
            try:
                with conn.cursor() as cursor:
                    query = """
                        SELECT id_colab, nombre_chef, contrasena, administrador
                        FROM chef
                        ORDER BY nombre_chef ASC
                    """
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    chefs = [
                        {
                            "id_colab": row[0],
                            "nombre_chef": row[1],
                            "contrasena": row[2],
                            "administrador":row[3]
                        }
                        for row in rows
                    ]
                    return chefs
            except psycopg2.Error as e:
                logging.error(f"Error al obtener chefs: {str(e)}")
                raise HTTPException(status_code=500, detail="Error al obtener chefs")
            finally:
                self.pg_connector.release(conn)



    
    def search_items(self, search_term: str, limit: int) -> List[ItemResponse]:
            pattern = f"{search_term.lower()}%"
            conn = self.pg_connector.connect()
            try:
                with conn.cursor() as cursor:
                    query = """
                        SELECT "ItemCode", "Dealmacen", "Dscription", "UomCode"
                        FROM productos_sap
                        WHERE LOWER("Dscription") LIKE %s OR LOWER("ItemCode") LIKE %s
                        ORDER BY "Dscription"
                        LIMIT %s
                    """
                    cursor.execute(query, (pattern, pattern, limit))
                    rows = cursor.fetchall()
                    return [
                        ItemResponse(
                            ItemCode=row[0],
                            Dealmacen=row[1],
                            Dscription=row[2],
                            UomCode=row[3]
                        )
                        for row in rows
                    ]
            except psycopg2.Error as e:
                logging.error(f"Error al buscar productos: {str(e)}")
                raise HTTPException(status_code=500, detail="Error en la base de datos")
            finally:
                self.pg_connector.release(conn)

    def save_items(self, items: List[Item]):
            conn = self.pg_connector.connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT nextval('itemsselected_id_partida_lista_seq')")
                    partida_id = cursor.fetchone()[0]
                    query = """
                        INSERT INTO ItemsSelected (ItemCode, ItemName, UomCode, Quantity, emite, destino, Timestamp, sucursal_destino, chef, id_partida_lista, observaciones)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    for item in items:
                        cursor.execute(query, (item.iditem, item.itemname, item.um_art, item.cantidad_art, item.emite, item.destino, item.timestamp, item.sucursal_destino, item.chef, partida_id, item.observaciones))
                    conn.commit()

                return {"message": "Ítems guardados correctamente."}
            except psycopg2.Error as e:
                logging.error(f"Error al guardar los ítems: {str(e)}")
                raise HTTPException(status_code=500, detail="Error al guardar los ítems")
            finally:
                self.pg_connector.release(conn)
    
    
    def get_registered_today(self) -> List[RegisteredItem]:
            conn = self.pg_connector.connect()
            try:
                with conn.cursor() as cursor:
                    query = """
                        SELECT 
                        isel.id_ingrediente,
                        isel.itemCode, 
                        isel.itemName, 
                        isel.uomCode, 
                        isel.quantity, 
                        isel.emite, 
                        isel.destino, 
                        TO_CHAR(isel.Timestamp AT TIME ZONE 'America/Mexico_City', 'YYYY-MM-DD') AS fecha, 
                        TO_CHAR(isel.Timestamp AT TIME ZONE 'America/Mexico_City', 'HH12:MI') AS hora,
                        isel.sucursal_destino,
                        c.nombre_chef,
                        c.id_colab,
                        isel.id_partida_lista,
                        isel.enviado,
                        isel.cantidad_almacen,
                        isel.acepta_almacen,
                        isel.observaciones
                        FROM itemsselected as isel
                        LEFT JOIN chef c ON isel.chef = c.id_colab
                        ORDER BY isel.Timestamp DESC;
                    """
                    cursor.execute(query)
                    results = cursor.fetchall()
                    return [
                        RegisteredItem(id_ingrediente=row[0],
                        ItemCode=row[1],
                        ItemName=row[2],
                        UomCode=row[3],
                        Quantity=row[4],
                        emite=row[5],
                        destino=row[6],
                        fecha=row[7],
                        hora=row[8],
                        sucursal_destino=row[9],
                        nombre_chef=row[10],
                        id_colab=row[11],
                        id_partida_lista=row[12],
                        enviado=row[13],
                        cantidad_almacen=row[14],
                        acepta_almacen=row[15],
                        observaciones=row[16]

                    
                        )
                        for row in results
                    ]
            except psycopg2.Error as e:
                logging.error(f"Error al obtener registros: {str(e)}")
                raise HTTPException(status_code=500, detail="Error al obtener registros, no hay")
            finally:
                self.pg_connector.release(conn)

repository = ItemRepository(postgres_db)



@app.get("/items", response_model=List[ItemResponse])
async def search_items(search_term: Optional[str] = Query(None, min_length=1), limit: int = 20, repo: ItemRepository = Depends(lambda: repository)):
    return repo.search_items(search_term or "", limit)

@app.post("/save_items")
async def save_items(items: List[Item], repo: ItemRepository = Depends(lambda: repository)):
    return repo.save_items(items)

@app.get("/registered_today", response_model=List[RegisteredItem])
async def get_registered_today(repo: ItemRepository = Depends(lambda: repository)):
    return repo.get_registered_today()

@app.get("/chefs", response_model=List[Chef])
async def get_chefs(repo: ItemRepository = Depends(lambda: repository)):
    return repo.get_chefs()

@app.put("/registered_today/{id_ingrediente}/enviado")
async def update_enviado(id_ingrediente: int, repo: ItemRepository = Depends(lambda: repository)):
    """Marca un registro como enviado (enviado = true)"""
    return repo.update_enviado(id_ingrediente)

@app.delete("/registered_today/{id_ingrediente}")
async def delete_item(id_ingrediente: int, repo: ItemRepository = Depends(lambda: repository)):
    """Elimina un registro de la tabla `itemsselected` por `id_ingrediente`"""
    return repo.delete_item(id_ingrediente)

@app.put("/approve_records")
async def approve_records(data: List[dict], repo: ItemRepository = Depends(lambda: repository)):
    """
    Endpoint para aprobar registros.
    Recibe una lista de registros con sus cantidades editadas y marca como aprobados.
    """
    try:
        conn = postgres_db.connect()

        with conn.cursor() as cursor:
            for record in data:
                query = """
                    UPDATE itemsselected
                    SET cantidad_almacen = %s,
                        acepta_almacen = 'aprobado'
                    WHERE id_ingrediente = %s
                """
                cursor.execute(query, (record["cantidad_almacen"], record["id_ingrediente"]))
            conn.commit()
        return {"message": "Registros aprobados correctamente."}
    except psycopg2.Error as e:
        logging.error(f"Error al aprobar registros: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al aprobar registros.")
    finally:
        postgres_db.release(conn)
        

def image_base64_to_embedding(image_base64: str):
    header, encoded = image_base64.split(',', 1)  # separa el 'data:image/png;base64,...'
    image_data = base64.b64decode(encoded)
    image = Image.open(io.BytesIO(image_data)).convert('RGB')  # 👈 asegúrate que sea RGB
    np_image = np.array(image)

    face_encodings = face_recognition.face_encodings(np_image)
    if not face_encodings:
        raise ValueError("No se detectó ningún rostro en la imagen.")
    return face_encodings[0].tolist()

@app.put("/update_observation/{id_ingrediente}")
async def update_observation(id_ingrediente: int, data: dict, repo: ItemRepository = Depends(lambda: repository)):
    """
    Endpoint para actualizar el campo observaciones de un registro específico.
    """
    conn = postgres_db.connect()

    try:            
        with conn.cursor() as cursor:
            query = """
                UPDATE itemsselected
                SET observaciones = %s
                WHERE id_ingrediente = %s
            """
            cursor.execute(query, (data.get("observaciones"), id_ingrediente))
            conn.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Registro no encontrado")
        return {"message": "Observaciones actualizadas correctamente."}

    except psycopg2.Error as e:
        logging.error(f"Error al actualizar observaciones: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al actualizar observaciones.")  
    finally:
        postgres_db.release(conn)  

@app.post("/register_face")
async def register_face(data: FaceRegisterRequest):

    try:
        embedding = image_base64_to_embedding(data.image_base64)
    except Exception as e:
        logging.error(f"Error al convertir imagen a embedding: {str(e)}")
        raise HTTPException(status_code=400, detail="Error al procesar imagen")

    # Guardar en la base de datos (sin hashing)
    conn = postgres_db.connect()
    try:

        with conn.cursor() as cursor:
            query = """
                INSERT INTO chef (id_colab, nombre_chef, contrasena, administrador, embedding)
                VALUES (%s, %s, %s, DEFAULT, %s)
                ON CONFLICT (id_colab) DO UPDATE 
                SET nombre_chef = EXCLUDED.nombre_chef,
                    contrasena = EXCLUDED.contrasena,
                    embedding = EXCLUDED.embedding
            """
            cursor.execute(query, (
                data.id_colab,
                data.nombre_chef,
                data.contrasena,  # Guardar la contraseña sin hashing
                embedding
            ))
            conn.commit()

        return {"status": "success", "message": "Chef registrado con rostro correctamente."}
    except Exception as e:
        logging.error(f"Error al registrar chef: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al registrar chef.")
    finally:
        postgres_db.release(conn)

@app.post("/login_face")
async def login_face(data: FaceLoginRequest):
    try:
        image = image_base64_to_embedding(data.image_base64)
        input_embedding = np.array(image)

        conn = postgres_db.connect()

        with conn.cursor() as cursor:
            cursor.execute("SELECT id_colab, nombre_chef, administrador, embedding FROM chef WHERE embedding IS NOT NULL")
            matches = []
            for id_colab, nombre, admin, embedding_bytes in cursor.fetchall():
                known_embedding = np.array(embedding_bytes, dtype=np.float64)
                distance = np.linalg.norm(input_embedding - known_embedding)
                matches.append((distance, id_colab, nombre, admin))

            matches.sort()
            if matches and matches[0][0] < 0.6:
                return {
                    "id_colab": matches[0][1], 
                    "nombre_chef": matches[0][2],
                    "administrador": matches[0][3]
                }

        raise HTTPException(status_code=404, detail="Rostro no reconocido")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en login facial: {str(e)}")
    finally:
        postgres_db.release(conn)
        
