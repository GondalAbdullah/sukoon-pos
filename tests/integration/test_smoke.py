"""Phase 0's required smoke test: the application boots and serves a placeholder
page (Development Specification, Phase 0, Required Tests)."""


def test_app_boots_and_serves_placeholder(client, seeded):
    # an empty database now leads to the setup screen (ADR-0038 §6, test_setup.py);
    # this test is about a set-up shop serving its page
    response = client.get("/")
    assert response.status_code == 200
    assert b"sukoon" in response.data.lower()


def test_app_factory_produces_distinct_instances():
    from sukoon.app import create_app

    app_a = create_app("testing")
    app_b = create_app("testing")
    assert app_a is not app_b
