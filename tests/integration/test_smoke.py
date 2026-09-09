"""Phase 0's required smoke test: the application boots and serves a placeholder
page (Development Specification, Phase 0, Required Tests)."""


def test_app_boots_and_serves_placeholder(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"sukoon" in response.data.lower()


def test_app_factory_produces_distinct_instances():
    from sukoon.app import create_app

    app_a = create_app("testing")
    app_b = create_app("testing")
    assert app_a is not app_b
