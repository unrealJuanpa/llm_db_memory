import sqlite3
import datetime
from typing import List, Optional, Tuple

class CompositeAgent:
    def __init__(self, agent_name: str, n_top_results: int = 5):
        """
        Inicializa el CompositeAgent y configura la conexión a la base de datos.

        Args:
            agent_name (str): El nombre del agente, usado para nombrar el archivo de la base de datos.
            n_top_results (int): El número de elementos principales a retornar
                                 cuando se buscan contenidos por etiquetas.
        """
        self.agent_name = agent_name
        self.db_name = f"{agent_name}_db.sqlite"
        self.n_top_results = n_top_results
        self._check_and_create_schema()

    def _get_db_connection(self):
        """Retorna una conexión a la base de datos."""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row # Permite acceder a las columnas por nombre
        return conn

    def _check_and_create_schema(self):
        """
        Verifica si el esquema de la base de datos está presente y lo crea si no lo está.
        El esquema incluye las tablas 'tags', 'content', y 'content_tags'.
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        # Crear tabla 'tags'
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_text TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Crear tabla 'content'
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_text TEXT NOT NULL,
                points INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Crear tabla 'content_tags' (tabla de unión para la relación muchos a muchos)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content_tags (
                content_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (content_id, tag_id),
                FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        print(f"Esquema de '{self.db_name}' verificado/creado exitosamente.")

    def save_content_with_tags(self, text: str, tags: List[str]):
        """
        Guarda un texto de contenido con una lista de etiquetas en la base de datos.

        Args:
            text (str): El texto del contenido a guardar.
            tags (List[str]): Una lista de etiquetas (strings) asociadas al contenido.
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            # 1. Insertar o recuperar el content_id
            cursor.execute("INSERT INTO content (content_text) VALUES (?)", (text,))
            content_id = cursor.lastrowid

            # 2. Procesar las tags
            for tag_text in tags:
                # Insertar la tag si no existe, o obtener su id si ya existe
                cursor.execute(
                    "INSERT OR IGNORE INTO tags (tag_text) VALUES (?)",
                    (tag_text.lower(),) # Guardar tags en minúsculas para consistencia
                )
                cursor.execute(
                    "SELECT id FROM tags WHERE tag_text = ?",
                    (tag_text.lower(),)
                )
                tag_id = cursor.fetchone()[0]

                # 3. Asociar content_id y tag_id en content_tags
                cursor.execute(
                    "INSERT OR IGNORE INTO content_tags (content_id, tag_id) VALUES (?, ?)",
                    (content_id, tag_id)
                )
            conn.commit()
            print(f"Contenido guardado con ID {content_id} y etiquetas: {', '.join(tags)}")
            return content_id
        except sqlite3.Error as e:
            print(f"Error al guardar contenido y etiquetas: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_related_content_by_tags(self, search_tags: List[str]) -> List[Tuple[int, str, int, List[str]]]:
        """
        Dada una lista de etiquetas de búsqueda, retorna los N elementos de contenido
        que tienen más etiquetas relacionadas, ordenados por la cantidad de coincidencias
        y luego por 'points' (descendente). Incrementa los puntos de los elementos retornados.

        Args:
            search_tags (List[str]): Lista de etiquetas (strings) para buscar contenido relacionado.

        Returns:
            List[Tuple[int, str, int, List[str]]]: Una lista de tuplas, donde cada tupla contiene:
            (content_id, content_text, points, [lista de tags asociadas])
        """
        if not search_tags:
            return []

        conn = self._get_db_connection()
        cursor = conn.cursor()

        # Convertir etiquetas de búsqueda a minúsculas para coincidir con la base de datos
        lower_search_tags = [tag.lower() for tag in search_tags]
        tag_placeholders = ','.join('?' * len(lower_search_tags))

        try:
            # Consulta para encontrar contenido relacionado y contar coincidencias de tags
            query = f"""
                SELECT
                    c.id,
                    c.content_text,
                    c.points,
                    GROUP_CONCAT(t.tag_text) AS associated_tags,
                    COUNT(DISTINCT ct.tag_id) AS tag_match_count
                FROM
                    content AS c
                JOIN
                    content_tags AS ct ON c.id = ct.content_id
                JOIN
                    tags AS t ON ct.tag_id = t.id
                WHERE
                    t.tag_text IN ({tag_placeholders})
                GROUP BY
                    c.id, c.content_text, c.points
                ORDER BY
                    tag_match_count DESC, c.points DESC, c.created_at DESC
                LIMIT ?
            """
            cursor.execute(query, lower_search_tags + [self.n_top_results])
            results = cursor.fetchall()

            final_results = []
            content_ids_to_update_points = []

            for row in results:
                content_id = row['id']
                content_text = row['content_text']
                points = row['points']
                associated_tags = row['associated_tags'].split(',') if row['associated_tags'] else []

                final_results.append((content_id, content_text, points, associated_tags))
                content_ids_to_update_points.append(content_id)

            # Incrementar los puntos para los contenidos encontrados
            if content_ids_to_update_points:
                update_placeholders = ','.join('?' * len(content_ids_to_update_points))
                cursor.execute(f"""
                    UPDATE content
                    SET points = points + 1
                    WHERE id IN ({update_placeholders})
                """, content_ids_to_update_points)
                conn.commit()
                print(f"Puntos incrementados para contenidos con IDs: {content_ids_to_update_points}")

            return final_results

        except sqlite3.Error as e:
            print(f"Error al buscar contenido relacionado: {e}")
            return []
        finally:
            conn.close()
