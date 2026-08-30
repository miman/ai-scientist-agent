## ⚙️ Core Stack & Port Configurations

Following deployment, your local loop splits across these core ports on the host system:
* **FastAPI Backend Service Backend Engine:** Port `8500`
* **Streamlit Dashboard Interface Frontend Control Panel:** Port `8501`
* **ChromaDB Vector Store Allocation Layer:** Port `8000`

---

## 📦 Service Architecture & Internal Container Networks

The application architecture utilizes an internal bridged network (`hermes-net`) to handle container-to-container queries.

### Critical Configuration Rules for `ui.py`
When running locally for standalone testing outside of your containers, the UI connects via:
```python
API_URL = "http://localhost:8500"
```

When running inside the orchestrated Docker stack, the frontend cannot locate the API over standard localhost routing. It queries across the bridge network using the compose service name
```Python
API_URL = "http://hermes_api:8500"
```

### 🚀 Post-UI Update Deployment Strategy
When deploying features that change agent logic or introduce dependencies (such as streamlit), use the following re-initialization sequence:
1. Add your requirements to **requirements.txt**.
2. Execute the automated installer shell environment

```Bash
./install.sh
```

The **install.sh** script automatically carries out cache invalidation steps:
* It stops previous system instances (docker-compose down) to release active port lines.
* It prunes old builder image caches (docker builder prune -f) to ensure your modified code changes inside **app.py** and the **ui.py** additions are completely built into the container environment.  
