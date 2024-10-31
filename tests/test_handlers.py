# pytest.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from handlers import BotHandlers, WAITING_FOR_FOLDER_PATH, WAITING_FOR_QUESTION, WAITING_FOR_PROJECT_SELECTION

# Import necessary telegram classes
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, User, Message
from telegram.ext import ContextTypes


@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    user = MagicMock()
    user.id = 123456789
    user.full_name = 'Test User'
    user.language_code = 'en'
    update.effective_user = user
    message = MagicMock()
    message.text = '/start'
    message.reply_text = AsyncMock()
    update.message = message
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    context.bot = MagicMock()
    return context


@patch('handlers.AuthService')
@pytest.mark.asyncio
async def test_start(mock_auth_service, mock_update, mock_context):
    bot_handlers = BotHandlers()
    bot_handlers.auth_service = mock_auth_service.return_value

    await bot_handlers.start(mock_update, mock_context)

    # Check that reply_text was called
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Welcome to the AI document assistant bot!" in args[0]

    # Check that save_user_info was called
    bot_handlers.auth_service.save_user_info.assert_called_with(123456789, 'Test User', 'en')


@patch('handlers.AuthService')
@pytest.mark.asyncio
async def test_status_no_folder(mock_auth_service, mock_update, mock_context):
    bot_handlers = BotHandlers()
    bot_handlers.auth_service = mock_auth_service.return_value
    bot_handlers.auth_service.check_user_access.return_value = True

    # Mock the authorized_only decorator to always allow access
    await bot_handlers.status(mock_update, mock_context)

    # Check that reply_text was called
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "No folder path has been set yet" in args[0]


@patch('handlers.AuthService')
@patch('handlers.os')
@pytest.mark.asyncio
async def test_folder_valid_path(mock_os, mock_auth_service, mock_update, mock_context):
    bot_handlers = BotHandlers()
    bot_handlers.auth_service = mock_auth_service.return_value
    bot_handlers.auth_service.check_user_access.return_value = True

    # Mock os.path.isdir to return True
    mock_os.path.isdir.return_value = True
    # Mock os.listdir to return valid files
    mock_os.listdir.return_value = ['121212.pdf', 'report.docx', 'data.xlsx']

    # Simulate the /folder command
    mock_update.message.text = '/folder'
    await bot_handlers.folder(mock_update, mock_context)

    # Check that reply_text was called asking for folder path
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Please provide the folder path for your documents:" in args[0]

    # Now simulate user providing folder path
    # Update message text to folder path
    mock_update.message.text = '/path/to/folder'

    # Mock the llm_service
    llm_service = MagicMock()
    llm_service.load_and_index_documents.return_value = "Documents successfully indexed."
    llm_service.count_tokens_in_context.return_value = 5000
    mock_context.user_data['llm_service'] = llm_service

    # Call set_folder
    await bot_handlers.set_folder(mock_update, mock_context)

    # Check that reply_text was called indicating success
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Folder path successfully set to" in args[0]
    assert "Context storage is" in args[0]

@patch('handlers.AuthService')
@patch('handlers.os')
@pytest.mark.asyncio
async def test_folder_invalid_path(mock_os, mock_auth_service, mock_update, mock_context):
    bot_handlers = BotHandlers()
    bot_handlers.auth_service = mock_auth_service.return_value
    bot_handlers.auth_service.check_user_access.return_value = True

    # Mock os.path.isdir to return True
    mock_os.path.isdir.return_value = True

    # Mock os.listdir to return invalid files
    mock_os.listdir.return_value = ['image.jpg', 'archive.zip']

    # Simulate the /folder command
    mock_update.message.text = '/folder'
    await bot_handlers.folder(mock_update, mock_context)

    # Verify that the bot asks for the folder path
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Please provide the folder path for your documents:" in args[0]

    # Simulate the user providing the folder path
    mock_update.message.text = '/path/to/folder'

    # Mock the llm_service
    llm_service = MagicMock()
    llm_service.load_and_index_documents.return_value = "Documents successfully indexed."
    llm_service.count_tokens_in_context.return_value = 5000
    mock_context.user_data['llm_service'] = llm_service

    # Call set_folder
    await bot_handlers.set_folder(mock_update, mock_context)

    # Check that reply_text was called indicating no valid files
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "No valid files found in the folder. Please provide a folder containing valid documents." in args[0]


@patch('handlers.AuthService')
@patch('handlers.os')
@pytest.mark.asyncio
async def test_folder_invalid_path(mock_os, mock_auth_service, mock_update, mock_context):
    bot_handlers = BotHandlers()
    bot_handlers.auth_service = mock_auth_service.return_value
    bot_handlers.auth_service.check_user_access.return_value = True

    # Mock os.path.isdir to return False
    mock_os.path.isdir.return_value = False

    # Simulate the /folder command
    mock_update.message.text = '/folder'
    await bot_handlers.folder(mock_update, mock_context)

    # Check that reply_text was called asking for folder path
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Please provide the folder path for your documents:" in args[0]

    # Now simulate user providing folder path
    # Update message text to invalid folder path
    mock_update.message.text = '/invalid/path'

    # Call set_folder
    await bot_handlers.set_folder(mock_update, mock_context)

    # Check that reply_text was called indicating invalid path
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Invalid folder path" in args[0]


@patch('handlers.AuthService')
@pytest.mark.asyncio
async def test_unauthorized_user(mock_auth_service, mock_update, mock_context):
    bot_handlers = BotHandlers()
    bot_handlers.auth_service = mock_auth_service.return_value
    bot_handlers.auth_service.check_user_access.return_value = False

    # Mock update.message.reply_text
    mock_update.message.reply_text = AsyncMock()

    # Try to call a command that requires authorization
    await bot_handlers.status(mock_update, mock_context)

    # Check that reply_text was called with access denied message
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "You do not have access, please make the /request_access." in args[0]


@patch('handlers.AuthService')
@patch('handlers.os')
@pytest.mark.asyncio
async def test_request_access(mock_os, mock_auth_service, mock_update, mock_context):
    bot_handlers = BotHandlers()
    bot_handlers.auth_service = mock_auth_service.return_value

    # Mock update.message.reply_text
    mock_update.message.reply_text = AsyncMock()

    # Mock context.bot.send_message
    mock_context.bot.send_message = AsyncMock()

    # Mock environment variable for ADMIN_TELEGRAM_ID
    mock_os.getenv.return_value = '987654321'

    await bot_handlers.request_access(mock_update, mock_context)

    # Check that reply_text was called confirming request
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Your access request has been sent to the admin." in args[0]

    # Check that send_message was called to admin
    mock_context.bot.send_message.assert_called()
    args, kwargs = mock_context.bot.send_message.call_args
    assert kwargs['chat_id'] == '987654321'
    assert "Access request from" in kwargs['text']


@patch('handlers.AuthService')
@patch('handlers.DatabaseService')
@patch('handlers.os')
@pytest.mark.asyncio
async def test_handle_message(mock_os, mock_db_service, mock_auth_service, mock_update, mock_context):
    # Initialize BotHandlers and mock AuthService
    bot_handlers = BotHandlers()
    bot_handlers.auth_service = mock_auth_service.return_value
    bot_handlers.auth_service.check_user_access.return_value = True

    # Mock DatabaseService
    mock_context.user_data['db_service'] = mock_db_service.return_value

    # Mock the LLMService
    llm_service = MagicMock()
    llm_service.generate_response.return_value = ("This is a test response.", ["source1.pdf", "source2.docx"])
    mock_context.user_data['llm_service'] = llm_service

    # Mock os.path.isfile to return True
    mock_os.path.isfile.return_value = True

    # Set necessary user_data
    mock_context.user_data['vector_store_loaded'] = True
    mock_context.user_data['folder_path'] = '/path/to/folder'

    # **Add valid_files_in_folder to simulate presence of valid documents**
    mock_context.user_data['valid_files_in_folder'] = ['document.pdf', 'report.docx', 'data.xlsx']

    # Simulate a user message
    mock_update.message.text = 'What is the summary?'
    mock_update.message.reply_text = AsyncMock()

    # Call the handler
    await bot_handlers.handle_message(mock_update, mock_context)

    # Check that reply_text was called
    mock_update.message.reply_text.assert_called()
    args, kwargs = mock_update.message.reply_text.call_args

    # **Assertion to check if the bot's response contains the expected text**
    assert "This is a test response." in args[0]

# Continue with more tests for other methods...
