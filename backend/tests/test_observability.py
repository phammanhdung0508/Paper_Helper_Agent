import pytest
import uuid
from fastapi import HTTPException
from app import config
from main import log_chat_feedback, run_agent_chat, FeedbackRequest, ChatRequest
from app.agents import MasteryEvaluatorAgent

def test_trace_uuid_format():
    """Verify that generated trace IDs conform to valid UUIDv4 formats."""
    trace_id = str(uuid.uuid4())
    # This should parse successfully
    parsed_uuid = uuid.UUID(trace_id, version=4)
    assert str(parsed_uuid) == trace_id

def test_feedback_graceful_empty_trace():
    """Verify feedback logging raises 400 HTTPException when trace_id is empty."""
    req = FeedbackRequest(rating="up", trace_id="")
    with pytest.raises(HTTPException) as exc_info:
        log_chat_feedback(req)
    assert exc_info.value.status_code == 400
    assert "trace_id is required" in exc_info.value.detail

def test_feedback_graceful_none_trace():
    # Since FeedbackRequest requires trace_id as string, none or empty string both behave similarly.
    req = FeedbackRequest(rating="down", trace_id="")
    with pytest.raises(HTTPException) as exc_info:
        log_chat_feedback(req)
    assert exc_info.value.status_code == 400

def test_host_validation_config():
    """Verify that LANGFUSE_HOST is configured and starts with http:// or https://."""
    host = config.LANGFUSE_HOST
    assert host is not None
    assert host.startswith("http://") or host.startswith("https://")

def test_mastery_unified_score_formula():
    """Verify unified mastery weighted formula is computed correctly."""
    scores = {
        "memory": 80,        # weight 0.25 -> 20
        "comprehension": 90, # weight 0.30 -> 27
        "structure": 70,     # weight 0.20 -> 14
        "application": 85    # weight 0.25 -> 21.25
    }
    # Expected: 20 + 27 + 14 + 21.25 = 82.25 -> rounded to 82
    expected = round(80 * 0.25 + 90 * 0.30 + 70 * 0.20 + 85 * 0.25)
    calculated = MasteryEvaluatorAgent.calculate_unified_score(scores)
    assert calculated == expected

def test_mastery_monotone_clamp():
    """Verify that monotone clamping prevents mastery scores from decreasing."""
    prev = {
        "memory": 50,
        "comprehension": 60,
        "structure": 40,
        "application": 30
    }
    # Student scores drop on a bad assessment
    next_eval = {
        "memory": 40,        # lower than 50 -> should stay 50
        "comprehension": 70, # higher than 60 -> should become 70
        "structure": 30,     # lower than 40 -> should stay 40
        "application": 80    # higher than 30 -> should become 80
    }
    clamped = MasteryEvaluatorAgent.clamp_monotone(prev, next_eval)
    assert clamped["memory"] == 50
    assert clamped["comprehension"] == 70
    assert clamped["structure"] == 40
    assert clamped["application"] == 80

from unittest.mock import patch, MagicMock

def test_feedback_success_mocked():
    """Verify that feedback is successfully logged when trace_id and credentials are present."""
    with patch("main.config") as mock_config:
        mock_config.LANGFUSE_PUBLIC_KEY = "pk-mock"
        mock_config.LANGFUSE_SECRET_KEY = "sk-mock"
        mock_config.LANGFUSE_HOST = "http://localhost:3000"
        
        with patch("langfuse.Langfuse") as mock_langfuse_class:
            mock_lf = MagicMock()
            mock_langfuse_class.return_value = mock_lf
            
            req = FeedbackRequest(rating="up", trace_id="valid-trace-id")
            res = log_chat_feedback(req)
            
            mock_langfuse_class.assert_called_once_with(
                public_key="pk-mock",
                secret_key="sk-mock",
                host="http://localhost:3000"
            )
            mock_lf.score.assert_called_once_with(
                trace_id="valid-trace-id",
                name="helpfulness",
                value=1.0
            )
            assert "Feedback logged successfully" in res.status

def test_chat_trace_callback_generation():
    """Verify that CallbackHandler is initialized and updated during chat when keys are configured."""
    with patch("main.config") as mock_config, \
         patch("app.supervisor.supervisor") as mock_supervisor, \
         patch("main.database.add_chat_message") as mock_add_msg, \
         patch("langfuse.callback.CallbackHandler") as mock_callback_handler, \
         patch("langfuse.Langfuse") as mock_langfuse_class:
         
        mock_config.LANGFUSE_PUBLIC_KEY = "pk-mock"
        mock_config.LANGFUSE_SECRET_KEY = "sk-mock"
        mock_config.LANGFUSE_HOST = "http://localhost:3000"
        
        mock_supervisor.route_and_execute.return_value = {
            "ai_reply": "Hello AI response",
            "route_taken": "general"
        }
        
        mock_lf = MagicMock()
        mock_langfuse_class.return_value = mock_lf
        
        req = ChatRequest(
            query="Hello",
            chat_history=[],
            doc_id="doc-123",
            session_id="session-456"
        )
        res = run_agent_chat(req)
        
        # Verify CallbackHandler was initialized with trace info
        mock_callback_handler.assert_called_once()
        kwargs = mock_callback_handler.call_args[1]
        assert kwargs["trace_id"] == res.trace_id
        assert kwargs["session_id"] == "session-456"
        assert kwargs["public_key"] == "pk-mock"
        assert kwargs["secret_key"] == "sk-mock"
        
        # Verify Langfuse was initialized and trace metadata was updated with route_taken
        mock_langfuse_class.assert_called_once_with(
            public_key="pk-mock",
            secret_key="sk-mock",
            host="http://localhost:3000"
        )
        mock_lf.trace.assert_called_once_with(id=res.trace_id)
        mock_lf.trace(id=res.trace_id).update.assert_called_once_with(
            metadata={
                "session_id": "session-456",
                "user_id": "default_student_501",
                "route_taken": "general"
            }
        )

def test_host_validation_boundaries():
    """Test boundary checks on host validation errors."""
    with patch("main.config") as mock_config:
        mock_config.LANGFUSE_PUBLIC_KEY = "pk-mock"
        mock_config.LANGFUSE_SECRET_KEY = "sk-mock"
        mock_config.LANGFUSE_HOST = ""
        
        with patch("langfuse.Langfuse", side_effect=ValueError("Invalid Host URL")):
            req = FeedbackRequest(rating="up", trace_id="some-trace-id")
            with pytest.raises(HTTPException) as exc_info:
                log_chat_feedback(req)
            assert exc_info.value.status_code == 500
            assert "Invalid Host URL" in exc_info.value.detail
