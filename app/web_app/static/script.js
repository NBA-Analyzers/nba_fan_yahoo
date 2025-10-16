class FantasyBasketballChat {
    constructor() {
        console.log('FantasyBasketballChat constructor called');
        this.sessionId = null;
        this.isLoading = false;
        this.league_id = window.LEAGUE_ID && window.LEAGUE_ID !== null && window.LEAGUE_ID.trim() !== '' ? window.LEAGUE_ID : null;
        
        // Debug logging
        console.log('Debug - window.LEAGUE_ID:', window.LEAGUE_ID);
        console.log('Debug - window.SESSION_ID:', window.SESSION_ID);
        console.log('Debug - this.league_id:', this.league_id);
        
        this.initializeElements();
        this.bindEvents();
        // Always start with a new session
        this.startNewChat();
        console.log('FantasyBasketballChat initialized with league_id:', this.league_id);
    }
    
    initializeElements() {
        console.log('Initializing elements...');
        
        // Screen elements
        this.initialScreen = document.getElementById('initialScreen');
        this.sessionIdScreen = document.getElementById('sessionIdScreen');
        this.chatScreen = document.getElementById('chatScreen');
        
        // Initial screen elements (only new chat option)
        this.newChatOption = document.getElementById('newChatOption');
        
        // Chat screen elements
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.currentSessionIdDisplay = document.getElementById('currentSessionId');
        this.newSessionFromChatButton = document.getElementById('newSessionFromChatButton');
        this.quitSessionButton = document.getElementById('quitSessionButton');
        
        // Status elements
        this.connectionStatus = document.getElementById('connectionStatus');
        
        // Debug: Log which elements were found
        console.log('Elements found:', {
            initialScreen: !!this.initialScreen,
            sessionIdScreen: !!this.sessionIdScreen,
            chatScreen: !!this.chatScreen,
            newChatOption: !!this.newChatOption,
            chatMessages: !!this.chatMessages,
            messageInput: !!this.messageInput,
            sendButton: !!this.sendButton,
            currentSessionIdDisplay: !!this.currentSessionIdDisplay,
            newSessionFromChatButton: !!this.newSessionFromChatButton,
            quitSessionButton: !!this.quitSessionButton,
            connectionStatus: !!this.connectionStatus
        });
    }
    
    bindEvents() {
        console.log('Binding events...');
        
        // Initial screen events (only new chat)
        if (this.newChatOption) {
            this.newChatOption.addEventListener('click', () => {
                console.log('New chat clicked');
                this.startNewChat();
            });
        }
        
        // Chat screen events
        if (this.sendButton) {
            this.sendButton.addEventListener('click', () => {
                console.log('Send button clicked');
                this.sendMessage();
            });
        }
        
        if (this.messageInput) {
            this.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    console.log('Enter pressed in message input');
                    this.sendMessage();
                }
            });
        }
        
        if (this.newSessionFromChatButton) {
            this.newSessionFromChatButton.addEventListener('click', () => {
                console.log('New session from chat clicked');
                this.startNewChat();
            });
        }
        
        if (this.quitSessionButton) {
            this.quitSessionButton.addEventListener('click', () => {
                console.log('Quit session clicked');
                this.quitSession();
            });
        }
        
        console.log('Events bound successfully');
    }
    
    generateSessionId() {
        return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }
    
    showScreen(screenId) {
        console.log('Showing screen:', screenId);
        
        // Hide all screens
        if (this.initialScreen) this.initialScreen.classList.add('hidden');
        if (this.sessionIdScreen) this.sessionIdScreen.classList.add('hidden');
        if (this.chatScreen) this.chatScreen.classList.add('hidden');
        
        // Show target screen
        const targetScreen = document.getElementById(screenId);
        if (targetScreen) {
            targetScreen.classList.remove('hidden');
            console.log('Screen shown:', screenId);
        } else {
            console.error('Target screen not found:', screenId);
        }
        
        // Focus appropriate input
        if (screenId === 'chatScreen' && this.messageInput) {
            setTimeout(() => this.messageInput.focus(), 100);
        }
    }
    
    startNewChat() {
        this.sessionId = this.generateSessionId();
        this.updateSessionDisplay();
        this.clearChatMessages();
        this.addSystemMessage('Welcome to Fantasy Basketball Helper! I\'m here to help you with your league management, player analysis, and strategic advice. Use the "Quit Session" button or type \'quit\' to end the conversation.');
        this.showScreen('chatScreen');
    }
    
    quitSession() {
        console.log('Quit session button clicked - starting new session');
        
        // Add a system message showing the session ended
        this.addSystemMessage('Session ended. Starting a new session.');
        
        // Update status
        this.updateStatus('success', 'Session ended');
        
        // Start a new session after a short delay
        setTimeout(() => {
            this.startNewChat();
        }, 1500);
    }
    
    
    updateSessionDisplay() {
        if (this.currentSessionIdDisplay) {
            this.currentSessionIdDisplay.textContent = this.sessionId;
        }
    }
    
    clearChatMessages() {
        if (this.chatMessages) {
            this.chatMessages.innerHTML = '';
        }
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isLoading) return;
        
        // Add user message to chat
        this.addUserMessage(message);
        this.messageInput.value = '';
        
        // Check if user typed "quit" - handle it locally
        if (message.toLowerCase() === 'quit') {
            console.log('User typed quit - starting new session');
            this.addSystemMessage('Session ended. Starting a new session.');
            this.updateStatus('success', 'Session ended');
            
            setTimeout(() => {
                this.startNewChat();
            }, 1500);
            return;
        }
        
        // Show loading state for regular messages
        this.setLoading(true);
        
        try {
            const response = await this.callChatAPI(message);
            this.addAssistantMessage(response);
            this.updateStatus('success', 'Message sent successfully');
        } catch (error) {
            console.error('Error sending message:', error);
            this.addSystemMessage('Sorry, I encountered an error. Please try again.');
            this.updateStatus('error', 'Error sending message');
        } finally {
            this.setLoading(false);
        }
    }
    
    async callChatAPI(message) {
        const response = await fetch(`/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: this.sessionId,
                user_message: message,
                league_id: this.league_id,
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.text();
    }
    
    addUserMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user-message';
        messageDiv.innerHTML = `
            <div class="message-content">${this.escapeHtml(message)}</div>
        `;
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    addAssistantMessage(response) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant-message';
        const formattedResponse = this.formatAssistantResponse(response);
        messageDiv.innerHTML = `
            <div class="message-content">${formattedResponse}</div>
        `;
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    addSystemMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message system-message';
        messageDiv.innerHTML = `
            <div class="message-content">${this.escapeHtml(message)}</div>
        `;
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    showError(message) {
        // Create a temporary error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        errorDiv.style.cssText = `
            background: #f8d7da;
            color: #721c24;
            padding: 10px;
            border-radius: 8px;
            margin: 10px 0;
            border: 1px solid #f5c6cb;
        `;
        
        // Insert at the top of the session input card
        const sessionInputCard = document.querySelector('.session-input-card');
        sessionInputCard.insertBefore(errorDiv, sessionInputCard.firstChild);
        
        // Remove after 3 seconds
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.parentNode.removeChild(errorDiv);
            }
        }, 3000);
    }
    
    setLoading(loading) {
        this.isLoading = loading;
        this.sendButton.disabled = loading;
        
        if (loading) {
            this.sendButton.innerHTML = `
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            `;
            this.updateStatus('loading', 'Sending message...');
        } else {
            this.sendButton.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="22" y1="2" x2="11" y2="13"></line>
                    <polygon points="22,2 15,22 11,13 2,9 22,2"></polygon>
                </svg>
            `;
            this.updateStatus('ready', 'Ready');
        }
    }
    
    updateStatus(type, message) {
        this.connectionStatus.textContent = message;
        this.connectionStatus.className = `status-indicator ${type}`;
    }
    
    scrollToBottom() {
        if (this.chatMessages) {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        }
    }
    
    formatAssistantResponse(text) {
        // First escape HTML to prevent XSS
        let formatted = this.escapeHtml(text);
        
        // Replace line breaks with <br> tags
        formatted = formatted.replace(/\n/g, '<br>');
        
        // Format bullet points and lists
        formatted = formatted.replace(/^[\s]*[-•]\s+(.+)$/gm, '<div class="bullet-point">• $1</div>');
        formatted = formatted.replace(/^[\s]*(\d+)\.\s+(.+)$/gm, '<div class="numbered-point">$1. $2</div>');
        
        // Format headers (lines that end with :)
        formatted = formatted.replace(/^(.+):\s*$/gm, '<div class="response-header">$1:</div>');
        
        // Format code blocks (text between backticks)
        formatted = formatted.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
        
        // Format bold text (text between **)
        formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        
        // Format italic text (text between *)
        formatted = formatted.replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, '<em>$1</em>');
        
        // Wrap paragraphs
        const paragraphs = formatted.split('<br><br>');
        formatted = paragraphs.map(para => {
            if (para.trim() && !para.includes('<div class=') && !para.includes('<code') && !para.includes('<strong') && !para.includes('<em')) {
                return `<div class="response-paragraph">${para}</div>`;
            }
            return para;
        }).join('<br><br>');
        
        return formatted;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
}

// Initialize the chat when the page loads
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded');
    try {
        const chat = new FantasyBasketballChat();
        
        // No automatic connection test - only connect when user sends message
        
        // Make chat instance globally available for debugging
        window.fantasyChat = chat;
        console.log('Chat initialized and available as window.fantasyChat');
    } catch (error) {
        console.error('Error initializing chat:', error);
    }
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && window.fantasyChat) {
        // Focus the appropriate input based on current screen
        const activeScreen = document.querySelector('.screen:not(.hidden)');
        if (activeScreen && activeScreen.id === 'chatScreen') {
            window.fantasyChat.messageInput.focus();
        }
    }
});