import sqlite3
from datetime import datetime # Se mantiene porque LLMAgent usa datetime para su timestamp de impresión
from typing import List, Optional, Tuple
from llm_agent import LLMAgent # Asumo que llm_agent.py está en el mismo directorio

class CompositeAgent:
    def __init__(
            self,
            agent_name: str,
            server_ip: str,
            expert_model: str = "deepseek-r1:latest",
            tagger_model: str = "deepseek-r1:latest",
            interpreter_model: str = "deepseek-r1:latest",
            system_prompt: str = "You are a helpful assistant",
            max_context_tags: int = 12,
            short_term_memory_items: int = 8,
            long_term_top_results: int = 8
        ):
        self.agent_name = agent_name
        self.db_name = f"{agent_name}_db.sqlite"
        self.n_top_results = long_term_top_results

        print('[DB LOG] Checking DB schema...')
        self._check_and_create_schema()

        self.expert_agent = LLMAgent(server_ip=server_ip, model=expert_model, system_prompt=system_prompt, max_interactions=short_term_memory_items)
        self.tagger_agent = LLMAgent(server_ip=server_ip, model=tagger_model, system_prompt=f'You are an AI agent that extracts keywords representing the provided text and combines them with the provided keywords to produce a single list of maximum {max_context_tags} keywords representing both sets. If there are more keywords, prioritize or join the concepts of the most important ones to meet the planned amount.. The resulting keywords are returned separated by "," as plain text, not JSON, not XML.', max_interactions=1)
        # self.interpreter_agent = LLMAgent(server_ip=server_ip, model=interpreter_model, system_prompt="You are an AI agent that aims to take the information presented by the user and give a short but concise, integrated and clear synthesis of the given information.", max_interactions=1)
        self.context_tags = []


    def _get_db_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn

    def _check_and_create_schema(self):
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_text TEXT UNIQUE NOT NULL,
                    timestamp_created TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_text TEXT NOT NULL,
                    points INTEGER DEFAULT 0,
                    timestamp_created TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content_tags (
                    content_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    PRIMARY KEY (content_id, tag_id),
                    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                )
            """)
            
            # Agregar columnas timestamp si no existen (para bases de datos existentes)
            try:
                cursor.execute("ALTER TABLE tags ADD COLUMN timestamp_created TEXT DEFAULT (datetime('now'))")
            except sqlite3.OperationalError:
                pass  # La columna ya existe
                
            try:
                cursor.execute("ALTER TABLE content ADD COLUMN timestamp_created TEXT DEFAULT (datetime('now'))")
            except sqlite3.OperationalError:
                pass  # La columna ya existe
            
            conn.commit()
            print(f"[DB LOG] Schema for '{self.db_name}' checked/created successfully.")
        except sqlite3.OperationalError as e:
            print(f"[DB ERROR] Error creating database schema: {e}")
            conn.rollback()
        finally:
            conn.close()

    def save_content_with_tags(self, text: str, tags: List[str]):
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            current_timestamp = datetime.now().isoformat()
            
            # Insertar contenido con timestamp
            cursor.execute(
                "INSERT INTO content (content_text, timestamp_created) VALUES (?, ?)", 
                (text, current_timestamp)
            )
            content_id = cursor.lastrowid

            for tag_text in tags:
                # Insertar tag con timestamp si no existe
                cursor.execute(
                    "INSERT OR IGNORE INTO tags (tag_text, timestamp_created) VALUES (?, ?)",
                    (tag_text.lower(), current_timestamp)
                )
                cursor.execute(
                    "SELECT id FROM tags WHERE tag_text = ?",
                    (tag_text.lower(),)
                )
                tag_id = cursor.fetchone()[0]

                cursor.execute(
                    "INSERT OR IGNORE INTO content_tags (content_id, tag_id) VALUES (?, ?)",
                    (content_id, tag_id)
                )
            conn.commit()
            print(f"[DB LOG] Content saved with ID {content_id} and tags: {', '.join(tags)} at {current_timestamp}")
            return content_id
        except sqlite3.Error as e:
            print(f"[DB ERROR] Error saving content and tags: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_related_content_by_tags(self, search_tags: List[str]) -> List[Tuple[int, str, int, List[str], str]]:
        """
        Retorna una lista de tuplas con:
        (content_id, content_text, points, associated_tags, timestamp_created)
        """
        if not search_tags:
            return []

        conn = self._get_db_connection()
        cursor = conn.cursor()

        lower_search_tags = [tag.lower() for tag in search_tags]
        tag_placeholders = ','.join('?' * len(lower_search_tags))

        try:
            query = f"""
                SELECT
                    c.id,
                    c.content_text,
                    c.points,
                    c.timestamp_created,
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
                    c.id, c.content_text, c.points, c.timestamp_created
                ORDER BY
                    tag_match_count DESC, c.points DESC, c.timestamp_created ASC
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
                timestamp_created = row['timestamp_created']
                associated_tags = row['associated_tags'].split(',') if row['associated_tags'] else []

                final_results.append((content_id, content_text, points, associated_tags, timestamp_created))
                content_ids_to_update_points.append(content_id)

            if content_ids_to_update_points:
                update_placeholders = ','.join('?' * len(content_ids_to_update_points))
                cursor.execute(f"""
                    UPDATE content
                    SET points = points + 1
                    WHERE id IN ({update_placeholders})
                """, content_ids_to_update_points)
                conn.commit()
                # print(f"[DB LOG] Points incremented for content IDs: {content_ids_to_update_points}")

            return final_results

        except sqlite3.Error as e:
            print(f"[DB ERROR] Error searching related content: {e}")
            return []
        finally:
            conn.close()

    def chat(self, prompt):
        # print('[TAGGER AGENT OUTPUT FOR AGENT INPUT]')
        self.context_tags = self.tagger_agent.chat(f"Existing keywords: {','.join(self.context_tags)}\n\nText to integrate: {prompt}")
        self.context_tags = self.context_tags.split(',')
        self.context_tags = [t.strip() for t in self.context_tags]
        # print(self.context_tags)
        self.save_content_with_tags(f"user said: {prompt}", ['user'] + self.context_tags)


        # print("[QUERYING LONG TERM MEMORY]")
        input_db_context = "\n\n".join([f"Created at: {c[-1]}\nContent: {c[1]}" for c in self.get_related_content_by_tags(self.context_tags)])
        # print(input_db_context)
        # print(input_db_context)

        # print("[EXPERT AGENT OUTPUT]")
        expert_output = self.expert_agent.chat(prompt, temporal_input=f"Current date and time: {datetime.now()}\nCONTEXT FROM LONG TERM MEMORY: {input_db_context}")
        

        # print('[TAGGER AGENT OUTPUT FOR AGENT RESPONSE]')
        self.context_tags = self.tagger_agent.chat(f"Existing keywords: {','.join(self.context_tags)}\n\nText to integrate: {expert_output}")
        self.context_tags = self.context_tags.split(',')
        self.context_tags = [t.strip() for t in self.context_tags]
        # print(self.context_tags)
        self.save_content_with_tags(f"agent said: {expert_output}", ['agent', 'ai'] + self.context_tags)

        return expert_output



        


