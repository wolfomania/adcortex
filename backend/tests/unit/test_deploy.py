"""The Modal deployment file: the names the backend looks up, and what it sends."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import modal
import pytest

from neuromarketing.brain.remote import WORKER_CLASS
from neuromarketing.jobs.base import ORCHESTRATOR_FUNCTION

DEPLOY = Path(__file__).resolve().parents[3] / "deploy" / "modal_app.py"


@pytest.fixture(scope="module")
def deploy() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as patch:
        # Never read the developer's real .env (it holds keys).
        patch.setenv("NM_DEPLOY_ENV_FILE", "/nonexistent/.env")
        spec = importlib.util.spec_from_file_location("nm_deploy_app", DEPLOY)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        yield module


def test_the_backend_finds_the_deployed_functions(deploy: ModuleType) -> None:
    # Modal names functions and classes after their Python names.
    assert isinstance(getattr(deploy, ORCHESTRATOR_FUNCTION), modal.Function)
    assert isinstance(getattr(deploy, WORKER_CLASS), modal.Cls)
    assert isinstance(deploy.web, modal.Function)


def test_settings_the_deployment_decides_stay_local(
    deploy: ModuleType, tmp_path: Path
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# local development\n"
        "NM_LLM_MODEL=google:gemini-4-hydrogen\n"
        "GOOGLE_API_KEY=test-key\n"
        "NM_BRAIN_BACKEND=mock\n"
        "NM_DATA_DIR=.nm-data\n"
        "NM_PASSWORD=\n"
    )

    assert deploy.secret_values(env) == {
        "NM_LLM_MODEL": "google:gemini-4-hydrogen",
        "GOOGLE_API_KEY": "test-key",
    }


def test_a_missing_env_file_sends_nothing(deploy: ModuleType, tmp_path: Path) -> None:
    assert deploy.secret_values(tmp_path / ".env") == {}


def test_the_gpu_image_gets_the_backend_dependencies(deploy: ModuleType) -> None:
    requirements = deploy.backend_requirements()

    assert any(r.startswith("fastapi") for r in requirements)
    assert any(r.startswith("modal") for r in requirements)
