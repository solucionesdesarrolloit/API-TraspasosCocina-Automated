import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional, Protocol
from fastapi.middleware.cors import CORSMiddleware
import logging
import pyodbc
import psycopg2
from datetime import datetime


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Interfaces para la conexión a bases de datos
class DatabaseConnector(Protocol):
    def connect(self):
        pass

class SQLServerConnector:
    def __init__(self):
        self.connection_string = f"""
            DRIVER={os.getenv("SQL_SERVER_DRIVER")};
            SERVER={os.getenv("SQL_SERVER_HOST")},1433;
            DATABASE={os.getenv("SQL_SERVER_DB")};
            UID={os.getenv("SQL_SERVER_USER")};
            PWD={os.getenv("SQL_SERVER_PASSWORD")};
            TrustServerCertificate=yes;
        """
    
    def connect(self):
        return pyodbc.connect(self.connection_string)

class PostgreSQLConnector:
    def __init__(self):
        self.connection_string = f"""
            dbname={os.getenv("POSTGRES_DB")}
            user={os.getenv("POSTGRES_USER")}
            password={os.getenv("POSTGRES_PASSWORD")}
            host={os.getenv("POSTGRES_HOST")}
            port={os.getenv("POSTGRES_PORT")}
        """
    
    def connect(self):
        return psycopg2.connect(self.connection_string)

# Instancias de conexiones

load_dotenv(dotenv_path=".env", override=True)

sqlserver_db = SQLServerConnector()
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
    id_colab: int
    id_partida_lista: int
    enviado: bool

# Repositorio para manejar la base de datos
class ItemRepository:
    def __init__(self, sql_connector: DatabaseConnector, pg_connector: DatabaseConnector):
        self.sql_connector = sql_connector
        self.pg_connector = pg_connector


    def update_enviado(self, id_ingrediente: int):
        """Actualiza el campo `enviado` a TRUE en un registro específico"""
        try:
            with self.pg_connector.connect() as conn:
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

    def delete_item(self, id_ingrediente: int):
        """Elimina un registro por `id_ingrediente`"""
        try:
            with self.pg_connector.connect() as conn:
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
        
    def get_chefs(self) -> List[Chef]:
        try:
            with self.pg_connector.connect() as conn:
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
    
    def search_items(self, search_term: str, limit: int) -> List[ItemResponse]:
        try:
            pattern = f"{search_term.lower()}%"
            with self.pg_connector.connect() as conn:
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

    def save_items(self, items: List[Item]):
        try:
            with self.pg_connector.connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT nextval('itemsselected_id_partida_lista_seq')")
                    partida_id = cursor.fetchone()[0]
                    query = """
                        INSERT INTO ItemsSelected (ItemCode, ItemName, UomCode, Quantity, emite, destino, Timestamp, sucursal_destino, chef, id_partida_lista)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    for item in items:
                        cursor.execute(query, (item.iditem, item.itemname, item.um_art, item.cantidad_art, item.emite, item.destino, item.timestamp, item.sucursal_destino, item.chef, partida_id))
                    conn.commit()
            return {"message": "Ítems guardados correctamente."}
        except psycopg2.Error as e:
            logging.error(f"Error al guardar los ítems: {str(e)}")
            raise HTTPException(status_code=500, detail="Error al guardar los ítems")
        
    
    
    def get_registered_today(self) -> List[RegisteredItem]:
        try:
            with self.pg_connector.connect() as conn:
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
                        isel.enviado
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
                        enviado=row[13]
                    
                        )
                        for row in results
                    ]
        except psycopg2.Error as e:
            logging.error(f"Error al obtener registros: {str(e)}")
            raise HTTPException(status_code=500, detail="Error al obtener registros")

repository = ItemRepository(sqlserver_db, postgres_db)



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
