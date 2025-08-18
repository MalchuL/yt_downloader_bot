import pytest
from dotenv import load_dotenv


@pytest.fixture(scope="session", autouse=True)
def load_test_environment():
    """
    A session-wide fixture to set up the environment for tests.
    This runs automatically for every test session.
    It explicitly loads the .env file to ensure that settings,
    especially the required BOT_TOKEN, are available before
    Pydantic performs validation at module import time.
    """
    load_dotenv()
