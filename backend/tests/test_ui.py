import os
from unittest import mock
from dotenv import dotenv_values
from app import ui, config

def test_handle_save_config_security():
    # Save current state
    if os.path.exists(".env"):
        os.rename(".env", ".env.backup")

    try:
        # A malicious key attempting to inject a newline
        malicious_key = "sk-fakekey\nMALICIOUS_VAR=hacked\r"

        # Make sure config has some defaults to avoid NoneType errors
        config.LANGFUSE_PUBLIC_KEY = "test_pub"
        config.LANGFUSE_SECRET_KEY = "test_sec"
        config.LANGFUSE_HOST = "test_host"

        # Call the function
        result = ui.handle_save_config(malicious_key)

        # Verify success message
        assert result == "Configurations saved successfully!"

        # Verify the .env file was created and contains the sanitized key
        assert os.path.exists(".env")

        # Read the .env file using python-dotenv to verify parsing
        parsed_env = dotenv_values(".env")

        # The key should be sanitized (no newlines)
        assert parsed_env["OPENAI_API_KEY"] == "sk-fakekeyMALICIOUS_VAR=hacked"
        # The injected variable should NOT exist
        assert "MALICIOUS_VAR" not in parsed_env

    finally:
        # Cleanup and restore
        if os.path.exists(".env"):
            os.remove(".env")
        if os.path.exists(".env.backup"):
            os.rename(".env.backup", ".env")
