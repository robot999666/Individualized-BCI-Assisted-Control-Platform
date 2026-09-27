import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import assistant_service
from app.core.config import Settings
from app.main import app
from app.services.project_assistant import ProjectAssistantService
from app.services.rag import ProjectKnowledgeIndex
from backend.tests.test_platform import clients

client = TestClient(app)
repo_dir = Path(__file__).resolve().parents[2]


def test_rag_index_loads_and_finds_project_facts() -> None:
    index = ProjectKnowledgeIndex(repo_dir)
    assert index.ready is True
    assert len(index.documents) >= 4
    assert len(index.chunks) > 10

    results = index.search("四分类分别是什么？", top_k=5)
    assert results
    assert any("左转" in result.chunk.text for result in results)


def test_unknown_question_does_not_call_provider() -> None:
    settings = Settings(openai_api_key="test-key", _env_file=None)
    service = ProjectAssistantService(settings, repo_dir)

    response = __import__("asyncio").run(service.chat("火星基地的食堂菜单是什么？"))
    assert response.answer == "当前项目资料中未说明这一内容。"
    assert response.sources == []


def test_service_starts_without_api_key() -> None:
    settings = Settings(openai_api_key=None, _env_file=None)
    service = ProjectAssistantService(settings, repo_dir)
    assert service.index.ready is True
    assert service.provider_configured is False


def test_assistant_health_never_returns_key() -> None:
    response = client.get("/api/v1/assistant/health")
    assert response.status_code == 200
    data = response.json()
    assert data["rag_ready"] is True
    assert data["document_count"] >= 4
    assert data["model"] == "deepseek-v4.1-flash"
    assert "api_key" not in data
    assert "key" not in json.dumps(data).lower()


def test_chat_requires_provider_configuration(monkeypatch) -> None:
    monkeypatch.setattr(assistant_service.settings, "openai_api_key", None)
    response = client.post(
        "/api/v1/assistant/chat",
        json={"question": "这个项目解决什么问题？"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "项目知识服务暂时不可用，请稍后再试。"


def test_question_length_is_limited() -> None:
    response = client.post(
        "/api/v1/assistant/chat",
        json={"question": "问" * 501},
    )
    assert response.status_code == 422


def test_only_public_knowledge_is_indexed():
    index = ProjectKnowledgeIndex(repo_dir)
    assert all(path.parent == repo_dir/'docs'/'rag' for path in index.documents)
    for question in ('校准和同源回放如何操作？', 'EOG怎么确认？', '3D护理床如何工作？'):
        assert index.search(question)


def test_provider_receives_requested_model_and_cited_public_context(monkeypatch):
    import io
    from app.services import project_assistant
    service=ProjectAssistantService(Settings(openai_api_key='test-key',_env_file=None),repo_dir)
    requests=[]
    def provider(request, timeout):
        requests.append((request, json.loads(request.data), timeout))
        return io.BytesIO(json.dumps({'choices':[{'message':{'content':'依据资料，先校准再准备同源回放。'},'finish_reason':'stop'}]}).encode())
    monkeypatch.setattr(project_assistant,'urlopen',provider)
    response=__import__('asyncio').run(service.chat('校准和同源回放如何操作？'))
    assert response.sources
    request,payload,_=requests[0]
    assert payload['model']=='deepseek-v4.1-flash'
    assert request.get_header('Authorization')=='Bearer test-key'
    assert '<project_context>' in payload['messages'][1]['content']
    assert 'DATABASE_URL' not in json.dumps(payload)


def test_busy_provider_rejects_without_call(monkeypatch):
    from app.services.project_assistant import AssistantBusyError
    import pytest
    service=ProjectAssistantService(Settings(openai_api_key='test-key',_env_file=None),repo_dir)
    service._active_requests=2
    with pytest.raises(AssistantBusyError):
        __import__('asyncio').run(service.chat('EOG如何工作？'))


def test_truncated_provider_answer_is_not_presented_as_complete(monkeypatch):
    import io
    import pytest
    from app.services import project_assistant
    service=ProjectAssistantService(Settings(openai_api_key='test-key',_env_file=None),repo_dir)
    monkeypatch.setattr(project_assistant,'urlopen',lambda *a,**k:io.BytesIO(b'{"choices":[{"message":{"content":"partial"},"finish_reason":"length"}]}'))
    with pytest.raises(project_assistant.AssistantProviderError):
        __import__('asyncio').run(service.chat('EOG如何工作？'))
    assert service._active_requests==0


def test_production_guest_chat_allowed_but_anonymous_requires_login(monkeypatch, clients):
    from app.main import settings
    from app.schemas.assistant import AssistantChatResponse
    async def chat(question):
        return AssistantChatResponse(answer='项目说明',sources=[])
    monkeypatch.setattr(assistant_service,'chat',chat)
    monkeypatch.setattr(settings,'production',True)
    response=client.post('/api/v1/assistant/chat',json={'question':'EOG如何工作？'},headers={'X-BCI-Request':'1'})
    assert response.status_code==401
    response=clients['guest'].post('/api/v1/assistant/chat',json={'question':'EOG如何工作？'},headers={'X-BCI-Request':'1'})
    assert response.status_code==200
    assert clients['guest'].post('/api/v1/analyze',headers={'X-BCI-Request':'1'}).status_code==403
