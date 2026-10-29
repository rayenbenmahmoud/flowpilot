import pytest

from automation.models import Execution, Workflow

pytestmark = pytest.mark.django_db(transaction=True)

NEW = {
    "name": "Big orders",
    "trigger_event": "order.created",
    "match_mode": "all",
    "conditions": [{"field": "total", "operator": "gte", "value": 500}],
    "actions": [{"type": "notify_internal", "config": {"title": "Big order {{ payload.order_id }}"}}],
}


class TestAuth:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/workflows/",
            "/api/v1/executions/",
            "/api/v1/dashboard/",
            "/api/v1/integrations/",
            "/api/v1/notifications/",
            "/api/v1/demo/scenarios/",
        ],
    )
    def test_requires_authentication(self, anon, path):
        r = anon.get(path)
        assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"

    def test_unauthenticated_cannot_run_or_retry(self, anon, make_workflow, integration_rows):
        wf = make_workflow("order-notification")
        assert (
            anon.post(
                f"/api/v1/workflows/{wf.id}/run/", {"payload": {"order_id": "1", "total": 1}}, format="json"
            ).status_code
            == 401
        )
        assert anon.post("/api/v1/demo/scenarios/new-order/run/").status_code == 401

    def test_login_and_logout(self, anon, user):
        bad = anon.post("/api/v1/auth/login/", {"username": "tester", "password": "wrong"}, format="json")
        assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"
        ok = anon.post("/api/v1/auth/login/", {"username": "tester", "password": "pw-for-tests-123"}, format="json")
        token = ok.json()["token"]
        anon.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        assert anon.get("/api/v1/auth/me/").json()["username"] == "tester"
        assert anon.post("/api/v1/auth/logout/").status_code == 204
        assert anon.get("/api/v1/auth/me/").status_code == 401

    def test_login_is_rate_limited(self, anon, user, monkeypatch):
        from automation.throttles import LoginThrottle

        monkeypatch.setitem(LoginThrottle.THROTTLE_RATES, "login", "3/min")
        codes = [
            anon.post("/api/v1/auth/login/", {"username": "tester", "password": "x"}, format="json").status_code
            for _ in range(5)
        ]
        assert codes[-1] == 429

    def test_public_config_exposes_demo_flag_only(self, anon):
        body = anon.get("/api/v1/config/").json()
        assert body["demo_mode"] is True and set(body) == {"app", "version", "demo_mode"}


class TestWorkflowManagement:
    def test_create_defaults_to_disabled_and_returns_stats(self, api):
        r = api.post("/api/v1/workflows/", NEW, format="json")
        assert r.status_code == 201
        assert r.json()["status"] == "disabled" and r.json()["runs_total"] == 0 and r.json()["version"] == 1

    def test_validation_errors_are_field_level(self, api):
        bad = {**NEW, "trigger_event": "nope", "actions": [{"type": "send_email", "config": {"to": "a@b.co"}}]}
        r = api.post("/api/v1/workflows/", bad, format="json")
        assert r.status_code == 400
        details = r.json()["error"]["details"]
        assert "trigger_event" in details and any("'subject' is required" in m for m in details["actions"])

    def test_edit_bumps_version_only_when_logic_changes(self, api):
        wid = api.post("/api/v1/workflows/", NEW, format="json").json()["id"]
        assert (
            api.patch(f"/api/v1/workflows/{wid}/", {"description": "just text"}, format="json").json()["version"] == 1
        )
        changed = api.patch(f"/api/v1/workflows/{wid}/", {"conditions": []}, format="json")
        assert changed.json()["version"] == 2

    def test_enable_disable_archive_restore(self, api):
        wid = api.post("/api/v1/workflows/", NEW, format="json").json()["id"]
        assert api.post(f"/api/v1/workflows/{wid}/enable/").json()["status"] == "active"
        assert api.post(f"/api/v1/workflows/{wid}/enable/").json()["status"] == "active"  # idempotent
        assert api.post(f"/api/v1/workflows/{wid}/disable/").json()["status"] == "disabled"
        archived = api.post(f"/api/v1/workflows/{wid}/archive/").json()
        assert archived["status"] == "archived" and archived["archived_at"]
        assert api.post(f"/api/v1/workflows/{wid}/enable/").status_code == 409  # must restore first
        assert api.patch(f"/api/v1/workflows/{wid}/", {"name": "x"}, format="json").status_code == 400
        assert api.post(f"/api/v1/workflows/{wid}/restore/").json()["status"] == "disabled"

    def test_delete_is_not_offered(self, api, make_workflow):
        wf = make_workflow("order-notification")
        assert api.delete(f"/api/v1/workflows/{wf.id}/").status_code == 405

    def test_from_template(self, api):
        r = api.post(
            "/api/v1/workflows/from-template/",
            {"template_key": "low-inventory-alert", "name": "Stock watch"},
            format="json",
        )
        assert r.status_code == 201 and r.json()["name"] == "Stock watch" and r.json()["status"] == "disabled"
        assert api.post("/api/v1/workflows/from-template/", {"template_key": "nope"}, format="json").status_code == 404

    def test_list_filters(self, api, make_workflow):
        make_workflow("order-notification")
        make_workflow("welcome-email", status="disabled")
        make_workflow("low-inventory-alert", status="archived")
        names = lambda q: [w["trigger_event"] for w in api.get(f"/api/v1/workflows/?{q}").json()["results"]]  # noqa: E731
        assert names("status=active") == ["order.created"]
        assert names("status=archived") == ["inventory.updated"]
        assert names("q=welcome") == ["customer.registered"]

    def test_manual_run_validates_payload_and_requires_active(self, api, make_workflow, integration_rows):
        wf = make_workflow("order-notification")
        assert (
            api.post(f"/api/v1/workflows/{wf.id}/run/", {"payload": {"order_id": "A"}}, format="json").status_code
            == 400
        )
        ok = api.post(f"/api/v1/workflows/{wf.id}/run/", {"payload": {"order_id": "A", "total": 3}}, format="json")
        assert ok.status_code == 202 and ok.json()["status"] == "success" and ok.json()["source"] == "manual"
        Workflow.objects.filter(pk=wf.pk).update(status="disabled")
        assert (
            api.post(
                f"/api/v1/workflows/{wf.id}/run/", {"payload": {"order_id": "A", "total": 3}}, format="json"
            ).status_code
            == 409
        )

    def test_manual_run_honours_idempotency_key_header(self, api, make_workflow, integration_rows):
        wf = make_workflow("order-notification")
        body = {"payload": {"order_id": "A", "total": 3}}
        a = api.post(f"/api/v1/workflows/{wf.id}/run/", body, format="json", HTTP_IDEMPOTENCY_KEY="click-1")
        b = api.post(f"/api/v1/workflows/{wf.id}/run/", body, format="json", HTTP_IDEMPOTENCY_KEY="click-1")
        assert a.status_code == 202 and b.status_code == 200 and a.json()["id"] == b.json()["id"]
        assert Execution.objects.count() == 1


class TestExecutions:
    @pytest.fixture
    def history(self, make_workflow, integration_rows, api):
        from automation.engine.runner import dispatch_event

        make_workflow("welcome-email")
        make_workflow("order-notification")
        dispatch_event(
            "customer.registered",
            {"customer_id": "c1", "email": "ok@example.com", "name": "Okay"},
            source="webhook",
            idempotency_key="1",
        )
        dispatch_event(
            "customer.registered",
            {"customer_id": "c2", "email": "bad@bounce.example.com", "name": "Bouncer"},
            source="webhook",
            idempotency_key="2",
        )
        dispatch_event("order.created", {"order_id": "ORD-55", "total": 9}, source="webhook", idempotency_key="3")

    def test_filter_by_status_workflow_and_search(self, api, history):
        get = lambda q: api.get(f"/api/v1/executions/?{q}").json()["results"]  # noqa: E731
        assert len(get("")) == 3
        assert [e["status"] for e in get("status=failed")] == ["failed"]
        assert len(get("status=failed&status=success")) == 3
        assert [e["input_summary"] for e in get("q=ORD-55")] == ["Order ORD-55, total 9"]
        assert get("q=bounce")[0]["status"] == "failed"
        wid = get("q=ORD-55")[0]["workflow"]
        assert len(get(f"workflow={wid}")) == 1

    def test_filter_by_date(self, api, history):
        assert len(api.get("/api/v1/executions/?date_from=2999-01-01").json()["results"]) == 0
        assert len(api.get("/api/v1/executions/?date_to=2999-01-01&date_from=2000-01-01").json()["results"]) == 3

    def test_detail_has_logs_payload_and_retry_info(self, api, history):
        failed = Execution.objects.get(status="failed")
        d = api.get(f"/api/v1/executions/{failed.id}/").json()
        assert d["error_code"] == "recipient_rejected" and d["can_retry"] is True and d["logs"][-1]["level"] == "error"
        assert d["payload"]["email"] == "bad@bounce.example.com" and d["retried_by"] is None

    def test_retry_endpoint_and_conflicts(self, api, make_workflow, integration_rows):
        from automation.engine.runner import dispatch_event

        make_workflow("welcome-email")
        dispatch_event(
            "customer.registered",
            {"customer_id": "c", "email": "x@flaky.example.com", "name": "X"},
            source="webhook",
            idempotency_key="f",
        )
        failed = Execution.objects.get(status="failed")
        ok = api.post(f"/api/v1/executions/{failed.id}/retry/")
        assert ok.status_code == 202 and ok.json()["status"] == "success" and ok.json()["attempt"] == 2
        again = api.post(f"/api/v1/executions/{failed.id}/retry/")
        assert again.status_code == 409 and again.json()["error"]["code"] == "already_retried"
        done = api.post(f"/api/v1/executions/{ok.json()['id']}/retry/")
        assert done.json()["error"]["code"] == "not_failed"

    def test_dashboard_numbers_match_the_data(self, api, history):
        d = api.get("/api/v1/dashboard/").json()
        assert d["workflows"]["total"] == 2 and d["workflows"]["active"] == 2
        assert d["executions"]["success"] == 2 and d["executions"]["failed"] == 1
        assert d["needs_attention"] == 1 and len(d["daily"]) == 7 and len(d["recent"]) == 3
        assert d["success_rate"] == 66.7

    def test_dashboard_with_no_data(self, api):
        d = api.get("/api/v1/dashboard/").json()
        assert d["success_rate"] is None and d["executions"]["total"] == 0


class TestOutputsAndDemo:
    def test_scenarios_run_end_to_end(self, api, make_workflow, integration_rows):
        make_workflow("welcome-email")
        make_workflow("failure-notification")
        r = api.post("/api/v1/demo/scenarios/bounced-email/run/")
        assert r.status_code == 202
        assert r.json()["runs"][0]["executions"][0]["status"] == "failed"
        notes = api.get("/api/v1/notifications/?severity=error").json()["results"]
        assert len(notes) == 1 and "Workflow failed" in notes[0]["title"]

    def test_duplicate_scenario_shows_second_delivery_as_duplicate(self, api, make_workflow, integration_rows):
        make_workflow("order-notification")
        runs = api.post("/api/v1/demo/scenarios/duplicate-event/run/").json()["runs"]
        assert [e["duplicate"] for e in runs[0]["executions"]] == [False]
        assert [e["duplicate"] for e in runs[1]["executions"]] == [True]
        assert Execution.objects.count() == 1

    def test_demo_tools_are_off_when_demo_mode_is_off(self, api, settings):
        settings.FLOWPILOT_DEMO_MODE = False
        assert api.post("/api/v1/demo/reset/").status_code == 403
        assert api.get("/api/v1/demo/scenarios/").json()["error"]["code"] == "demo_disabled"

    def test_seed_is_idempotent_and_realistic(self, api, settings):
        from django.core.management import call_command

        call_command("seed_demo")
        first = Execution.objects.count()
        call_command("seed_demo")
        assert Execution.objects.count() == first > 50
        assert Workflow.objects.filter(status="archived").exists()
        assert Execution.objects.filter(
            status="failed", retries__isnull=True
        ).exists()  # something to retry in the demo
        assert api.post("/api/v1/demo/reset/").status_code == 200

    def test_seed_refuses_outside_demo_mode(self, settings):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        settings.FLOWPILOT_DEMO_MODE = False
        with pytest.raises(CommandError):
            call_command("seed_demo")
