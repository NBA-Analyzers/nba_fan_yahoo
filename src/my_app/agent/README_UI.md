# Fantasy Basketball Helper - Web UI

A simple, modern web interface for chatting with the Fantasy Basketball Helper API.

## Features

- 🎨 **Modern UI**: Clean, responsive design with gradient backgrounds and smooth animations
- 💬 **Real-time Chat**: Send messages and receive responses from the Fantasy Basketball Helper
- 🔄 **Session Management**: Automatic session handling with the ability to start new sessions
- 📱 **Mobile Responsive**: Works great on both desktop and mobile devices
- ⚡ **Fast & Lightweight**: Pure HTML, CSS, and JavaScript - no heavy frameworks

## How to Use

### 1. Start the API Server

Make sure your FastAPI server is running:

```bash
cd src/my_app/agent
python main.py
```

The server will start on `http://localhost:5001`

### 2. Open the Web Interface

Open your web browser and navigate to:

```
http://localhost:5001
```

### 3. Start Chatting

- Type your message in the input field at the bottom
- Press Enter or click the send button to send your message
- The assistant will respond with fantasy basketball advice
- Use the "New Session" button to start a fresh conversation
- Type "quit" to end the current conversation

## File Structure

```
static/
├── index.html      # Main HTML structure
├── styles.css      # CSS styling and animations
└── script.js       # JavaScript for API communication
```

## API Integration

The UI communicates with your AgentAPI through:

- **Endpoint**: `POST /chat`
- **Request Format**:
  ```json
  {
    "session_id": "unique_session_id",
    "user_message": "Your message here",
    "vs_id": "vector_store_id"
  }
  ```

## Customization

### Changing the Vector Store ID

In `script.js`, modify the `vectorStoreId` property:

```javascript
this.vectorStoreId = 'your_vector_store_id';
```

### Styling

Modify `styles.css` to customize:
- Colors and gradients
- Fonts and typography
- Layout and spacing
- Animations and transitions

### API Configuration

In `script.js`, update the API base URL if needed:

```javascript
this.apiBaseUrl = 'http://your-api-server:port';
```

## Troubleshooting

### Connection Issues

- Make sure the FastAPI server is running on port 5001
- Check the browser console for any JavaScript errors
- Verify CORS settings if running on different ports

### API Errors

- Check the server logs for detailed error messages
- Ensure the OpenAI API key is properly configured
- Verify that the vector store ID is valid

## Browser Compatibility

- Chrome 60+
- Firefox 55+
- Safari 12+
- Edge 79+

## Security Notes

- The current CORS configuration allows all origins (`*`) - restrict this in production
- API keys should be properly secured and not exposed in client-side code
- Consider adding authentication for production use
