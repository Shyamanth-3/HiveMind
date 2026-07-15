import urllib.request
import json
import time

try:
    print("Fetching projects...")
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1/projects/")
    with urllib.request.urlopen(req) as response:
        projects = json.loads(response.read().decode())
    
    project_id = projects[0]["id"]
    print(f"Project ID: {project_id}")

    print("Creating run...")
    data = json.dumps({"project_id": project_id, "goal": "End-to-End Testing Goal"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1/runs/", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
    
    print("Success! Check FastAPI and Scheduler logs.")
except Exception as e:
    print(f"Error: {e}")
