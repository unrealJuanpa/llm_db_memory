# LLM DB Memory: An Experiment in Long-Term Memory for LLM Agents

**Status: In Development**

This project is an experimental implementation of a long-term memory system for Large Language Model (LLM) agents. It explores how to overcome the inherent limitation of finite context windows in LLMs by creating a persistent, searchable memory using a local SQLite database.

## The Problem

LLM agents are powerful, but they suffer from amnesia. Their memory is limited to the current conversation history (short-term memory). Once the context window is full, they forget past interactions. This project aims to solve this by providing a mechanism for the agent to store and retrieve relevant information from a long-term memory store.

## The Solution: A Composite Agent Architecture

The core of this project is the `CompositeAgent`, which orchestrates a set of specialized LLM agents to manage both short-term and long-term memory.

### Key Components

*   **`LLMAgent`**: A basic agent responsible for direct interaction with an LLM through an API. It can be configured with different models and system prompts.

*   **`CompositeAgent`**: The main orchestrator. It manages the overall chat flow and memory operations. It contains three specialized agents:
    *   **Expert Agent**: The main "personality" of the agent that chats with the user.
    *   **Tagger Agent**: An agent whose sole purpose is to generate descriptive tags from a piece of text.
    *   **Interpreter Agent**: An agent that synthesizes and summarizes information retrieved from the long-term memory.

*   **Short-Term Memory**: A simple list of the most recent interactions in the conversation history.

*   **Long-Term Memory**: An SQLite database (`<agent_name>_db.sqlite`) that stores information in a structured way.
    *   **Content Table**: Stores chunks of text.
    *   **Tags Table**: Stores unique tags.
    *   **Content-Tags Table**: Links content with tags, creating a many-to-many relationship.

### How it Works: The Interaction Flow

1.  **User Input**: The user sends a message to the `CompositeAgent`.
2.  **Context Tagging**: The `Tagger Agent` analyzes the conversation history (short-term memory) and generates a set of tags that represent the current context.
3.  **Long-Term Memory Retrieval**: The `CompositeAgent` uses these tags to search the SQLite database for relevant content. The search query prioritizes content that matches more tags and has been retrieved more often (based on a "points" system).
4.  **Information Interpretation**: The retrieved content is passed to the `Interpreter Agent`, which creates a concise summary.
5.  **Expert Response**: The `Expert Agent` receives the user's original prompt *and* the summary from the `Interpreter Agent`. This summary acts as a "memory" that informs the expert's response.
6.  **Memory Storage**:
    *   The user's prompt and the agent's final response are individually sent to the `Tagger Agent` to generate new tags.
    *   Both the prompt and the response are saved as new entries in the long-term memory, associated with their respective tags and the context tags.

## How to Use

1.  **Prerequisites**:
    *   Python 3
    *   An Ollama server (or any other LLM server with a compatible API) running and accessible from your network.
    *   The `requests` library. You can install it with:
        ```bash
        pip install requests
        ```

2.  **Configuration**:
    *   Open `main.py`.
    *   Modify the `CompositeAgent` parameters:
        *   `agent_name`: A name for your agent (this will also be the name of the database file).
        *   `server_ip`: The IP address and port of your LLM server.
        *   `expert_model`, `tagger_model`, `interpreter_model`: The names of the models you want to use for each agent.
        *   `system_prompt`: The system prompt for the `Expert Agent`.

3.  **Running the Agent**:
    ```bash
    python main.py
    ```

## Customization

This project is designed to be modular and extensible. You can:

*   **Swap Models**: Easily change the models for each specialized agent to experiment with different LLMs for different tasks (e.g., a small, fast model for tagging and a powerful model for the expert).
*   **Modify Prompts**: Change the system prompts in `composite_agent.py` to alter the behavior of the tagger and interpreter.
*   **Extend the Database Schema**: Add more metadata to the `content` table, such as timestamps or relationship types.
*   **Improve Retrieval Logic**: Modify the `get_related_content_by_tags` method to experiment with different information retrieval algorithms.

## TODO
* **Forget**: A point system is currently in place, where each "memory" increases by one point each time it is returned. The plan is to have a defined limit so that when a "memory" exceeds a maximum time limit and a minimum number of points, it is forgotten.
* **Notion of time**: Add a notion of time to the agents.

* New Version
dos agentes
- tagger: recibe las tags actuales del contexto + un mensaje a la vez y actualiza las tags de contexto
- expert: recibe las interacciones del contexto y genera una respuesta

Flujo de informacion:
1) se recibe el mensaje del usuario
2) se le pasan las tags de contexto + el mensaje del usuario y el agente actualiza las tags
3) se consultan en la bd las tags pertinentes y se devuelven las interacciones con fecha (nombre del mes, numero del dia y el dia en palabras) y hora
4) se le pasan las interacciones de contexto al experto junto con el mensaje del usuario y se genera la respuesta
5) el tagger toma las tags de contexto + la respuesta del agente y genera nuevas tags
6) nuevo ciclo iniciado