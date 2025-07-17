import sqlite3
import datetime # Se mantiene porque LLMAgent usa datetime para su timestamp de impresión
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
            short_term_items: int = 16,
            long_term_top_results: int = 5
        ):
        self.agent_name = agent_name
        self.db_name = f"{agent_name}_db.sqlite"
        self.n_top_results = long_term_top_results

        print('[DB LOG] Checking DB schema...')
        self._check_and_create_schema()

        self.expert_agent = LLMAgent(server_ip=server_ip, model=expert_model, system_prompt=system_prompt, max_interactions=short_term_items)
        self.tagger_agent = LLMAgent(server_ip=server_ip, model=tagger_model, system_prompt="You are an AI agent that takes the content given by the user and converts it into tags that represent the information presented. Tags are simple strings separated by a comma ','. Tags arent sentences, tags are simple words or composed words. Do not give greetings, explanations or anything else other than the plain text list of tags. Generate a short but expressive set of tags that represent the information. No JSON, no Markdown, no YAML format, just plain text.", max_interactions=1)
        self.interpreter_agent = LLMAgent(server_ip=server_ip, model=interpreter_model, system_prompt="You are an AI agent that aims to take the information presented by the user and give a short but concise, integrated and clear synthesis of the given information.", max_interactions=1)

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
                    tag_text TEXT UNIQUE NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_text TEXT NOT NULL,
                    points INTEGER DEFAULT 0
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
            # No timestamp inserted here anymore
            cursor.execute("INSERT INTO content (content_text) VALUES (?)", (text,))
            content_id = cursor.lastrowid

            for tag_text in tags:
                cursor.execute(
                    "INSERT OR IGNORE INTO tags (tag_text) VALUES (?)",
                    (tag_text.lower(),)
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
            print(f"[DB LOG] Content saved with ID {content_id} and tags: {', '.join(tags)}")
            return content_id
        except sqlite3.Error as e:
            print(f"[DB ERROR] Error saving content and tags: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_related_content_by_tags(self, search_tags: List[str]) -> List[Tuple[int, str, int, List[str]]]:
        if not search_tags:
            return []

        conn = self._get_db_connection()
        cursor = conn.cursor()

        lower_search_tags = [tag.lower() for tag in search_tags]
        tag_placeholders = ','.join('?' * len(lower_search_tags))

        try:
            # Removed `c.timestamp_created DESC` from ORDER BY
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
                    tag_match_count DESC, c.points DESC
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

            if content_ids_to_update_points:
                update_placeholders = ','.join('?' * len(content_ids_to_update_points))
                cursor.execute(f"""
                    UPDATE content
                    SET points = points + 1
                    WHERE id IN ({update_placeholders})
                """, content_ids_to_update_points)
                conn.commit()
                print(f"[DB LOG] Points incremented for content IDs: {content_ids_to_update_points}")

            return final_results

        except sqlite3.Error as e:
            print(f"[DB ERROR] Error searching related content: {e}")
            return []
        finally:
            conn.close()

    def chat(self, prompt):
        history_text = "This is a conversation between an user and an assistant:\n"

        for i in range(len(self.expert_agent.history)):
            history_text = f"{history_text}\n{self.expert_agent.history[i]['role']} said: {self.expert_agent.history[i]['content']}"

        history_text = f"{history_text}\nuser said: {prompt}"

        print('[TAGGER AGENT OUTPUT FOR CONTEXT]')
        context_tags = self.tagger_agent.chat(history_text)
        context_tags = context_tags.split(',')
        context_tags = [t.strip() for t in context_tags]

        content_obj = "\n".join([c[1] for c in self.get_related_content_by_tags(context_tags)])
        if len(content_obj) == 0:
            content_obj = "No data to interpret yet."

        print("[CONTENT RETRIEVED FROM LONG TERM MEMORY]")
        print(content_obj)

        print("[INTERPRETER AGENT OUTPUT]")
        interpretation = self.interpreter_agent.chat(content_obj)

        print("[EXPERT AGENT OUTPUT]")
        expert_output = self.expert_agent.chat(prompt, temporal_input=f"CONTEXT FROM LONG TERM MEMORY: {interpretation}")

        print('[TAGGER AGENT OUTPUT FOR PROMPT]')
        prompt_tags = self.tagger_agent.chat(f"The following is what a user says: {prompt}")
        prompt_tags = prompt_tags.split(',')
        prompt_tags = [t.strip() for t in prompt_tags]

        print('[TAGGER AGENT OUTPUT FOR RESPONSE]')
        response_tags = self.tagger_agent.chat(f"The following is what an ai agent says: {expert_output}")
        response_tags = response_tags.split(',')
        response_tags = [t.strip() for t in response_tags]

        self.save_content_with_tags(f"user said: {prompt}", ['user'] + prompt_tags + context_tags)
        self.save_content_with_tags(f"agent said: {expert_output}", ['agent', 'ai'] + response_tags + context_tags)
        return expert_output



        


