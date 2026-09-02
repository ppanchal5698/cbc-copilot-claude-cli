"""Job enqueue authorization — estimators may run pipeline work only."""
from __future__ import annotations

import pytest

from cbc.schemas.common import ESTIMATOR_JOB_TYPES


@pytest.mark.parametrize("job_type", sorted(ESTIMATOR_JOB_TYPES))
def test_estimators_may_enqueue_pipeline_jobs(client, as_role, job_type: str) -> None:
    as_role("estimator")
    response = client.post("/api/jobs", json={"type": job_type, "projectId": "DEMO-001"})
    assert response.status_code in (201, 404, 409), response.text


def test_estimators_cannot_enqueue_delete_catalog(client, as_role) -> None:
    as_role("estimator")
    response = client.post(
        "/api/jobs",
        json={"type": "delete_catalog", "payload": {"filename": "hager.pdf"}},
    )
    assert response.status_code == 403


def test_admins_may_enqueue_delete_catalog(client, as_role) -> None:
    as_role("admin")
    response = client.post(
        "/api/jobs",
        json={"type": "delete_catalog", "payload": {"filename": "hager.pdf"}},
    )
    assert response.status_code == 201, response.text
