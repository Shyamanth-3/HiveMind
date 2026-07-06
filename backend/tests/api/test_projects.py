def test_create_project(client):
    response = client.post(
        "/api/v1/projects/",
        json={
            "name": "Test Project",
            "owner": "shyam",
            "goal_summary": "Testing the API"
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Project"
    assert data["owner"] == "shyam"
    assert "id" in data

def test_get_projects(client):
    # First create one
    client.post(
        "/api/v1/projects/",
        json={
            "name": "Test Project 2",
            "owner": "shyam",
            "goal_summary": "Testing the API 2"
        },
    )
    
    response = client.get("/api/v1/projects/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["name"] == "Test Project 2"
