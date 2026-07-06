def test_create_and_get_run(client):
    # Create project first
    proj_res = client.post(
        "/api/v1/projects/",
        json={
            "name": "Run Test Project",
            "owner": "shyam",
            "goal_summary": "Testing Runs"
        },
    )
    project_id = proj_res.json()["id"]

    # Create run
    run_res = client.post(
        "/api/v1/runs/",
        json={
            "project_id": project_id,
            "goal": "Build something cool"
        },
    )
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert run_data["goal"] == "Build something cool"
    assert run_data["status"] == "running"
    run_id = run_data["id"]

    # Get run
    get_res = client.get(f"/api/v1/runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["goal"] == "Build something cool"

def test_update_run(client):
    proj_res = client.post(
        "/api/v1/projects/",
        json={
            "name": "Run Test Project 2",
            "owner": "shyam",
            "goal_summary": "Testing Runs 2"
        },
    )
    project_id = proj_res.json()["id"]

    run_res = client.post(
        "/api/v1/runs/",
        json={
            "project_id": project_id,
            "goal": "Build something else"
        },
    )
    run_id = run_res.json()["id"]

    update_res = client.patch(
        f"/api/v1/runs/{run_id}",
        json={"status": "completed", "duration_ms": 5000}
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["status"] == "completed"
    assert updated_data["duration_ms"] == 5000
